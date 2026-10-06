import { acknowledgment } from "./review-bodies.ts";
import {
  ciBlocker,
  conflictBlocker,
  findingsBlocker,
  gateReason,
  readSnapshot,
  threadBlocker,
} from "./policy.ts";
import type * as T from "./types.ts";
import {
  latestVerdict,
  parseCommitSha,
  type CommitSha,
  type IssueComment,
  type PatchId,
  type VerdictReading,
} from "./verdict.ts";

/**
 * The Shipping playbook's landing conditions, each one a gate the merge
 * must clear. Order is the order reports list them.
 */
export const GATES = [
  "verdict",
  "head",
  "patch-id",
  "checks",
  "review-bodies",
  "threads",
  "mergeability",
  "draft",
  "merge-queue",
] as const;
export type Gate = (typeof GATES)[number];

export interface GateResult {
  readonly gate: Gate;
  readonly ok: boolean;
  readonly detail: string;
}

/** Every gate is computed, so a failure never hides the ones behind it. */
export interface GateReport {
  readonly pr: T.PrContext;
  readonly state: T.PullRequestFacts["state"];
  readonly headSha: CommitSha | null;
  readonly localPatchId: PatchId | null;
  readonly verdict: VerdictReading;
  readonly gates: readonly GateResult[];
  readonly ready: boolean;
}

export type ReviewConnection =
  | "reviewThreads"
  | "reviewRequests"
  | "reviews"
  | "comments";
/** A connection holds more than the watcher's review query fetches. */
export interface Truncation {
  readonly connection: ReviewConnection;
  readonly total: number;
  readonly limit: number;
}
export interface Conversation {
  readonly prAuthor: string | null;
  readonly comments: readonly IssueComment[];
  readonly truncated: readonly Truncation[];
}
export interface MergeRequest {
  readonly context: T.PrContext;
  readonly headSha: CommitSha;
  readonly subject: string;
  readonly bodyFile: string;
}
/**
 * `gh pr merge` can succeed by only enqueueing the PR. `merged` means a
 * follow-up read saw the PR merged; anything else, including a failed read,
 * is `pending` and carries what was observed.
 */
export type MergeReceipt =
  | { readonly kind: "merged"; readonly mergeCommit: string | null }
  | {
      readonly kind: "pending";
      readonly mergeCommit: string | null;
      readonly observed: string;
    };

/** Every side effect and non-watcher read merge-gate performs. */
export interface MergePort {
  conversation(context: T.PrContext): Promise<Conversation>;
  patchId(baseRef: string, headSha: CommitSha): Promise<PatchId>;
  usesMergeQueue(context: T.PrContext, baseRef: string): Promise<boolean>;
  merge(request: MergeRequest): Promise<MergeReceipt>;
  comment(context: T.PrContext, body: string): Promise<void>;
}

export class MergeGateError extends Error {
  readonly source: "git" | "gh";
  constructor(source: "git" | "gh", detail: string) {
    super(detail);
    this.name = "MergeGateError";
    this.source = source;
  }
}

interface Outcome {
  readonly ok: boolean;
  readonly detail: string;
}
const pass = (detail: string): Outcome => ({ ok: true, detail });
const fail = (detail: string): Outcome => ({ ok: false, detail });
const plural = (count: number, noun: string): string =>
  `${count} ${noun}${count === 1 ? "" : "s"}`;
const names = (checks: readonly T.Check[]): string =>
  checks.map((check) => `${check.name} (${check.reportedState})`).join(", ");

function verdictGate(verdict: VerdictReading): Outcome {
  if (verdict.kind === "absent") return fail("no verdict block");
  if (verdict.kind === "malformed")
    return fail(
      `latest verdict comment ${verdict.url} by ${verdict.author} is malformed: ${verdict.problems.join("; ")}`
    );
  const { record } = verdict;
  const problems = [
    ...(record.verdict === "FAIL" ? ["Verdict: FAIL"] : []),
    ...(record.docs === "pass" || record.docs === "n/a"
      ? []
      : [`Docs: ${record.docs}`]),
  ];
  return problems.length === 0
    ? pass(
        `Verdict: ${record.verdict}, Docs: ${record.docs}, by ${record.author} at ${record.url}`
      )
    : fail(`${problems.join("; ")} by ${record.author} at ${record.url}`);
}

const repoLabel = (repo: T.Repository): string =>
  `${repo.host}/${repo.owner}/${repo.repo}`;

