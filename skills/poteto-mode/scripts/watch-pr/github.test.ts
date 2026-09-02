import { describe, expect, it } from "bun:test";
import {
  ChecksUnavailable,
  WatcherQueryError,
  mapRollupNode,
  orderStack,
  parsePullRequest,
  parseReviewState,
  resolveChecks,
  resolveContext,
} from "./github.ts";
import {
  fakeReader,
  failedCheck,
  passingCheck,
  pendingCheck,
} from "./fakes.test-helper.ts";
import { parsePrNumber } from "./types.ts";

const context = {
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

  it("fails closed when both paths are empty", async () => {
    const reader = fakeReader({
      fastPath: {
        kind: "unusable",
        exitCode: 8,
        stderr: "credential cannot read checks",
      },
    });
    await expect(resolveChecks(reader, context)).rejects.toBeInstanceOf(
      ChecksUnavailable
    );
    expect(reader.calls).toEqual(["checksFastPath", "checkRollupPage:null"]);
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
}) {
  return {
    data: {
      repository: {
        pullRequest: {
          reviewThreads: { nodes: args.threads ?? [] },
          reviews: { nodes: args.reviews ?? [] },
          reviewRequests: { nodes: args.reviewRequests ?? [] },
        },
      },
    },
  };
}

describe("parseReviewState", () => {
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

describe("context and stack discovery", () => {
  it("returns a fully explicit context without any reader call", async () => {
    const reader = fakeReader();
    expect(
      await resolveContext({
        reader,
        owner: "explicit",
        repo: "repo",
        pr: context.number,
      })
    ).toEqual({ owner: "explicit", repo: "repo", number: context.number });
    expect(reader.calls).toEqual([]);
  });

  it("uses the local origin before currentPr for an explicit number", async () => {
    const reader = fakeReader({ origin: { owner: "local", repo: "checkout" } });
    expect(
      await resolveContext({
        reader,
        owner: null,
        repo: null,
        pr: context.number,
      })
    ).toEqual({ owner: "local", repo: "checkout", number: context.number });
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
