import { describe, expect, it } from "bun:test";
import {
  WatcherQueryError,
  buildReviewState,
  mapRollupNode,
  orderStack,
  parsePullRequest,
  parseReviewStatePage,
  parseRollupPage,
  resolveChecks,
  resolveContext,
  resolveReviewState,
} from "../../../../../skills/poteto-mode/scripts/watch-pr/github.ts";
import {
  fakeReader,
  failedCheck,
  passingCheck,
  pendingCheck,
} from "./fakes.test-helper.ts";
import { parsePrNumber } from "../../../../../skills/poteto-mode/scripts/watch-pr/types.ts";

const context = {
  host: "github.com",
  owner: "owner",
  repo: "repo",
  number: parsePrNumber(42),
};

describe("checks fallback chain", () => {
  it("uses a non-empty fast-path result without a rollup query", async () => {
    const reader = fakeReader({
      fastPath: { kind: "checks", checks: [passingCheck("fast")] },
    });
    const read = await resolveChecks(reader, context);
    expect(read.source).toBe("gh-pr-checks");
    expect(read.checks.map((check) => check.name)).toEqual(["fast"]);
    expect(reader.calls).toEqual(["checksFastPath"]);
  });

  it("paginates GraphQL when the fast path is unusable", async () => {
    const reader = fakeReader({
      fastPath: { kind: "unusable", exitCode: 8, stderr: "" },
      rollupPages: [
        { checks: [passingCheck("first")], endCursor: "next" },
        { checks: [failedCheck("second")], endCursor: null },
      ],
    });
    const read = await resolveChecks(reader, context);
    expect(read.source).toBe("graphql-rollup");
    expect(read.checks.map((check) => check.name)).toEqual(["first", "second"]);
    expect(reader.calls).toEqual([
      "checksFastPath",
      "checkRollupPage:null",
      "checkRollupPage:next",
    ]);
  });

  it("falls back when valid fast-path JSON represented an empty list", async () => {
    const reader = fakeReader({
      fastPath: { kind: "checks", checks: [] },
      rollupPages: [{ checks: [pendingCheck("fallback")], endCursor: null }],
    });
    expect((await resolveChecks(reader, context)).checks[0].name).toBe(
      "fallback"
    );
    expect(reader.calls).toEqual(["checksFastPath", "checkRollupPage:null"]);
  });

  it("resolves to empty checks from graphql-rollup when the fast path is unusable at exit 1 and the rollup is null", async () => {
    const reader = fakeReader({
      fastPath: { kind: "unusable", exitCode: 1, stderr: "" },
    });
    expect(await resolveChecks(reader, context)).toEqual({
      source: "graphql-rollup",
      checks: [],
    });
    expect(reader.calls).toEqual(["checksFastPath", "checkRollupPage:null"]);
  });
});

