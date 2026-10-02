import { describe, expect, it } from "bun:test";
import { parseReviewState } from "../../../../../skills/poteto-mode/scripts/watch-pr/github.ts";
import {
  HEADS,
  botReview,
  comment,
  realAckComment,
  restReviews,
  reviewBodiesResponse,
} from "./review-fixtures.test-helper.ts";
import type { RestComment, RestReview } from "./review-fixtures.test-helper.ts";

const COPILOT = "copilot-pull-request-reviewer";
const MARKER = "<!-- ccr-overview-v2 -->";

function flagged(args: {
  readonly head: string;
  readonly reviews: readonly RestReview[];
  readonly comments?: readonly RestComment[];
  readonly prAuthor?: string | null;
}) {
  const state = parseReviewState(
    reviewBodiesResponse({
      headRefOid: args.head,
      reviews: args.reviews,
      ...(args.comments === undefined ? {} : { comments: args.comments }),
      ...(args.prAuthor === undefined ? {} : { prAuthor: args.prAuthor }),
    })
  );
  return state;
}

const json = (value: unknown): unknown => JSON.parse(JSON.stringify(value));
const finding = (section: string, title: string, location: string | null) => ({
  section,
  title,
  location,
});

describe("review body classification over the real fixtures", () => {
  const none: null = null;
  const table: readonly [
    pr: 104 | 107 | 108,
    id: string,
    expected: ReturnType<typeof finding> | null,
  ][] = [
    [104, "5386322877", none],
    [104, "5386340917", none],
    [
      104,
      "5386371606",
      finding(
        "Previously missed",
        "Require listed model catalog to support requested reasoning effort",
        "skills/setup-pstack/scripts/check-models-config.py:108"
      ),
    ],
    [107, "5386573417", none],
    [107, "5386587770", none],
    [
      107,
      "5386669231",
      finding(
        "Previously missed",
        "Align none-effort lint claims with the static model table",
        "skills/setup-pstack/references/models-config.md:14"
      ),
    ],
    [107, "5386687443", none],
    [
      107,
      "5386703352",
      finding(
        "Previously missed",
        "Documentation overstates lint coverage for gpt-6.1-luna",
        "skills/setup-pstack/references/models-config.md:14"
      ),
    ],
    [107, "5386732704", none],
    [108, "5388102853", none],
    [108, "5388116138", none],
    [108, "5388116230", none],
    [108, "5388116311", none],
    [108, "5388116396", none],
    [
      108,
      "5388128492",
      finding(
        "Previously missed",
        "Porting invariant conflicts with unreworked cloud orchestration requirements",
        "PORTING.md:45"
      ),
    ],
  ];

  it("covers every review in the three fixture files", () => {
    for (const pr of [104, 107, 108] as const)
      expect(
        restReviews(pr).map((review) => review.html_url.split("-").pop())
      ).toEqual(table.filter(([row]) => row === pr).map(([, id]) => id));
  });

  for (const [pr, id, expected] of table)
    it(`#${pr} review ${id} at its own commit reports ${expected === null ? "no finding" : expected.title}`, () => {
      const review = restReviews(pr).find((row) => row.id === Number(id));
      if (review === undefined) throw new Error(`fixture lacks ${id}`);
      const state = flagged({ head: review.commit_id, reviews: [review] });
      expect(state.flaggedReviews.map((row) => row.reading)).toEqual(
        expected === null
          ? []
          : [
              {
                kind: "findings",
                format: "copilot-overview-v2",
                findings: [expected],
              },
            ]
      );
      expect(state.unreadReviews).toEqual([]);
    });

  it("never reads a user-authored review, even with a bot's findings in its body", () => {
    const body = restReviews(104)[2]?.body ?? "";
    const review = {
      ...botReview({ id: 9, commit: HEADS[104], body }),
      user: { login: "mdsmithaustin", type: "User" },
    };
    const state = flagged({ head: HEADS[104], reviews: [review] });
    expect(state.flaggedReviews).toEqual([]);
    expect(state.unreadReviews).toEqual([]);
  });
});

