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
 * Block format, all four lines at the start of a line, one of each, plain
 * text (no markdown decoration, no code fence needed or tolerated):
 *
 *   Verdict: PASS | PASS+NOTES | FAIL
 *   Head: <40 lowercase hex>
 *   Patch-id: <40 lowercase hex>
 *   Docs: pass | needs changes | unverified | n/a
 *
 * Keys are case-sensitive. Surrounding prose in the comment is ignored.
 */
function lineValues(lines: readonly string[], key: string): readonly string[] {
  const prefix = `${key}:`;
  return lines
    .filter((line) => line.startsWith(prefix))
    .map((line) => line.slice(prefix.length).trim());
}

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
  key: string,
  parse: (text: string) => T | null
): Field<T> {
  const found = lineValues(lines, key);
  const first = found[0];
  if (first === undefined)
    return { kind: "bad", problem: `missing "${key}:" line` };
  if (found.length > 1)
    return { kind: "bad", problem: `"${key}:" appears ${found.length} times` };
  const value = parse(first);
  return value === null
    ? { kind: "bad", problem: `invalid "${key}:" value "${first}"` }
    : { kind: "ok", value };
}

function readComment(comment: IssueComment): VerdictReading {
  const lines = comment.body.split(/\r?\n/);
  if (lineValues(lines, "Verdict").length === 0) return { kind: "absent" };
  const verdict = field(lines, "Verdict", (text) => enumMember(VERDICTS, text));
  const head = field(lines, "Head", parseCommitSha);
  const patchId = field(lines, "Patch-id", parsePatchId);
  const docs = field(lines, "Docs", (text) => enumMember(DOCS_STATUSES, text));
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