/**
 * A rebase moves the head without changing the reviewed patch (Shipping step
 * 3), so a differing head still passes when the patch-id gate passed.
 */
function headGate(
  verdict: VerdictReading,
  headSha: CommitSha | null,
  patchIdOk: boolean
): Outcome {
  if (verdict.kind !== "recorded") return fail("no verdict to compare");
  if (headSha === null) return fail("the PR head SHA is unreadable");
  if (verdict.record.head === headSha) return pass(`verdict covers ${headSha}`);
  return patchIdOk
    ? pass(
        `verdict Head: ${verdict.record.head} is not the PR head ${headSha}, but the patch is unchanged`
      )
    : fail(
        `verdict covers ${verdict.record.head} but the PR head is ${headSha}`
      );
}

function sameRepository(a: T.Repository, b: T.Repository): boolean {
  const lower = (text: string): string => text.toLowerCase();
  return (
    lower(a.host) === lower(b.host) &&
    lower(a.owner) === lower(b.owner) &&
    lower(a.repo) === lower(b.repo)
  );
}

function patchIdGate(args: {
  readonly verdict: VerdictReading;
  readonly state: T.PullRequestFacts["state"];
  readonly local: PatchId | null;
  readonly base: string;
  readonly headSha: CommitSha | null;
  readonly wrongCheckout: string | null;
}): Outcome {
  if (args.verdict.kind !== "recorded") return fail("no verdict to compare");
  if (args.state !== "OPEN") return fail(`not evaluated: PR is ${args.state}`);
  if (args.wrongCheckout !== null) return fail(args.wrongCheckout);
  if (args.local === null || args.headSha === null)
    return fail("the PR head SHA is unreadable");
  return args.verdict.record.patchId === args.local
    ? pass(`git diff ${args.base}...${args.headSha} has patch-id ${args.local}`)
    : fail(
        `verdict patch-id ${args.verdict.record.patchId} but git diff ${args.base}...${args.headSha} has ${args.local}`
      );
}

function checksGate(row: Extract<T.PrSnapshot, { kind: "open" }>): Outcome {
  const blocker = ciBlocker(row);
  if (blocker?.kind === "failing-checks") {
    const parts =
      blocker.ci.kind === "ci-failing"
        ? [`${plural(blocker.ci.failed.length, "check")} failed: ${names(blocker.ci.failed)}`]
        : [
            `GitHub reports a failing rollup on the head (mergeStateStatus=${blocker.ci.github.mergeStateStatus}, rollup=${blocker.ci.github.headRollupState})`,
          ];
    if (blocker.ci.pending.length > 0)
      parts.push(`${blocker.ci.pending.length} pending: ${names(blocker.ci.pending)}`);
    return fail(parts.join("; "));
  }
  return row.ci.kind === "ci-pending"
    ? fail(`${row.ci.pending.length} pending: ${names(row.ci.pending)}`)
    : pass(`${plural(row.ci.all.length, "check")}, none failed or pending`);
}

const CONNECTION_NOUN: Record<ReviewConnection, string> = {
  reviewThreads: "review threads",
  reviewRequests: "review requests",
  reviews: "reviews",
  comments: "PR comments",
};
function truncationProblems(
  conversation: Conversation,
  connections: readonly ReviewConnection[]
): readonly string[] {
  return conversation.truncated
    .filter((truncation) => connections.includes(truncation.connection))
    .map(
      (truncation) =>
        `more than ${truncation.limit} ${CONNECTION_NOUN[truncation.connection]} (${truncation.total}); cannot verify`
    );
}

function reviewBodiesGate(
  row: Extract<T.PrSnapshot, { kind: "open" }>,
  conversation: Conversation
): Outcome {
  const problems: string[] = [
    ...truncationProblems(conversation, ["reviewRequests", "reviews", "comments"]),
  ];
  const open = findingsBlocker(row);
  if (open?.kind === "review-findings")
    problems.push(
      `${plural(open.reviews.length, "unacknowledged bot review")}: ${open.reviews.map((review) => `${review.bot} ${review.url}`).join(", ")}`
    );
  if (row.pendingReviewBots.length > 0)
    problems.push(`review bot pending: ${row.pendingReviewBots.join(", ")}`);
  const unacknowledged = row.unreadReviews.filter(
    (unread) =>
      acknowledgment(conversation.comments, conversation.prAuthor, unread.url) ===
      undefined
  );
  if (unacknowledged.length > 0)
    problems.push(
      `${plural(unacknowledged.length, "unread bot review body")} with no acknowledgment: ${unacknowledged.map((unread) => `${unread.bot} ${unread.url}`).join(", ")}`
    );
  return problems.length === 0
    ? pass("every bot review body on the head is acknowledged or clean")
    : fail(problems.join("; "));
}