describe("parseRollupPage", () => {
  const rollupResponse = (statusCheckRollup: unknown) => ({
    data: {
      repository: {
        pullRequest: {
          commits: { nodes: [{ commit: { statusCheckRollup } }] },
        },
      },
    },
  });

  for (const connection of ["contexts", "reviewThreads"] as const) {
    const parse = (pageInfo: object) => connection === "contexts"
      ? parseRollupPage(rollupResponse({ contexts: { nodes: [], pageInfo } }))
      : parseReviewStatePage({ data: { repository: { pullRequest: {
          headRefOid: "head", author: { login: "octocat" },
          reviewThreads: { nodes: [], pageInfo },
          reviews: { nodes: [] }, reviewRequests: { nodes: [] }, comments: { nodes: [] },
        } } } });

    for (const endCursor of [null, ""]) {
      it(`rejects synthetic ${connection} hasNextPage=true plus endCursor=${JSON.stringify(endCursor)}`, () => {
        expect(() => parse({ hasNextPage: true, endCursor })).toThrow(
          `${connection}.pageInfo.endCursor`
        );
      });
    }

    it(`rejects ${connection} with an omitted endCursor`, () => {
      expect(() => parse({ hasNextPage: true })).toThrow(
        `${connection}.pageInfo.endCursor`
      );
    });

    it(`preserves ${connection} continuation and terminal pages`, () => {
      expect(parse({ hasNextPage: true, endCursor: "next" }).endCursor).toBe("next");
      for (const endCursor of [null, "", "last"]) {
        expect(parse({ hasNextPage: false, endCursor }).endCursor).toBeNull();
      }
    });
  }

  it("throws when the PR has zero commits", () => {
    expect(() =>
      parseRollupPage({
        data: {
          repository: { pullRequest: { commits: { nodes: [] } } },
        },
      })
    ).toThrow("missing commits.nodes[0]");
  });

  it("throws when every node on a page is an unknown check type", () => {
    expect(() =>
      parseRollupPage(
        rollupResponse({
          contexts: {
            nodes: [{ __typename: "FutureCheck" }],
            pageInfo: { hasNextPage: false, endCursor: null },
          },
        })
      )
    ).toThrow("invalid contexts.nodes");
  });

  it("filters an unknown node but keeps a known check on the same page", () => {
    const page = parseRollupPage(
      rollupResponse({
        contexts: {
          nodes: [
            { __typename: "FutureCheck" },
            {
              __typename: "CheckRun",
              name: "ci",
              status: "COMPLETED",
              conclusion: "SUCCESS",
            },
          ],
          pageInfo: { hasNextPage: false, endCursor: null },
        },
      })
    );
    expect(page.checks.map((check) => check.name)).toEqual(["ci"]);
  });
});

describe("rollup node mapping", () => {
  it("maps terminal and non-terminal CheckRun states fail closed", () => {
    const cases = [
      ["IN_PROGRESS", null, "pending", "PENDING"],
      ["COMPLETED", "SUCCESS", "passed", "SUCCESS"],
      ["COMPLETED", "NEUTRAL", "skipped", "NEUTRAL"],
      ["COMPLETED", "SKIPPED", "skipped", "SKIPPED"],
      ["COMPLETED", "ACTION_REQUIRED", "failed", "ACTION_REQUIRED"],
      ["COMPLETED", "TIMED_OUT", "failed", "FAILURE"],
      ["COMPLETED", "FUTURE_VALUE", "failed", "FAILURE"],
    ] as const;
    for (const [status, conclusion, kind, reportedState] of cases) {
      expect(
        mapRollupNode({
          __typename: "CheckRun",
          name: "ci",
          status,
          conclusion,
        })
      ).toMatchObject({ kind, reportedState });
    }
  });

  it("classifies an in-progress Code Review Gate from the rollup as the gate", () => {
    expect(
      mapRollupNode({
        __typename: "CheckRun",
        name: "Code Review Gate",
        status: "IN_PROGRESS",
        conclusion: null,
      })
    ).toMatchObject({ kind: "code-review-gate" });
    expect(
      mapRollupNode({
        __typename: "StatusContext",
        context: "Code Review Gate",
        state: "PENDING",
      })
    ).toMatchObject({ kind: "code-review-gate" });
  });

  it("maps StatusContext states and drops unknown typenames", () => {
    expect(
      mapRollupNode({
        __typename: "StatusContext",
        context: "ci",
        state: "EXPECTED",
      })
    ).toMatchObject({ kind: "pending", reportedState: "PENDING" });
    expect(
      mapRollupNode({
        __typename: "StatusContext",
        context: "ci",
        state: "FUTURE_VALUE",
      })
    ).toMatchObject({ kind: "failed", reportedState: "FUTURE_VALUE" });
    expect(mapRollupNode({ __typename: "FutureNode" })).toBeNull();
  });
});