describe("which reviews count", () => {
  it("#104 flags only the Copilot review of the head, as an open review", () => {
    const state = flagged({ head: HEADS[104], reviews: restReviews(104) });
    expect(
      state.flaggedReviews.map((row) => [row.id, row.status, row.bot, row.commitOid])
    ).toEqual([["5386371606", "open", COPILOT, HEADS[104]]]);
    expect(state.flaggedReviews[0]?.url).toBe(
      "https://github.com/mdsmithaustin/pstack/pull/104#pullrequestreview-5386371606"
    );
  });

  it("#104 flags nothing once the head moves past that review's commit", () => {
    expect(
      flagged({ head: "f".repeat(40), reviews: restReviews(104) }).flaggedReviews
    ).toEqual([]);
  });

  it("#107 at its final head is clean, though two earlier passes had findings", () => {
    const state = flagged({ head: HEADS[107], reviews: restReviews(107) });
    expect(state.flaggedReviews).toEqual([]);
    expect(state.unreadReviews).toEqual([]);
  });

  it("#108 at 3e3260b7 flags review 5388128492 as open", () => {
    const state = flagged({ head: HEADS[108], reviews: restReviews(108) });
    expect(json(state.flaggedReviews.map((row) => [row.id, row.status]))).toEqual([
      ["5388128492", "open"],
    ]);
  });

  it("skips a PENDING review", () => {
    const body = restReviews(104)[2]?.body ?? "";
    const review = botReview({ id: 5, commit: HEADS[104], body, state: "PENDING" });
    expect(flagged({ head: HEADS[104], reviews: [review] }).flaggedReviews).toEqual(
      []
    );
  });

  it("ignores the same bot's marked reviews of older commits", () => {
    const body = restReviews(104)[2]?.body ?? "";
    const reviews = [
      botReview({ id: 5, commit: HEADS[104], body }),
      ...Array.from({ length: 5 }, (_, index) =>
        botReview({ id: 10 + index, commit: "a".repeat(40), body: MARKER })
      ),
    ];
    expect(
      json(flagged({ head: HEADS[104], reviews }).flaggedReviews.map((row) => row.id))
    ).toEqual(["5"]);
  });
});

