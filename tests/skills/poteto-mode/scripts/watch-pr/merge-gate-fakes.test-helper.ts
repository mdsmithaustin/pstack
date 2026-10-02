import { WatcherQueryError } from "../../../../../skills/poteto-mode/scripts/watch-pr/github.ts";
import type {
  Conversation,
  MergePort,
  MergeReceipt,
  MergeRequest,
  Truncation,
} from "../../../../../skills/poteto-mode/scripts/watch-pr/merge-gate.ts";
import type { MergeGateRuntime } from "../../../../../skills/poteto-mode/scripts/watch-pr/merge-gate-cli.ts";
import type {
  CommitSha,
  IssueComment,
  PatchId,
} from "../../../../../skills/poteto-mode/scripts/watch-pr/verdict.ts";
import {
  parseCommitSha,
  parsePatchId,
} from "../../../../../skills/poteto-mode/scripts/watch-pr/verdict.ts";
import type {
  ChecksFastPath,
  FlaggedReview,
  GitHubReader,
  PrContext,
  PullRequestFacts,
  Repository,
  ReviewId,
  ReviewThread,
  UnreadReview,
} from "../../../../../skills/poteto-mode/scripts/watch-pr/types.ts";
import { parsePrNumber } from "../../../../../skills/poteto-mode/scripts/watch-pr/types.ts";
import { fakeReader, failedCheck } from "./fakes.test-helper.ts";

function required<T>(value: T | null, label: string): T {
  if (value === null) throw new Error(`bad test constant: ${label}`);
  return value;
}
export const sha = (text: string): CommitSha =>
  required(parseCommitSha(text), text);
export const patchId = (text: string): PatchId =>
  required(parsePatchId(text), text);

export const HEAD = sha("a1".repeat(20));
export const MOVED_HEAD = sha("c3".repeat(20));
export const PATCH = patchId("b2".repeat(20));
export const OTHER_PATCH = patchId("d4".repeat(20));

export function verdictBody(
  args: {
    readonly verdict?: string;
    readonly head?: string;
    readonly patchId?: string;
    readonly docs?: string;
    readonly prose?: string;
  } = {}
): string {
  return [
    `Verdict: ${args.verdict ?? "PASS"}`,
    `Head: ${args.head ?? HEAD}`,
    `Patch-id: ${args.patchId ?? PATCH}`,
    `Docs: ${args.docs ?? "pass"}`,
    "",
    args.prose ?? "## Independent verdict (trail reviewer)",
    "Findings: none.",
  ].join("\n");
}

let commentCounter = 0;
export function issueComment(
  args: {
    readonly body?: string;
    readonly createdAt?: string;
    readonly login?: string;
    readonly association?: IssueComment["association"];
    readonly url?: string;
  } = {}
): IssueComment {
  commentCounter += 1;
  return {
    url:
      args.url ?? `https://github.com/owner/repo/pull/1#issuecomment-${commentCounter}`,
    author: { login: args.login ?? "mdsmithaustin", isBot: false },
    association: args.association ?? "OWNER",
    body: args.body ?? verdictBody(),
    createdAt: args.createdAt ?? "2026-10-02T12:00:00Z",
  };
}

export type PortCall =
  | { readonly kind: "conversation" }
  | {
      readonly kind: "patch-id";
      readonly baseRef: string;
      readonly headSha: CommitSha;
    }
  | { readonly kind: "merge"; readonly request: MergeRequest }
  | { readonly kind: "comment"; readonly body: string };

export interface FakePortOptions {
  readonly comments?: readonly IssueComment[];
  readonly prAuthor?: string | null;
  readonly patchId?: PatchId;
  readonly patchIdError?: Error;
  readonly mergeError?: Error;
  readonly receipt?: MergeReceipt;
  readonly truncated?: readonly Truncation[];
  readonly commentError?: Error;
}