describe("closed enum parsing", () => {
  const rawPullRequest = {
    mergeable: "MERGEABLE",
    mergeStateStatus: "CLEAN",
    reviewDecision: "APPROVED",
    headRefOid: "head",
    headRefName: "feature",
    baseRefName: "main",
    state: "OPEN",
    mergedAt: null,
    isDraft: false,
  };

  it("accepts mergeStateStatus CONFLICTING", () => {
    expect(
      parsePullRequest(
        { ...rawPullRequest, mergeStateStatus: "CONFLICTING" },
        context
      ).mergeStateStatus
    ).toBe("CONFLICTING");
  });

  it("reads gh's empty reviewDecision as no decision rather than a parse failure", () => {
    expect(
      parsePullRequest({ ...rawPullRequest, reviewDecision: "" }, context)
        .reviewDecision
    ).toBeNull();
  });

  it("still rejects an unknown reviewDecision", () => {
    expect(() =>
      parsePullRequest({ ...rawPullRequest, reviewDecision: "MAYBE" }, context)
    ).toThrow(WatcherQueryError);
  });

  it("rejects unknown enum values as retryable errors carrying the raw value", () => {
    try {
      parsePullRequest(
        { ...rawPullRequest, mergeStateStatus: "FUTURE_STATE" },
        context
      );
      throw new Error("expected parser to throw");
    } catch (error) {
      expect(error).toBeInstanceOf(WatcherQueryError);
      if (!(error instanceof WatcherQueryError)) throw error;
      expect(error.failure).toMatchObject({
        kind: "missing-key",
        retryable: true,
        rawValue: '"FUTURE_STATE"',
      });
    }
  });
});

function reviewStateResponse(args: {
  readonly threads?: readonly unknown[];
  readonly reviews?: readonly unknown[];
  readonly reviewRequests?: readonly unknown[];
  readonly pageInfo?: { readonly hasNextPage: boolean; readonly endCursor: string | null };
}) {
  return {
    data: {
      repository: {
        pullRequest: {
          headRefOid: "head",
          author: { login: "octocat" },
          reviewThreads: {
            pageInfo: args.pageInfo ?? { hasNextPage: false, endCursor: null },
            nodes: args.threads ?? [],
          },
          reviews: {
            nodes: (args.reviews ?? []).map((review) => ({
              url: "https://github.com/owner/repo/pull/42#pullrequestreview-1",
              body: "",
              state: "COMMENTED",
              commit: { oid: "head" },
              ...(review as object),
            })),
          },
          reviewRequests: { nodes: args.reviewRequests ?? [] },
          comments: { nodes: [] },
        },
      },
    },
  };
}

const parseReviewState = (response: unknown) =>
  buildReviewState([parseReviewStatePage(response)]);