describe("acknowledging a flagged review", () => {
  const link = "https://github.com/mdsmithaustin/pstack/pull/104#pullrequestreview-5386371606";
  const statusOf = (
    comments: readonly RestComment[],
    prAuthor: string | null = "mdsmithaustin"
  ) =>
    flagged({
      head: HEADS[104],
      reviews: restReviews(104),
      comments,
      prAuthor,
    }).flaggedReviews.map((row) => row.status);

  it("accepts the PR author, whatever their association", () => {
    expect(
      statusOf([
        comment({ id: 1, body: `Disproof: ${link}`, login: "mdsmithaustin", association: "NONE" }),
      ])
    ).toEqual(["acknowledged"]);
  });

  it("accepts an OWNER, MEMBER, or COLLABORATOR who is not the author", () => {
    for (const association of ["OWNER", "MEMBER", "COLLABORATOR"])
      expect(
        statusOf([comment({ id: 1, body: `Fixed. ${link}`, login: "maintainer", association })])
      ).toEqual(["acknowledged"]);
  });

  it("records who acknowledged and where", () => {
    const state = flagged({
      head: HEADS[104],
      reviews: restReviews(104),
      comments: [
        comment({ id: 7, body: `Fixed. ${link}`, login: "maintainer", association: "MEMBER" }),
      ],
    });
    expect(state.flaggedReviews[0]).toMatchObject({
      status: "acknowledged",
      ack: {
        author: "maintainer",
        url: "https://github.com/owner/repo/pull/1#issuecomment-7",
      },
    });
  });

  it("rejects a bot, even one with write access", () => {
    expect(
      statusOf([
        comment({ id: 1, body: link, login: "helper", association: "MEMBER", type: "Bot" }),
      ])
    ).toEqual(["open"]);
  });

  it("rejects a commenter who is neither the author nor trusted", () => {
    for (const association of ["NONE", "CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "SOMETHING_NEW"])
      expect(
        statusOf([comment({ id: 1, body: link, login: "stranger", association })])
      ).toEqual(["open"]);
  });

  it("rejects a link to a longer review id that starts with the same digits", () => {
    expect(
      statusOf([
        comment({
          id: 1,
          body: `${link}0`,
          login: "mdsmithaustin",
          association: "OWNER",
        }),
      ])
    ).toEqual(["open"]);
  });

  it("rejects a comment that mentions the review without linking it", () => {
    expect(
      statusOf([
        comment({
          id: 1,
          body: "Follow-up on Copilot's second review of this PR (22:28Z): fixed in abc123.",
          login: "mdsmithaustin",
          association: "OWNER",
        }),
      ])
    ).toEqual(["open"]);
  });

  it("clears the real #108 review with its real acknowledgment comment", () => {
    const state = flagged({
      head: HEADS[108],
      reviews: restReviews(108),
      comments: [realAckComment()],
      prAuthor: "mdsmithaustin",
    });
    expect(state.flaggedReviews).toMatchObject([
      {
        id: "5388128492",
        status: "acknowledged",
        ack: {
          author: "mdsmithaustin",
          url: "https://github.com/mdsmithaustin/pstack/pull/108#issuecomment-5945280704",
        },
      },
    ]);
  });
});

describe("bodies the registry does not understand", () => {
  const at = (body: string, login = COPILOT) =>
    flagged({
      head: "head",
      reviews: [botReview({ id: 77, commit: "head", body, login })],
    });

  it("blocks on a non-empty body from the Copilot login that no format claims", () => {
    const state = at("## Copilot code review v3\n\nLooks risky.\n");
    expect(state.flaggedReviews).toMatchObject([
      {
        id: "77",
        status: "open",
        bot: COPILOT,
        reading: { kind: "unrecognized", excerpt: "## Copilot code review v3" },
      },
    ]);
    expect(state.unreadReviews).toEqual([]);
  });

  it("notes, without blocking, a non-empty body from any other bot", () => {
    const state = at("Bugbot reviewed your changes and found no bugs!", "cursor-bugbot");
    expect(state.flaggedReviews).toEqual([]);
    expect(json(state.unreadReviews)).toEqual([
      {
        id: "77",
        url: "https://github.com/owner/repo/pull/1#pullrequestreview-77",
        bot: "cursor-bugbot",
        excerpt: "Bugbot reviewed your changes and found no bugs!",
      },
    ]);
  });

  it("treats an empty or blank body as clean for every bot", () => {
    for (const login of [COPILOT, "cursor-bugbot"]) {
      const state = at("  \n", login);
      expect(state.flaggedReviews).toEqual([]);
      expect(state.unreadReviews).toEqual([]);
    }
  });

  it("counts every item of an unknown section in a recognized Copilot body", () => {
    const body = `${MARKER}\n<details>\n<summary><strong>Low confidence (2)</strong></summary>\n</details>`;
    expect(at(body).flaggedReviews).toMatchObject([
      {
        reading: {
          kind: "findings",
          findings: [
            { section: "Low confidence", title: "(unparsed)", location: null },
            { section: "Low confidence", title: "(unparsed)", location: null },
          ],
        },
      },
    ]);
  });

  it("leaves thread-linked Open items and Resolved items to the thread gate", () => {
    const body = `${MARKER}\n<details open>\n<summary><strong>Open (1)</strong></summary>\n\n- [Rename it](#discussion_r42) · New\n</details>\n<details>\n<summary><strong>Resolved since last review (2)</strong></summary>\n\n- [Done](#discussion_r41)\n</details>`;
    expect(at(body).flaggedReviews).toEqual([]);
  });

  it("flags an Open item that no thread carries", () => {
    const body = `${MARKER}\n<details open>\n<summary><strong>Open (1)</strong></summary>\n\n- Needs a thread-less look\n</details>`;
    expect(at(body).flaggedReviews).toMatchObject([
      {
        reading: {
          kind: "findings",
          findings: [{ section: "Open", title: "Needs a thread-less look", location: null }],
        },
      },
    ]);
  });
});