function threadsGate(
  row: Extract<T.PrSnapshot, { kind: "open" }>,
  conversation: Conversation
): Outcome {
  const blocker = threadBlocker(row);
  const problems: string[] = [];
  if (blocker?.kind === "review-threads") {
    const places = blocker.threads.map((thread) =>
      thread.firstComment?.path == null
        ? thread.id
        : `${thread.firstComment.path}:${thread.firstComment.line ?? "?"}`
    );
    problems.push(
      `${plural(blocker.threads.length, "unresolved review thread")}: ${places.join(", ")}`
    );
  }
  problems.push(...truncationProblems(conversation, ["reviewThreads"]));
  return problems.length === 0
    ? pass("no unresolved threads")
    : fail(problems.join("; "));
}

function mergeabilityGate(snapshot: T.PrSnapshot): Outcome {
  if (snapshot.kind !== "open")
    return fail(`PR is ${snapshot.facts.state}, not open`);
  const problems: string[] = [];
  const conflict = conflictBlocker(snapshot);
  if (conflict !== null)
    problems.push(
      `merge conflict (mergeable=${snapshot.facts.mergeable}, mergeStateStatus=${snapshot.facts.mergeStateStatus})`
    );
  else if (snapshot.facts.mergeable !== "MERGEABLE")
    problems.push(
      `GitHub has not computed mergeability (mergeable=${snapshot.facts.mergeable}); rerun`
    );
  if (gateReason(snapshot, true) === "changes-requested")
    problems.push("changes requested by a reviewer");
  if (snapshot.facts.reviewDecision === "REVIEW_REQUIRED")
    problems.push("review required (reviewDecision=REVIEW_REQUIRED)");
  return problems.length === 0 ? pass("mergeable") : fail(problems.join("; "));
}

const draftGate = (isDraft: boolean): Outcome =>
  isDraft ? fail("PR is a draft") : pass("not a draft");

/**
 * On a queue-enabled branch `gh pr merge` only enqueues the PR. The queue
 * reruns required status checks, but it lands the PR later without rechecking
 * the verdict, the bot reviews, or the open threads.
 */
const mergeQueueGate = (base: string, queued: boolean): Outcome =>
  queued
    ? fail(
        `${base} uses a merge queue: gh pr merge would only enqueue the PR, and the queue would land it later without rechecking the verdict, the bot reviews, or the open threads`
      )
    : pass(`${base} has no merge queue`);

export async function evaluateGates(args: {
  readonly reader: T.GitHubReader;
  readonly port: MergePort;
  readonly context: T.PrContext;
}): Promise<GateReport> {
  const snapshot = await readSnapshot({
    reader: args.reader,
    context: args.context,
    pendingHistory: "include",
    allowDraft: false,
  });
  const conversation = await args.port.conversation(args.context);
  const verdict = latestVerdict(conversation.comments, conversation.prAuthor);
  const { facts } = snapshot;
  const headSha = parseCommitSha(facts.headRefOid);
  const wantsPatchId =
    snapshot.kind === "open" && headSha !== null && verdict.kind === "recorded";
  const origin = wantsPatchId ? await args.reader.originRepo() : null;
  const wrongCheckout = !wantsPatchId
    ? null
    : origin === null
      ? `cwd has no origin remote; run merge-gate from a checkout of ${repoLabel(args.context)}`
      : sameRepository(origin, args.context)
        ? null
        : `cwd repository ${repoLabel(origin)} is not the PR's ${repoLabel(args.context)}; run merge-gate from a checkout of ${repoLabel(args.context)}`;
  const localPatchId =
    wantsPatchId && wrongCheckout === null
      ? await args.port.patchId(facts.baseRefName, headSha)
      : null;
  const notEvaluated = fail(`not evaluated: PR is ${facts.state}`);
  const open = snapshot.kind === "open" ? snapshot : null;
  const queued =
    open === null
      ? null
      : await args.port.usesMergeQueue(args.context, facts.baseRefName);
  const patchIdOutcome = patchIdGate({
    verdict,
    state: facts.state,
    local: localPatchId,
    base: facts.baseRefName,
    headSha,
    wrongCheckout,
  });
  const outcomes: Record<Gate, Outcome> = {
    verdict: verdictGate(verdict),
    head: headGate(verdict, headSha, patchIdOutcome.ok),
    "patch-id": patchIdOutcome,
    checks: open === null ? notEvaluated : checksGate(open),
    "review-bodies":
      open === null ? notEvaluated : reviewBodiesGate(open, conversation),
    threads: open === null ? notEvaluated : threadsGate(open, conversation),
    mergeability: mergeabilityGate(snapshot),
    draft: draftGate(facts.isDraft),
    "merge-queue":
      queued === null ? notEvaluated : mergeQueueGate(facts.baseRefName, queued),
  };
  const gates = GATES.map((gate) => ({ gate, ...outcomes[gate] }));
  return {
    pr: args.context,
    state: facts.state,
    headSha,
    localPatchId,
    verdict,
    gates,
    ready: gates.every((result) => result.ok),
  };
}