describe("parseReviewState", () => {
  it("ignores reviews and review requests whose account was deleted", () => {
    const state = parseReviewState(
      reviewStateResponse({
        threads: [
          {
            id: "one",
            isResolved: false,
            comments: {
              nodes: [
                {
                  body: "looks off",
                  createdAt: "now",
                  path: "a.ts",
                  line: 1,
                  author: {
                    login: "copilot-pull-request-reviewer",
                    __typename: "Bot",
                  },
                },
              ],
            },
          },
        ],
        reviews: [
          { author: null },
          { author: { login: "copilot-pull-request-reviewer", __typename: "Bot" } },
        ],
        reviewRequests: [{ requestedReviewer: null }],
      })
    );
    expect(state.pendingBots).toEqual([]);
    expect(state.threads.map((thread) => thread.bot)).toEqual([
      { login: "copilot-pull-request-reviewer", passes: 1 },
    ]);
  });
  it("annotates Bugbot threads with distinct review-pass counts", () => {
    const response = reviewStateResponse({
      threads: [
        {
          id: "one",
          isResolved: false,
          comments: {
            nodes: [
              {
                body: "RUN_ID: run-1",
                createdAt: "now",
                path: "a.ts",
                line: 1,
                author: { login: "bugbot", __typename: "User" },
              },
            ],
          },
        },
        {
          id: "two",
          isResolved: false,
          comments: {
            nodes: [
              {
                body: "CURSOR_AUTOMATION_ID: run-2 severity high",
                createdAt: "now",
                path: null,
                line: null,
                author: { login: "cursor", __typename: "User" },
              },
            ],
          },
        },
        {
          id: "resolved",
          isResolved: true,
          comments: {
            nodes: [
              {
                body: "RUN_ID: run-3",
                createdAt: "now",
                path: null,
                line: null,
                author: { login: "bugbot", __typename: "User" },
              },
            ],
          },
        },
      ],
    });
    const state = parseReviewState(response);
    expect(state.threads).toHaveLength(2);
    expect(state.threads.map((thread) => thread.bot)).toEqual([
      { login: "bugbot", passes: 3 },
      { login: "bugbot", passes: 3 },
    ]);
    expect(state.pendingBots).toEqual([]);
  });

  it("classifies a first comment from a GitHub Bot author as that bot, counting its reviews", () => {
    const response = reviewStateResponse({
      threads: [
        {
          id: "copilot-thread",
          isResolved: false,
          comments: {
            nodes: [
              {
                body: "Consider renaming this variable.",
                createdAt: "now",
                path: "a.ts",
                line: 3,
                author: {
                  login: "copilot-pull-request-reviewer",
                  __typename: "Bot",
                },
              },
            ],
          },
        },
      ],
      reviews: [
        {
          author: {
            login: "copilot-pull-request-reviewer",
            __typename: "Bot",
          },
        },
        {
          author: {
            login: "copilot-pull-request-reviewer",
            __typename: "Bot",
          },
        },
        { author: { login: "octocat", __typename: "User" } },
      ],
    });
    const state = parseReviewState(response);
    expect(state.threads).toHaveLength(1);
    expect(state.threads[0].bot).toEqual({
      login: "copilot-pull-request-reviewer",
      passes: 2,
    });
  });

  it("leaves a human-authored thread's bot null", () => {
    const response = reviewStateResponse({
      threads: [
        {
          id: "human-thread",
          isResolved: false,
          comments: {
            nodes: [
              {
                body: "Please add a test for this.",
                createdAt: "now",
                path: "a.ts",
                line: 5,
                author: { login: "octocat", __typename: "User" },
              },
            ],
          },
        },
      ],
    });
    const state = parseReviewState(response);
    expect(state.threads[0].bot).toBeNull();
  });

  it("collects pending Bot review requests, ignoring human requests", () => {
    const response = reviewStateResponse({
      reviewRequests: [
        {
          requestedReviewer: {
            __typename: "Bot",
            login: "copilot-pull-request-reviewer",
          },
        },
        { requestedReviewer: { __typename: "User" } },
      ],
    });
    expect(parseReviewState(response).pendingBots).toEqual([
      "copilot-pull-request-reviewer",
    ]);
  });

  it("reports no pending review bots when there are no review requests", () => {
    expect(parseReviewState(reviewStateResponse({})).pendingBots).toEqual([]);
  });
});

