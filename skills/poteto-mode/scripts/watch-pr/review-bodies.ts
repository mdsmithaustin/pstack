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
}
const SECTION = /<summary><strong>([^<]*)<\/strong><\/summary>/g;
const COUNTED = /^(.*) \((\d+)\)$/;
const THREAD_LINK = /\]\([^)\s]*#discussion_r\d+\)/;
const NESTED_ITEM =
  /<summary>(?!<strong>)([\s\S]*?)<\/summary>([\s\S]*?)(?=<summary>|$)/g;
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
  const heads = [...body.matchAll(SECTION)];
  return heads.flatMap((head, index) => {
    const counted = COUNTED.exec((head[1] ?? "").trim());
    if (counted === null) return [];
    const start = (head.index ?? 0) + head[0].length;
    return [
      {
        name: counted[1] ?? "",
        count: Number(counted[2]),
        text: body.slice(start, heads[index + 1]?.index ?? body.length),
      },
    ];
  });
}
function threadlessOpenItems(section: CountedSection): readonly T.BodyFinding[] {
  const lines = section.text.split("\n").filter((line) => line.startsWith("- "));
  const loose = lines
    .filter((line) => !THREAD_LINK.test(line))
    .map((line) => ({
      section: section.name,
      title: stripTags(line.slice(2)),
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
  const items = [...section.text.matchAll(NESTED_ITEM)];
  return Array.from(
    { length: Math.max(Math.min(section.count, MAX_PADDED_FINDINGS), items.length) },
    (_, index) => {
      const item = items[index];
      if (item === undefined)
        return { section: section.name, title: "(unparsed)", location: null };
      return {
        section: section.name,
        title: stripTags(item[1] ?? ""),
        location:
          /`([^`\n]+:\d+)`/.exec(item[2] ?? "")?.[1]?.replace(/\u200b/g, "") ??
          null,
      };
    }
  );
}

const threadlessFindings = (body: string): readonly T.BodyFinding[] =>
  countedSections(body).flatMap((section) => {
    if (section.name === "Resolved since last review" || section.count === 0)
      return [];
    return section.name === "Open"
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
