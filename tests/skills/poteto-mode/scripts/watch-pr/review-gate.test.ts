import { describe, expect, it } from "bun:test";
import { parseReviewState } from "../../../../../skills/poteto-mode/scripts/watch-pr/github.ts";
import {
  applyQueueSnapshot,
  classifyPr,
  createQueueState,
  evaluateQueue,
  readSnapshot,
  selectTierMajorStackDecision,
} from "../../../../../skills/poteto-mode/scripts/watch-pr/policy.ts";
import { parsePrNumber } from "../../../../../skills/poteto-mode/scripts/watch-pr/types.ts";
import type {
  NonEmpty,
  PollingOptions,
  PrContext,
  PrSnapshot,
} from "../../../../../skills/poteto-mode/scripts/watch-pr/types.ts";
import { failedCheck, fakeReader } from "./fakes.test-helper.ts";
import {
  HEADS,
  botReview,
  comment,
  realAckComment,
  restReviews,
  reviewBodiesResponse,
} from "./review-fixtures.test-helper.ts";
import type { RestComment, RestReview } from "./review-fixtures.test-helper.ts";

const context = (number: number): PrContext => ({
  host: "github.com",
  owner: "owner",
  repo: "repo",
  number: parsePrNumber(number),
});
const options = {
  interval: 10,
  sweepInterval: 300,
  timeout: 0,
  maxQueryErrors: 5,
  allowDraft: false,
} satisfies PollingOptions;
const json = (value: unknown): unknown => JSON.parse(JSON.stringify(value));

async function snapshotAt(args: {
  readonly number: number;
  readonly head: string;
  readonly reviews: readonly RestReview[];
  readonly comments?: readonly RestComment[];
  readonly reader?: Parameters<typeof fakeReader>[0];
}): Promise<PrSnapshot> {
  const state = parseReviewState(
    reviewBodiesResponse({
      headRefOid: args.head,
      reviews: args.reviews,
      ...(args.comments === undefined ? {} : { comments: args.comments }),
    })
  );
  return readSnapshot({
    reader: fakeReader({
      facts: { headRefOid: args.head },
      commitRollups: [{ oid: args.head, state: "SUCCESS" }],
      flaggedReviews: state.flaggedReviews,
      unreadReviews: state.unreadReviews,
      ...args.reader,
    }),
    context: context(args.number),
    pendingHistory: "include",
    allowDraft: false,
  });
}

describe("the review-findings gate on the real PRs", () => {
  it("blocks #104 at the head Copilot reviewed", async () => {
    const row = await snapshotAt({
      number: 104,
      head: HEADS[104],
      reviews: restReviews(104),
    });
    expect(json(classifyPr(row))).toMatchObject({
      kind: "blocker",
      blocker: {
        kind: "review-findings",
        pr: { number: 104 },
        reviews: [{ id: "5386371606", status: "open" }],
      },
    });
  });

  it("does not block #104 on that review once the head has moved", async () => {
    const row = await snapshotAt({
      number: 104,
      head: "f".repeat(40),
      reviews: restReviews(104),
    });
    expect(classifyPr(row).kind).toBe("ready");
  });

  it("reports #107 READY at its final head with nothing acknowledged or unread", async () => {
    const row = await snapshotAt({
      number: 107,
      head: HEADS[107],
      reviews: restReviews(107),
    });
    const decision = classifyPr(row);
    expect(decision.kind).toBe("ready");
    if (decision.kind !== "ready") throw new Error("expected ready");
    expect(decision.pr.proof.acknowledgedReviews).toEqual([]);
    expect(decision.pr.proof.unreadReviews).toEqual([]);
  });

  it("blocks #108 at 3e3260b7 on review 5388128492", async () => {
    const row = await snapshotAt({
      number: 108,
      head: HEADS[108],
      reviews: restReviews(108),
    });
    expect(json(classifyPr(row))).toMatchObject({
      kind: "blocker",
      blocker: {
        kind: "review-findings",
        reviews: [{ id: "5388128492", status: "open" }],
      },
    });
  });

  it("reports #108 READY once its real acknowledgment comment is read, and lists the review", async () => {
    const row = await snapshotAt({
      number: 108,
      head: HEADS[108],
      reviews: restReviews(108),
      comments: [realAckComment()],
    });
    const decision = classifyPr(row);
    expect(json(decision)).toMatchObject({
      kind: "ready",
      pr: {
        proof: {
          acknowledgedReviews: [
            {
              id: "5388128492",
              status: "acknowledged",
              ack: { author: "mdsmithaustin" },
            },
          ],
        },
      },
    });
  });

  it("blocks only on the open reviews when others are acknowledged", async () => {
    const body = restReviews(104)[2]?.body ?? "";
    const reviews = [
      botReview({ id: 21, commit: "head", body }),
      botReview({ id: 22, commit: "head", body }),
    ];
    const row = await snapshotAt({
      number: 1,
      head: "head",
      reviews,
      comments: [
        comment({
          id: 1,
          body: "https://github.com/owner/repo/pull/1#pullrequestreview-21",
          login: "mdsmithaustin",
          association: "OWNER",
        }),
      ],
    });
    expect(json(classifyPr(row))).toMatchObject({
      kind: "blocker",
      blocker: { kind: "review-findings", reviews: [{ id: "22" }] },
    });
  });

  it("lists an unread bot body on a READY PR without blocking it", async () => {
    const row = await snapshotAt({
      number: 1,
      head: "head",
      reviews: [
        botReview({
          id: 31,
          commit: "head",
          body: "Found no bugs!",
          login: "other-bot",
        }),
      ],
    });
    const decision = classifyPr(row);
    expect(json(decision)).toMatchObject({
      kind: "ready",
      pr: { proof: { unreadReviews: [{ id: "31", bot: "other-bot" }] } },
    });
  });
});

