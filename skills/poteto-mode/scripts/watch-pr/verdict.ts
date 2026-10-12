import { isTrustedComment, type ConversationComment } from "./review-bodies.ts";
import type { NonEmpty } from "./types.ts";
import { nonEmpty } from "./types.ts";

declare const commitShaBrand: unique symbol;
export type CommitSha = string & { readonly [commitShaBrand]: "CommitSha" };
declare const patchIdBrand: unique symbol;
export type PatchId = string & { readonly [patchIdBrand]: "PatchId" };

const HEX_40 = /^[0-9a-f]{40}$/;
export const parseCommitSha = (text: string | null): CommitSha | null =>
  text !== null && HEX_40.test(text) ? (text as CommitSha) : null;
export const parsePatchId = (text: string | null): PatchId | null =>
  text !== null && HEX_40.test(text) ? (text as PatchId) : null;

export const VERDICTS = ["PASS", "PASS+NOTES", "FAIL"] as const;
export type VerdictWord = (typeof VERDICTS)[number];
export const DOCS_STATUSES = [
  "pass",
  "needs changes",
  "unverified",
  "n/a",
] as const;
export type DocsStatus = (typeof DOCS_STATUSES)[number];

/** A PR issue comment, with the timestamp the verdict ordering needs. */
export interface IssueComment extends ConversationComment {
  readonly createdAt: string;
}

export interface VerdictRecord {
  readonly verdict: VerdictWord;
  readonly head: CommitSha;
  readonly patchId: PatchId;
  readonly docs: DocsStatus;
  readonly url: string;
  readonly createdAt: string;
  readonly author: string;
}

/**
 * What the latest verdict comment says. A comment that opens a verdict claim
 * with a `Verdict:` line but cannot be read as a whole block is `malformed`,
 * not skipped: skipping it would let an older PASS stand behind a newer,
 * broken FAIL.
 */
export type VerdictReading =
  | { readonly kind: "absent" }
  | {
      readonly kind: "malformed";
      readonly url: string;
      readonly author: string;
      readonly problems: NonEmpty<string>;
    }
  | { readonly kind: "recorded"; readonly record: VerdictRecord };

/**
 * Block format. The comment's first four non-empty lines are, in order and
 * with nothing else before them (blank lines may lead):
 *
 *   Verdict: PASS | PASS+NOTES | FAIL
 *   Head: <40 lowercase hex>
 *   Patch-id: <40 lowercase hex>
 *   Docs: pass | needs changes | unverified | n/a
 *
 * Keys are case-sensitive and plain text. Prose may follow the block. A
 * comment whose first non-empty line starts with `Verdict:` claims a verdict
 * and is malformed unless the whole block reads. A block quoted further down
 * a comment is not a claim.
 */
const BLOCK_KEYS = ["Verdict", "Head", "Patch-id", "Docs"] as const;
const VERDICT_PREFIX = "Verdict:";

function enumMember<const V extends readonly string[]>(
  values: V,
  text: string
): V[number] | null {
  return values.find((candidate) => candidate === text) ?? null;
}

type Field<T> =
  | { readonly kind: "ok"; readonly value: T }
  | { readonly kind: "bad"; readonly problem: string };

function field<T>(
  lines: readonly string[],
  position: number,
  parse: (text: string) => T | null
): Field<T> {
  const key = BLOCK_KEYS[position];
  const line = lines[position];
  if (line === undefined)
    return { kind: "bad", problem: `missing "${key}:" line` };
  if (!line.startsWith(`${key}:`))
    return {
      kind: "bad",
      problem: `expected "${key}:" as non-empty line ${position + 1}`,
    };
  const text = line.slice(key.length + 1).trim();
  const value = parse(text);
  return value === null
    ? { kind: "bad", problem: `invalid "${key}:" value "${text}"` }
    : { kind: "ok", value };
}

