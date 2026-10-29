import type * as T from "./types.ts";
import { nonEmpty } from "./types.ts";

export interface SubmittedReview {
  readonly id: T.ReviewId;
  readonly url: string;
  readonly author: { readonly login: string; readonly isBot: boolean };
  readonly commitOid: string | null;
  readonly body: string;
}
const TRUSTED_ASSOCIATIONS = ["OWNER", "MEMBER", "COLLABORATOR"] as const;
export type CommentAssociation =
  | (typeof TRUSTED_ASSOCIATIONS)[number]
  | "untrusted";
export function commentAssociation(text: string): CommentAssociation {
  return TRUSTED_ASSOCIATIONS.find((known) => known === text) ?? "untrusted";
}
export interface ConversationComment {
  readonly url: string;
  readonly author: { readonly login: string; readonly isBot: boolean };
  readonly association: CommentAssociation;
  readonly body: string;
}
export interface ReviewBodyInput {
  readonly headRefOid: string;
  readonly prAuthor: string | null;
  readonly reviews: readonly SubmittedReview[];
  readonly comments: readonly ConversationComment[];
}
interface CountedSection {
  readonly name: string;
  readonly count: number;
  readonly text: string;
  readonly structure: string;
}
const SECTION = /<summary><strong>([^<]*)<\/strong><\/summary>/dg;
const TRAILING_COUNT = /^(.*) \((\d+)\)$/;
const LEADING_COUNT = /^(\d+) (.+)$/;
const RESOLVED = /^resolved\b/i;
const OPEN = /^open\b/i;
const THREAD_LINK = /\]\([^)\s]*#discussion_r\d+\)/;
const NESTED_ITEM =
  /<summary>(?!<strong>)([\s\S]*?)<\/summary>([\s\S]*?)(?=<summary>|$)/dg;
