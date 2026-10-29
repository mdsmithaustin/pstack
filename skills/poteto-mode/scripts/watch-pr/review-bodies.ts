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
const LIST_MARKER = /^([-*+]|\d{1,9}[.)])(?:( +)(?=[^ ])| *$)/;
const THEMATIC_BREAK = /^([-*_])(?: *\1){2,} *$/;
const HTML_BLOCKS: readonly (readonly [start: RegExp, end: RegExp | "blank"])[] = [
  [/^<(?:pre|script|style|textarea)(?:[ \t>]|$)/i, /<\/(?:pre|script|style|textarea)>/i],
  [/^<!--/, /-->/],
  [/^<\?/, /\?>/],
  [/^<![A-Za-z]/, />/],
  [/^<!\[CDATA\[/, /\]\]>/],
  [
    /^<\/?(?:address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul)(?:[ \t>]|\/>|$)/i,
    "blank",
  ],
];
const LONE_TAG =
  /^(?:<[A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z_:][\w.:-]*(?:\s*=\s*(?:[^\s"'=<>`]+|'[^']*'|"[^"]*"))?)*\s*\/?>|<\/[A-Za-z][A-Za-z0-9-]*\s*>)\s*$/;
const ATX_HEADING = /^#{1,6}(?: |$)/;
const FENCE_OPENER = /^(?:`{3,}(?=[^`]*$)|~{3,})/;
const INLINE_CODE = /(?<!`)(?<=(?:^|[^\\])(?:\\\\)*)(`+)(?!`).*?(?<!`)\1(?!`)/g;
const blank = (code: string): string => code.replace(/[^\n]/g, " ");
function expandTabs(line: string): string {
  let text = "";
  for (const char of line) text += char === "\t" ? " ".repeat(4 - (text.length % 4)) : char;
  return text;
}
function htmlBlockEnd(rest: string): RegExp | "blank" | null {
  const block = HTML_BLOCKS.find(([start]) => start.test(rest));
  if (block !== undefined) return block[1];
  return LONE_TAG.test(rest) ? "blank" : null;
}
function interruptsParagraph(rest: string, lazy: boolean): boolean {
  const marker = LIST_MARKER.exec(rest);
  if (marker !== null)
    return lazy || (marker[2] !== undefined && /^(?:[-*+]|1[.)])$/.test(marker[1]));
  return (
    HTML_BLOCKS.some(([start]) => start.test(rest)) ||
    [THEMATIC_BREAK, FENCE_OPENER, ATX_HEADING, /^>/].some((block) => block.test(rest))
  );
}
const closesFence = (rest: string, opener: string): boolean => {
  const run = rest.replace(/ +$/, "");
  return run.length >= opener.length && [...run].every((char) => char === opener[0]);
};
function withoutCode(markdown: string): string {
  const items: number[] = [];
  let fence: { readonly opener: string; readonly container: number } | null = null;
  let html: { readonly end: RegExp | "blank"; readonly container: number } | null = null;
  let emptyItem = false;
  let paragraph = false;
  return markdown
    .split("\n")
    .map((line) => {
      const text = expandTabs(line.replace(/\r$/, ""));
      const indent = text.search(/[^ ]|$/);
      if (indent === text.length) {
        if (emptyItem) items.pop();
        if (html?.end === "blank") html = null;
        emptyItem = paragraph = false;
        return line;
      }
      emptyItem = false;
      const container = items.at(-1) ?? 0;
      if (
        paragraph &&
        (indent - container > 3 || !interruptsParagraph(text.slice(indent), indent < container))
      )
        return line.replace(INLINE_CODE, blank);
      while (indent < (items.at(-1) ?? 0)) items.pop();
      if (fence !== null && indent < fence.container) fence = null;
      if (html !== null && indent < html.container) html = null;
      if (fence !== null) {
        if (indent - fence.container <= 3 && closesFence(text.slice(indent), fence.opener))
          fence = null;
        return blank(line);
      }
      if (html !== null) {
        if (html.end !== "blank" && html.end.test(text)) html = null;
        return line;
      }
      if (indent - (items.at(-1) ?? 0) > 3 || THEMATIC_BREAK.test(text.slice(indent))) {
        paragraph = false;
        return line.replace(INLINE_CODE, blank);
      }
      let column = indent;
      for (let marker; (marker = LIST_MARKER.exec(text.slice(column))) !== null; ) {
        const gap = marker[2]?.length ?? 0;
        column += marker[1].length + (gap === 0 || gap > 4 ? 1 : gap);
        items.push(column);
        emptyItem = gap === 0;
      }
      const rest = text.slice(column);
      const end = htmlBlockEnd(rest);
      if (end !== null) {
        html = end === "blank" || !end.test(rest) ? { end, container: items.at(-1) ?? 0 } : null;
        paragraph = false;
        return line;
      }
      const opener = FENCE_OPENER.exec(rest)?.[0];
      paragraph = opener === undefined && /^[^ >]/.test(rest) && !ATX_HEADING.test(rest);
      if (opener === undefined) return line.replace(INLINE_CODE, blank);
      fence = { opener, container: items.at(-1) ?? 0 };
      return blank(line);
    })
    .join("\n");
}
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