function readComment(comment: IssueComment): VerdictReading {
  const lines = comment.body.split(/\r?\n/).filter((line) => line.trim() !== "");
  if (lines[0]?.startsWith(VERDICT_PREFIX) !== true) return { kind: "absent" };
  const verdict = field(lines, 0, (text) => enumMember(VERDICTS, text));
  const head = field(lines, 1, parseCommitSha);
  const patchId = field(lines, 2, parsePatchId);
  const docs = field(lines, 3, (text) => enumMember(DOCS_STATUSES, text));
  if (
    verdict.kind === "ok" &&
    head.kind === "ok" &&
    patchId.kind === "ok" &&
    docs.kind === "ok"
  )
    return {
      kind: "recorded",
      record: {
        verdict: verdict.value,
        head: head.value,
        patchId: patchId.value,
        docs: docs.value,
        url: comment.url,
        createdAt: comment.createdAt,
        author: comment.author.login,
      },
    };
  const problems = nonEmpty(
    [verdict, head, patchId, docs].flatMap((part) =>
      part.kind === "bad" ? [part.problem] : []
    )
  );
  return problems === null
    ? { kind: "absent" }
    : {
        kind: "malformed",
        url: comment.url,
        author: comment.author.login,
        problems,
      };
}

/**
 * The latest trusted comment that claims a verdict wins, readable or not.
 * Trust is the acknowledgment rule: the PR author, or an OWNER, MEMBER or
 * COLLABORATOR. Every other comment is ignored whole.
 */
export function latestVerdict(
  comments: readonly IssueComment[],
  prAuthor: string | null
): VerdictReading {
  let latest: { at: number; reading: VerdictReading } | null = null;
  for (const comment of comments) {
    if (!isTrustedComment(comment, prAuthor)) continue;
    const reading = readComment(comment);
    if (reading.kind === "absent") continue;
    const at = Date.parse(comment.createdAt);
    if (latest === null || at >= latest.at) latest = { at, reading };
  }
  return latest === null ? { kind: "absent" } : latest.reading;
}

const RESET_PREFIX = "Fail-count reset:";
const STOPPED_PREFIX = "Stopped:";
const SECURITY_ASK_LINE = "Security ask: open";
const FAIL_ROUND_LIMIT = 3;

type RoundEvent =
  | { readonly kind: "reset"; readonly at: number }
  | { readonly kind: "stopped"; readonly at: number }
  | { readonly kind: "fail"; readonly at: number; readonly round: string };
const TIE_ORDER = { reset: 0, stopped: 1, fail: 2 } as const;

type FailRoundState = "open" | "stop" | "stopped";
export interface FailRounds {
  readonly count: number;
  readonly state: FailRoundState;
}

/**
 * Any trusted `Verdict:` claim whose word is not PASS or PASS+NOTES is a FAIL
 * round, malformed or not, so a slipped block cannot keep the stop open. Its
 * round is its Head when that parses, and the comment itself otherwise.
 */
function roundEvent(comment: IssueComment): RoundEvent | null {
  const at = Date.parse(comment.createdAt);
  const lines = comment.body.split(/\r?\n/).filter((line) => line.trim() !== "");
  const first = lines[0];
  if (
    first?.startsWith(RESET_PREFIX) === true &&
    first.slice(RESET_PREFIX.length).trim() !== ""
  )
    return { kind: "reset", at };
  if (first?.startsWith(STOPPED_PREFIX) === true) return { kind: "stopped", at };
  if (first?.startsWith(VERDICT_PREFIX) !== true) return null;
  const word = first.slice(VERDICT_PREFIX.length).trim();
  if (word === "PASS" || word === "PASS+NOTES") return null;
  if (lines.some((line) => line.trim() === SECURITY_ASK_LINE)) return null;
  const head = field(lines, 1, parseCommitSha);
  return { kind: "fail", at, round: head.kind === "ok" ? head.value : comment.url };
}

export function failRounds(
  comments: readonly IssueComment[],
  prAuthor: string | null
): FailRounds {
  const events = comments
    .filter((comment) => isTrustedComment(comment, prAuthor))
    .flatMap((comment) => roundEvent(comment) ?? [])
    .sort((a, b) => a.at - b.at || TIE_ORDER[a.kind] - TIE_ORDER[b.kind]);
  const rounds = new Set<string>();
  let phase: FailRoundState | "granted" = "open";
  for (const event of events) {
    if (event.kind === "reset") phase = "granted";
    else if (event.kind === "stopped") phase = "stopped";
    else {
      rounds.add(event.round);
      if (phase !== "open" || rounds.size >= FAIL_ROUND_LIMIT) phase = "stop";
    }
  }
  return { count: rounds.size, state: phase === "granted" ? "open" : phase };
}