const FENCED_CODE =
  /^ {0,3}(`{3,}(?=[^`\n]*$)|~{3,})[^\n]*(?:\n[\s\S]*?^ {0,3}\1[`~]*[ \t]*$|[\s\S]*)/gm;
const INLINE_CODE = /(?<!`)(`+)(?!`)(?:(?!\n[ \t]*\n)[\s\S])*?(?<!`)\1(?!`)/g;
const blank = (code: string): string => code.replace(/[^\n]/g, " ");
const withoutCode = (markdown: string): string =>
  markdown.replace(FENCED_CODE, blank).replace(INLINE_CODE, blank);
function group(match: RegExpExecArray, index: number, text: string): string {
  const span = match.indices?.[index];
  return span === undefined ? "" : text.slice(...span);
}
function countOf(heading: string): { name: string; count: number } | null {
  const trailing = TRAILING_COUNT.exec(heading);
  if (trailing !== null)
    return { name: trailing[1], count: Number(trailing[2]) };
  const leading = LEADING_COUNT.exec(heading);
  return leading === null
    ? null
    : { name: leading[2], count: Number(leading[1]) };
}
function stripTags(html: string): string {
  let text = html;
  for (let previous = ""; previous !== text; ) {
    previous = text;
    text = text
      .replace(/<picture>[\s\S]*?<\/picture>/g, "")
      .replace(/<\/?[A-Za-z][^>]*>/g, "");
  }
  return text.replace(/<(?=[A-Za-z/])/g, "").trim();
}

const MAX_PADDED_FINDINGS = 20;
function countedSections(body: string): readonly CountedSection[] {
  const structure = withoutCode(body);
  const heads = [...structure.matchAll(SECTION)];
  return heads.flatMap((head, index) => {
    const counted = countOf(group(head, 1, body).trim());
    if (counted === null) return [];
    const start = head.index + head[0].length;
    const end = heads[index + 1]?.index ?? body.length;
    return [
      {
        ...counted,
        text: body.slice(start, end),
        structure: structure.slice(start, end),
      },
    ];
  });
}
function threadlessOpenItems(section: CountedSection): readonly T.BodyFinding[] {
  const raw = section.text.split("\n");
  const lines = section.structure
    .split("\n")
    .flatMap((line, index) =>
      line.startsWith("- ") ? [{ line, text: raw[index] }] : []
    );
  const loose = lines
    .filter(({ line }) => !THREAD_LINK.test(line))
    .map(({ text }) => ({
      section: section.name,
      title: stripTags(text.slice(2)),
      location: null,
    }));
  const unparsed = Array.from(
    {
      length: Math.max(
        0,
        Math.min(section.count, MAX_PADDED_FINDINGS) - lines.length
      ),
    },
    () => ({ section: section.name, title: "(unparsed)", location: null })
  );
  return [...loose, ...unparsed];
}
function threadlessSectionItems(
  section: CountedSection
): readonly T.BodyFinding[] {
  const items = [...section.structure.matchAll(NESTED_ITEM)];
  return Array.from(
    { length: Math.max(Math.min(section.count, MAX_PADDED_FINDINGS), items.length) },
    (_, index) => {
      const item = items[index];
      if (item === undefined)
        return { section: section.name, title: "(unparsed)", location: null };
      return {
        section: section.name,
        title: stripTags(group(item, 1, section.text)),
        location:
          /`([^`\n]+:\d+)`/
            .exec(group(item, 2, section.text))?.[1]
            ?.replace(/\u200b/g, "") ?? null,
      };
    }
  );
}

const threadlessFindings = (body: string): readonly T.BodyFinding[] =>
  countedSections(body).flatMap((section) => {
    if (RESOLVED.test(section.name) || section.count === 0)
      return [];
    return OPEN.test(section.name)
      ? threadlessOpenItems(section)
      : threadlessSectionItems(section);
  });

export function reviewIdFromUrl(url: string): T.ReviewId | null {
  const digits = /#pullrequestreview-(\d+)$/.exec(url)?.[1];
  return digits === undefined ? null : (digits as T.ReviewId);
}
function linksReview(body: string, reviewUrl: string): boolean {
  for (let from = body.indexOf(reviewUrl); from !== -1; ) {
    const next = body[from + reviewUrl.length];
    if (next === undefined || !/\d/.test(next)) return true;
    from = body.indexOf(reviewUrl, from + 1);
  }
  return false;
}
export const isTrustedComment = (
  comment: ConversationComment,
  prAuthor: string | null
): boolean =>
  !comment.author.isBot &&
  (comment.author.login === prAuthor || comment.association !== "untrusted");
const RECAP_START = "<!-- pstack-recap:start -->";
function acknowledgment(
  comments: readonly ConversationComment[],
  prAuthor: string | null,
  reviewUrl: string
): { author: string; url: string } | undefined {
  const comment = comments.find(
    (candidate) =>
      isTrustedComment(candidate, prAuthor) &&
      !candidate.body.trimStart().startsWith(RECAP_START) &&
      linksReview(candidate.body, reviewUrl)
  );
  return comment === undefined
    ? undefined
    : { author: comment.author.login, url: comment.url };
}
const isHeadBotReview = (
  review: SubmittedReview,
  headRefOid: string
): boolean => review.author.isBot && review.commitOid === headRefOid;

export function flagReviewBodies(
  input: ReviewBodyInput
): readonly T.FlaggedReview[] {
  const flagged: T.FlaggedReview[] = [];
  for (const review of input.reviews) {
    if (!isHeadBotReview(review, input.headRefOid)) continue;
    const findings = nonEmpty(threadlessFindings(review.body));
    if (findings === null) continue;
    const base = {
      id: review.id,
      url: review.url,
      bot: review.author.login,
      commitOid: input.headRefOid,
      findings,
    };
    const ack = acknowledgment(input.comments, input.prAuthor, review.url);
    flagged.push(
      ack === undefined
        ? { ...base, status: "open" }
        : { ...base, status: "acknowledged", ack }
    );
  }
  return flagged;
}