export function fakePort(
  options: FakePortOptions = {}
): MergePort & { readonly calls: readonly PortCall[] } {
  const calls: PortCall[] = [];
  const conversation: Conversation = {
    prAuthor: options.prAuthor === undefined ? "mdsmithaustin" : options.prAuthor,
    comments: options.comments ?? [issueComment()],
    truncated: options.truncated ?? [],
  };
  return {
    calls,
    async conversation() {
      calls.push({ kind: "conversation" });
      return conversation;
    },
    async patchId(baseRef, headSha) {
      calls.push({ kind: "patch-id", baseRef, headSha });
      if (options.patchIdError !== undefined) throw options.patchIdError;
      return options.patchId ?? PATCH;
    },
    async merge(request) {
      calls.push({ kind: "merge", request });
      if (options.mergeError !== undefined) throw options.mergeError;
      return options.receipt ?? { kind: "merged", mergeCommit: "e5".repeat(20) };
    },
    async comment(_context, body) {
      calls.push({ kind: "comment", body });
      if (options.commentError !== undefined) throw options.commentError;
    },
  };
}

export interface WorldOptions {
  readonly facts?: Partial<Omit<PullRequestFacts, "context">>;
  readonly checks?: ChecksFastPath;
  readonly rollupState?: "SUCCESS" | "FAILURE" | "PENDING";
  readonly threads?: readonly ReviewThread[];
  readonly pendingBots?: readonly string[];
  readonly flaggedReviews?: readonly FlaggedReview[];
  readonly unreadReviews?: readonly UnreadReview[];
  readonly origin?: Repository | null;
  readonly port?: FakePortOptions;
}

/** A PR that passes every gate. Each test breaks one thing. */
export function world(options: WorldOptions = {}): {
  readonly reader: GitHubReader & { readonly calls: readonly string[] };
  readonly port: ReturnType<typeof fakePort>;
} {
  return {
    reader: fakeReader({
      facts: { headRefOid: HEAD, ...options.facts },
      ...(options.origin === undefined ? {} : { origin: options.origin }),
      ...(options.checks === undefined ? {} : { fastPath: options.checks }),
      commitRollups: [{ oid: HEAD, state: options.rollupState ?? "SUCCESS" }],
      ...(options.threads === undefined ? {} : { threads: options.threads }),
      ...(options.pendingBots === undefined
        ? {}
        : { pendingBots: options.pendingBots }),
      ...(options.flaggedReviews === undefined
        ? {}
        : { flaggedReviews: options.flaggedReviews }),
      ...(options.unreadReviews === undefined
        ? {}
        : { unreadReviews: options.unreadReviews }),
    }),
    port: fakePort(options.port),
  };
}

export const failingChecks = {
  kind: "checks",
  checks: [failedCheck("unit-tests")],
} as const;

export const REVIEW_URL =
  "https://github.com/owner/repo/pull/1#pullrequestreview-777";
export function openFlaggedReview(): FlaggedReview {
  return {
    id: "777" as ReviewId,
    url: REVIEW_URL,
    bot: "copilot-pull-request-reviewer",
    commitOid: HEAD,
    reading: {
      kind: "findings",
      format: "copilot-overview-v2",
      findings: [
        { section: "Open", title: "unchecked cast", location: "a.ts:3" },
      ],
    },
    status: "open",
  };
}
export function unreadReview(): UnreadReview {
  return {
    id: "778" as ReviewId,
    url: "https://github.com/owner/repo/pull/1#pullrequestreview-778",
    bot: "other-bot",
    untrustedExcerpt: "looks fine to me",
  };
}
export function unresolvedThread(): ReviewThread {
  return {
    id: "thread-1",
    firstComment: {
      authorLogin: "reviewer",
      body: "please rename this",
      path: "a.ts",
      line: 3,
      createdAt: "2026-10-02T12:00:00Z",
    },
    bot: null,
  };
}

export const failureThrownByGitHub = new WatcherQueryError({
  kind: "command-exit",
  retryable: true,
  code: 1,
  detail: "gh: HTTP 502",
});

export function testRuntime(
  parts: {
    readonly reader: GitHubReader;
    readonly port: MergePort;
    readonly bodyFileReadable?: boolean;
  }
): {
  readonly runtime: MergeGateRuntime;
  readonly stdout: string[];
  readonly stderr: string[];
} {
  const stdout: string[] = [];
  const stderr: string[] = [];
  return {
    stdout,
    stderr,
    runtime: {
      reader: parts.reader,
      port: parts.port,
      clock: { observedAt: () => "2026-10-02T12:30:00.000Z" },
      bodyFileReadable: () => parts.bodyFileReadable ?? true,
      stdout: (value) => stdout.push(value),
      stderr: (value) => stderr.push(value),
    },
  };
}

export const CONTEXT: PrContext = {
  host: "github.com",
  owner: "owner",
  repo: "repo",
  number: parsePrNumber(1),
};