export type MergeAction =
  | { readonly kind: "check" }
  | {
      readonly kind: "merge";
      readonly subject: string;
      readonly bodyFile: string;
      readonly override: string | null;
    };

export interface MergeReceiptLine {
  readonly pr: number;
  readonly mergeCommit: string | null;
  readonly head: CommitSha;
  readonly patchId: PatchId | null;
  readonly verdictUrl: string | null;
}

export type MergeGateResult =
  | { readonly kind: "CHECK"; readonly report: GateReport }
  | {
      readonly kind: "REFUSED";
      readonly report: GateReport;
      readonly note: string | null;
    }
  | {
      readonly kind: "MERGED";
      readonly report: GateReport;
      readonly receipt: MergeReceiptLine;
      readonly override: string | null;
    }
  | {
      readonly kind: "QUEUED";
      readonly report: GateReport;
      readonly receipt: MergeReceiptLine;
      readonly override: string | null;
      readonly note: string;
    }
  | {
      readonly kind: "ERROR";
      readonly source: "github" | "git" | "gh";
      readonly detail: string;
    };

export const EXIT_NOT_READY = 10;
export const EXIT_QUEUED = 11;
export function exitCodeOf(result: MergeGateResult): 0 | 1 | 10 | 11 {
  switch (result.kind) {
    case "CHECK":
      return result.report.ready ? 0 : EXIT_NOT_READY;
    case "MERGED":
      return 0;
    case "REFUSED":
      return EXIT_NOT_READY;
    case "QUEUED":
      return EXIT_QUEUED;
    case "ERROR":
      return 1;
    default: {
      const exhaustive: never = result;
      return exhaustive;
    }
  }
}

export function overrideComment(
  reason: string,
  gates: readonly GateResult[]
): string {
  const failed = gates.filter((result) => !result.ok);
  return [
    `merge-gate override: ${reason}`,
    "",
    "Failed gates:",
    ...failed.map((result) => `- ${result.gate}: ${result.detail}`),
  ].join("\n");
}

export async function runMergeGate(args: {
  readonly reader: T.GitHubReader;
  readonly port: MergePort;
  readonly context: T.PrContext;
  readonly action: MergeAction;
}): Promise<MergeGateResult> {
  const report = await evaluateGates(args);
  const { action } = args;
  if (action.kind === "check") return { kind: "CHECK", report };
  const refuse = (note: string): MergeGateResult => ({
    kind: "REFUSED",
    report,
    note,
  });
  if (report.headSha === null)
    return refuse("refused: the PR head SHA is unreadable, so the merge cannot be pinned");
  if (!report.ready) {
    if (action.override === null) return { kind: "REFUSED", report, note: null };
    if (report.state !== "OPEN")
      return refuse(`override refused: PR is ${report.state}`);
    await args.port.comment(
      args.context,
      overrideComment(action.override, report.gates)
    );
  }
  const merged = await args.port.merge({
    context: args.context,
    headSha: report.headSha,
    subject: action.subject,
    bodyFile: action.bodyFile,
  });
  const receipt: MergeReceiptLine = {
    pr: args.context.number,
    mergeCommit: merged.mergeCommit,
    head: report.headSha,
    patchId: report.localPatchId,
    verdictUrl:
      report.verdict.kind === "recorded" ? report.verdict.record.url : null,
  };
  const override = report.ready ? null : action.override;
  return merged.kind === "merged"
    ? { kind: "MERGED", report, receipt, override }
    : {
        kind: "QUEUED",
        report,
        receipt,
        override,
        note: `PR is not merged yet (${merged.observed})`,
      };
}