describe("review thread pagination", () => {
  const thread = (id: string, resolved = false) => ({
    id,
    firstComment: {
      authorLogin: "someone",
      body: "please fix",
      path: "a.ts",
      line: 1,
      createdAt: "now",
    },
    resolved,
    botLogin: null,
  });

  it("keeps walking pages until the cursor is exhausted", async () => {
    const reader = fakeReader({
      threadPages: [
        { threads: [thread("one")], endCursor: "next" },
        { threads: [thread("two")], endCursor: "last" },
        { threads: [thread("three")], endCursor: null },
      ],
    });
    const state = await resolveReviewState(reader, context);
    expect(state.threads.map((item) => item.id)).toEqual(["one", "two", "three"]);
    expect(reader.calls).toEqual([
      "reviewStatePage:null",
      "reviewStatePage:next",
      "reviewStatePage:last",
    ]);
  });

  it("sees an unresolved thread that sits past the first page", async () => {
    const reader = fakeReader({
      threadPages: [
        { threads: [thread("early", true)], endCursor: "next" },
        { threads: [thread("late")], endCursor: null },
      ],
    });
    const state = await resolveReviewState(reader, context);
    expect(state.threads.map((item) => item.id)).toEqual(["late"]);
  });

  it("stops after a single page when the cursor is exhausted", async () => {
    const reader = fakeReader({
      threadPages: [{ threads: [thread("only")], endCursor: null }],
    });
    expect((await resolveReviewState(reader, context)).threads).toHaveLength(1);
    expect(reader.calls).toEqual(["reviewStatePage:null"]);
  });

  it("counts Bugbot review passes across every page", async () => {
    const bugbot = (id: string, runId: string) => ({
      id,
      firstComment: {
        authorLogin: "bugbot",
        body: `RUN_ID: ${runId}`,
        path: "a.ts",
        line: 1,
        createdAt: "now",
      },
      resolved: false,
      botLogin: "bugbot",
    });
    const reader = fakeReader({
      threadPages: [
        { threads: [bugbot("one", "run-1")], endCursor: "next" },
        { threads: [bugbot("two", "run-2")], endCursor: null },
      ],
    });
    const state = await resolveReviewState(reader, context);
    expect(state.threads.map((item) => item.bot)).toEqual([
      { login: "bugbot", passes: 2 },
      { login: "bugbot", passes: 2 },
    ]);
  });

  it("drops resolved threads from later pages too", async () => {
    const reader = fakeReader({
      threadPages: [
        { threads: [thread("one")], endCursor: "next" },
        { threads: [thread("two", true)], endCursor: null },
      ],
    });
    expect(
      (await resolveReviewState(reader, context)).threads.map((item) => item.id)
    ).toEqual(["one"]);
  });

  it("returns the cursor only while another page exists", () => {
    const cursor = (hasNextPage: boolean) =>
      parseReviewStatePage(
        reviewStateResponse({ pageInfo: { hasNextPage, endCursor: "cursor" } })
      ).endCursor;
    expect(cursor(true)).toBe("cursor");
    expect(cursor(false)).toBeNull();
  });

  it("rejects a page that omits pageInfo instead of assuming one page", () => {
    const response = {
      data: {
        repository: {
          pullRequest: {
            headRefOid: "head",
            author: { login: "octocat" },
            reviewThreads: { nodes: [] },
            reviews: { nodes: [] },
            reviewRequests: { nodes: [] },
            comments: { nodes: [] },
          },
        },
      },
    };
    expect(() => parseReviewStatePage(response)).toThrow(
      "missing reviewThreads.pageInfo"
    );
  });
});

describe("context and stack discovery", () => {
  it("uses the origin host for a fully explicit context", async () => {
    const reader = fakeReader();
    expect(
      await resolveContext({
        reader,
        owner: "explicit",
        repo: "repo",
        pr: context.number,
      })
    ).toEqual({
      host: "github.com",
      owner: "explicit",
      repo: "repo",
      number: context.number,
    });
    expect(reader.calls).toEqual(["originRepo"]);
  });

  it("defaults an explicit context to public GitHub without an origin", async () => {
    const saved = process.env.GH_HOST;
    delete process.env.GH_HOST;
    try {
      const reader = fakeReader({ origin: null });
      expect(
        await resolveContext({
          reader,
          owner: "explicit",
          repo: "repo",
          pr: context.number,
        })
      ).toEqual({
        host: "github.com",
        owner: "explicit",
        repo: "repo",
        number: context.number,
      });
      expect(reader.calls).toEqual(["originRepo"]);
    } finally {
      if (saved === undefined) delete process.env.GH_HOST;
      else process.env.GH_HOST = saved;
    }
  });

  it("uses the local origin before currentPr for an explicit number", async () => {
    const reader = fakeReader({
      origin: { host: "github.com", owner: "local", repo: "checkout" },
    });
    expect(
      await resolveContext({
        reader,
        owner: null,
        repo: null,
        pr: context.number,
      })
    ).toEqual({
      host: "github.com",
      owner: "local",
      repo: "checkout",
      number: context.number,
    });
    expect(reader.calls).toEqual(["originRepo"]);
  });

  it("orders the connected stack bottom-to-top", () => {
    const ordered = orderStack(context, [
      {
        number: parsePrNumber(41),
        headRefName: "base-feature",
        baseRefName: "main",
      },
      {
        number: context.number,
        headRefName: "feature",
        baseRefName: "base-feature",
      },
      {
        number: parsePrNumber(43),
        headRefName: "upstack",
        baseRefName: "feature",
      },
    ]);
    expect(ordered.map((item) => Number(item.number))).toEqual([41, 42, 43]);
  });
});
