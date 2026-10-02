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
export interface ReviewBodyReport {
  readonly flagged: readonly T.FlaggedReview[];
  readonly unread: readonly T.UnreadReview[];
}

interface BodyFormat {
  readonly name: string;
  readonly failClosedLogins: readonly string[];
  claims(body: string): boolean;
  findings(body: string): readonly T.BodyFinding[];
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

const COPILOT_OVERVIEW_V2 = {
  name: "copilot-overview-v2",
  failClosedLogins: ["copilot-pull-request-reviewer"],
  claims: (body) =>
    body.includes("<!-- ccr-overview-v2 -->") &&
    /\*\*Findings:\*\* (None|\d+)/.test(body) &&
    countedSections(body).every((section) => Number.isFinite(section.count)),
  findings: (body) =>
    countedSections(body).flatMap((section) => {
      if (section.name === "Resolved since last review" || section.count === 0)
        return [];
      return section.name === "Open"
        ? threadlessOpenItems(section)
        : threadlessSectionItems(section);
    }),
} as const satisfies BodyFormat;
const BODY_FORMATS = [COPILOT_OVERVIEW_V2] as const;
export type BodyFormatName = (typeof BODY_FORMATS)[number]["name"];

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
const untrustedExcerptOf = (body: string): string =>
  body.trim().split(/\r?\n/, 1)[0]?.slice(0, 180) ?? "";

type BodyOutcome =
  | { readonly kind: "clean" }
  | { readonly kind: "flagged"; readonly reading: T.BodyReading }
  | { readonly kind: "unread"; readonly untrustedExcerpt: string };

function readBody(login: string, body: string): BodyOutcome {
  if (body.trim() === "") return { kind: "clean" };
  const claimed = BODY_FORMATS.find((format) => format.claims(body));
  if (claimed !== undefined) {
    const findings = nonEmpty(claimed.findings(body));
    return findings === null
      ? { kind: "clean" }
      : {
          kind: "flagged",
          reading: { kind: "findings", format: claimed.name, findings },
        };
  }
  return BODY_FORMATS.some((format) => format.failClosedLogins.some((owned) => owned === login))
    ? {
        kind: "flagged",
        reading: { kind: "unrecognized", untrustedExcerpt: untrustedExcerptOf(body) },
      }
    : { kind: "unread", untrustedExcerpt: untrustedExcerptOf(body) };
}

function acknowledgment(
  comments: readonly ConversationComment[],
  prAuthor: string | null,
  reviewUrl: string
): { author: string; url: string } | undefined {
  const comment = comments.find(
    (candidate) =>
      !candidate.author.isBot &&
      (candidate.author.login === prAuthor ||
        candidate.association !== "untrusted") &&
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

export function flagReviewBodies(input: ReviewBodyInput): ReviewBodyReport {
  const flagged: T.FlaggedReview[] = [];
  const unread: T.UnreadReview[] = [];
  for (const review of input.reviews) {
    if (!isHeadBotReview(review, input.headRefOid)) continue;
    const { id } = review;
    const outcome = readBody(review.author.login, review.body);
    if (outcome.kind === "unread")
      unread.push({
        id,
        url: review.url,
        bot: review.author.login,
        untrustedExcerpt: outcome.untrustedExcerpt,
      });
    if (outcome.kind !== "flagged") continue;
    const base = {
      id,
      url: review.url,
      bot: review.author.login,
      commitOid: input.headRefOid,
      reading: outcome.reading,
    };
    const ack = acknowledgment(input.comments, input.prAuthor, review.url);
    flagged.push(
      ack === undefined
        ? { ...base, status: "open" }
        : { ...base, status: "acknowledged", ack }
    );
  }
  return { flagged, unread };
}
