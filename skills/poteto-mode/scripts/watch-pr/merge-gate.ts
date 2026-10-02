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

export interface Conversation {
  readonly prAuthor: string | null;
  readonly comments: readonly IssueComment[];
}
export interface MergeRequest {
  readonly context: T.PrContext;
  readonly headSha: CommitSha;
  readonly subject: string;
  readonly bodyFile: string;
}
export interface MergeReceipt {
  readonly mergeCommit: string | null;
}

/** Every side effect and non-watcher read merge-gate performs. */
export interface MergePort {
  conversation(context: T.PrContext): Promise<Conversation>;
  patchId(baseRef: string, headSha: CommitSha): Promise<PatchId>;
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

function headGate(verdict: VerdictReading, headSha: CommitSha | null): Outcome {
  if (verdict.kind !== "recorded") return fail("no verdict to compare");
  if (headSha === null) return fail("the PR head SHA is unreadable");
  return verdict.record.head === headSha
    ? pass(`verdict covers ${headSha}`)
    : fail(
        `verdict covers ${verdict.record.head} but the PR head is ${headSha}`
      );
}

function patchIdGate(args: {
  readonly verdict: VerdictReading;
  readonly state: T.PullRequestFacts["state"];
  readonly local: PatchId | null;
  readonly base: string;
  readonly headSha: CommitSha | null;
}): Outcome {
  if (args.verdict.kind !== "recorded") return fail("no verdict to compare");
  if (args.state !== "OPEN") return fail(`not evaluated: PR is ${args.state}`);
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

function reviewBodiesGate(
  row: Extract<T.PrSnapshot, { kind: "open" }>,
  conversation: Conversation
): Outcome {
  const problems: string[] = [];
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

function threadsGate(row: Extract<T.PrSnapshot, { kind: "open" }>): Outcome {
  const blocker = threadBlocker(row);
  if (blocker?.kind !== "review-threads") return pass("no unresolved threads");
  const places = blocker.threads.map((thread) =>
    thread.firstComment?.path == null
      ? thread.id
      : `${thread.firstComment.path}:${thread.firstComment.line ?? "?"}`
  );
  return fail(
    `${plural(blocker.threads.length, "unresolved review thread")}: ${places.join(", ")}`
  );
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
  return problems.length === 0 ? pass("mergeable") : fail(problems.join("; "));
}

const draftGate = (isDraft: boolean): Outcome =>
  isDraft ? fail("PR is a draft") : pass("not a draft");

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
  const localPatchId =
    snapshot.kind === "open" && headSha !== null && verdict.kind === "recorded"
      ? await args.port.patchId(facts.baseRefName, headSha)
      : null;
  const notEvaluated = fail(`not evaluated: PR is ${facts.state}`);
  const open = snapshot.kind === "open" ? snapshot : null;
  const outcomes: Record<Gate, Outcome> = {
    verdict: verdictGate(verdict),
    head: headGate(verdict, headSha),
    "patch-id": patchIdGate({
      verdict,
      state: facts.state,
      local: localPatchId,
      base: facts.baseRefName,
      headSha,
    }),
    checks: open === null ? notEvaluated : checksGate(open),
    "review-bodies":
      open === null ? notEvaluated : reviewBodiesGate(open, conversation),
    threads: open === null ? notEvaluated : threadsGate(open),
    mergeability: mergeabilityGate(snapshot),
    draft: draftGate(facts.isDraft),
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
      readonly kind: "ERROR";
      readonly source: "github" | "git" | "gh";
      readonly detail: string;
    };

export const EXIT_NOT_READY = 10;
export function exitCodeOf(result: MergeGateResult): 0 | 1 | 10 {
  switch (result.kind) {
    case "CHECK":
      return result.report.ready ? 0 : EXIT_NOT_READY;
    case "MERGED":
      return 0;
    case "REFUSED":
      return EXIT_NOT_READY;
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
  return {
    kind: "MERGED",
    report,
    override: report.ready ? null : action.override,
    receipt: {
      pr: args.context.number,
      mergeCommit: merged.mergeCommit,
      head: report.headSha,
      patchId: report.localPatchId,
      verdictUrl:
        report.verdict.kind === "recorded" ? report.verdict.record.url : null,
    },
  };
}