describe("blocker order", () => {
  const openReviews = () => {
    const body = restReviews(104)[2]?.body ?? "";
    return [botReview({ id: 41, commit: "head", body })];
  };

  it("ranks review-findings after merge-conflicts and review-threads, before failing-checks", async () => {
    const withReview = {
      head: "head",
      reviews: openReviews(),
      number: 1,
    };
    const failing = await snapshotAt({
      ...withReview,
      reader: {
        fastPath: { kind: "checks", checks: [failedCheck()] },
        commitRollups: [{ oid: "head", state: "FAILURE" }],
      },
    });
    expect(classifyPr(failing)).toMatchObject({
      kind: "blocker",
      blocker: { kind: "review-findings" },
    });
    const threaded = await snapshotAt({
      ...withReview,
      reader: {
        threads: [{ id: "t", firstComment: null, bot: null }],
        fastPath: { kind: "checks", checks: [failedCheck()] },
        commitRollups: [{ oid: "head", state: "FAILURE" }],
      },
    });
    expect(classifyPr(threaded)).toMatchObject({
      kind: "blocker",
      blocker: { kind: "review-threads" },
    });
    const conflicting = await snapshotAt({
      ...withReview,
      reader: {
        facts: { mergeable: "CONFLICTING" },
        threads: [{ id: "t", firstComment: null, bot: null }],
      },
    });
    expect(classifyPr(conflicting)).toMatchObject({
      kind: "blocker",
      blocker: { kind: "merge-conflicts" },
    });
  });

  it("scans a stack tier by tier so an upstack finding outranks frontier CI but not a frontier thread", async () => {
    const failingFrontier = await snapshotAt({
      number: 10,
      head: "head",
      reviews: [],
      reader: {
        fastPath: { kind: "checks", checks: [failedCheck()] },
        commitRollups: [{ oid: "head", state: "FAILURE" }],
      },
    });
    const upstackFinding = await snapshotAt({
      number: 11,
      head: "head",
      reviews: openReviews(),
    });
    expect(
      selectTierMajorStackDecision([failingFrontier, upstackFinding])
    ).toMatchObject({
      kind: "blocker",
      blocker: { kind: "review-findings", pr: { number: 11 } },
    });
    const threadedFrontier = await snapshotAt({
      number: 10,
      head: "head",
      reviews: [],
      reader: { threads: [{ id: "t", firstComment: null, bot: null }] },
    });
    expect(
      selectTierMajorStackDecision([threadedFrontier, upstackFinding])
    ).toMatchObject({
      kind: "blocker",
      blocker: { kind: "review-threads", pr: { number: 10 } },
    });
  });

  it("stops a queued stack on an open review finding", async () => {
    const queue = [context(50), context(51)] satisfies NonEmpty<PrContext>;
    let state = createQueueState(queue, 0);
    state = applyQueueSnapshot(
      state,
      await snapshotAt({ number: 50, head: "head", reviews: [] }),
      0,
      options
    ).state;
    state = applyQueueSnapshot(
      state,
      await snapshotAt({ number: 51, head: "head", reviews: openReviews() }),
      0,
      options
    ).state;
    expect(evaluateQueue(state, 0, options)).toMatchObject({
      kind: "blocker",
      blocker: { kind: "review-findings", pr: { number: 51 } },
    });
  });
});
