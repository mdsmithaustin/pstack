import type * as T from "./types.ts";
import { nonEmpty } from "./types.ts";

/** A submitted (not PENDING) review as github.ts validated it. */
export interface SubmittedReview {
  /** From `reviewIdFromUrl(url)`, so the id and the acknowledgment token share one source. */
  readonly id: T.ReviewId;
  readonly url: string;
  readonly author: { readonly login: string; readonly isBot: boolean };
  /** null when GitHub no longer has the reviewed commit. */
  readonly commitOid: string | null;
  readonly body: string;
}
export interface ConversationComment {
  readonly url: string;
  readonly author: { readonly login: string; readonly isBot: boolean };
  /** GitHub's CommentAuthorAssociation as text. An unknown value is untrusted, not an error. */
  readonly association: string;
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

/** One bot's overview grammar. */
interface BodyFormat {
  readonly name: T.BodyFormatName;
  /** Bot logins this format owns: an unrecognized body from one of them blocks. */
  readonly logins: readonly string[];
  claims(body: string): boolean;
  /** Findings no inline thread carries. Empty means clean. */
  findings(body: string): readonly T.BodyFinding[];
}

const SECTION = /<summary><strong>([^<]*)<\/strong><\/summary>/g;
const COUNTED = /^(.*) \((\d+)\)$/;
const THREAD_LINK = /#discussion_r\d+/;
const NESTED_ITEM =
  /<summary>(?!<strong>)([\s\S]*?)<\/summary>([\s\S]*?)(?=<summary>|$)/g;
const stripTags = (html: string): string =>
  html
    .replace(/<picture>[\s\S]*?<\/picture>/g, "")
    .replace(/<[^>]+>/g, "")
    .trim();

/**
 * Copilot's overview lists thread-linked items under "Open" and fixed ones
 * under "Resolved since last review". Every other counted section, such as
 * "Previously missed", has no thread, so each item in it is a finding. A
 * section added later fails closed the same way.
 */
const COPILOT_OVERVIEW_V2: BodyFormat = {
  name: "copilot-overview-v2",
  logins: ["copilot-pull-request-reviewer"],
  claims: (body) => body.includes("<!-- ccr-overview-v2 -->"),
  findings(body) {
    const heads = [...body.matchAll(SECTION)];
    const findings: T.BodyFinding[] = [];
    heads.forEach((head, index) => {
      const counted = COUNTED.exec((head[1] ?? "").trim());
      if (counted === null) return;
      const section = counted[1] ?? "";
      const count = Number(counted[2]);
      if (section === "Resolved since last review" || count === 0) return;
      const start = (head.index ?? 0) + head[0].length;
      const text = body.slice(start, heads[index + 1]?.index ?? body.length);
      if (section === "Open") {
        for (const line of text.split("\n"))
          if (line.startsWith("- ") && !THREAD_LINK.test(line))
            findings.push({
              section,
              title: stripTags(line.slice(2)),
              location: null,
            });
        return;
      }
      const items = [...text.matchAll(NESTED_ITEM)];
      for (let i = 0; i < Math.max(count, items.length); i += 1) {
        const item = items[i];
        const location =
          item === undefined
            ? null
            : (/`([^`\n]+:\d+)`/
                .exec(item[2] ?? "")?.[1]
                ?.replace(/​/g, "") ?? null);
        findings.push({
          section,
          title: item === undefined ? "(unparsed)" : stripTags(item[1] ?? ""),
          location,
        });
      }
    });
    return findings;
  },
};
/** Add an entry, a BodyFormatName literal, and a fixture test per new format. */
const BODY_FORMATS: readonly BodyFormat[] = [COPILOT_OVERVIEW_V2];

/** Associations that mirror who GitHub lets resolve a review thread. */
const TRUSTED_ASSOCIATIONS: ReadonlySet<string> = new Set([
  "OWNER",
  "MEMBER",
  "COLLABORATOR",
]);

export function reviewIdFromUrl(url: string): T.ReviewId | null {
  const digits = /#pullrequestreview-(\d+)$/.exec(url)?.[1];
  return digits === undefined ? null : (digits as T.ReviewId);
}
function linkedReviewIds(text: string): readonly string[] {
  return [...text.matchAll(/#pullrequestreview-(\d+)/g)].map(
    (match) => match[1] ?? ""
  );
}
const excerptOf = (body: string): string =>
  body.trim().split(/\r?\n/, 1)[0]?.slice(0, 180) ?? "";

type BodyOutcome =
  | { readonly kind: "clean" }
  | { readonly kind: "flagged"; readonly reading: T.BodyReading }
  | { readonly kind: "unread"; readonly excerpt: string };

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
  return BODY_FORMATS.some((format) => format.logins.includes(login))
    ? {
        kind: "flagged",
        reading: { kind: "unrecognized", excerpt: excerptOf(body) },
      }
    : { kind: "unread", excerpt: excerptOf(body) };
}

/**
 * Bot reviews of the head commit whose body blocks, each open or
 * acknowledged, plus the head reviews no format can read.
 *
 * Every bot review whose commit is the head counts, not only the latest: a
 * second pass that omits an item does not disprove it. A push moves the head,
 * so older reviews stop counting. A review is acknowledged by a PR comment
 * linking `#pullrequestreview-<id>` from a non-bot who is the PR author or an
 * OWNER, MEMBER, or COLLABORATOR.
 */
export function flagReviewBodies(input: ReviewBodyInput): ReviewBodyReport {
  const acks = new Map<string, { author: string; url: string }>();
  for (const comment of input.comments) {
    if (comment.author.isBot) continue;
    if (
      comment.author.login !== input.prAuthor &&
      !TRUSTED_ASSOCIATIONS.has(comment.association)
    )
      continue;
    for (const id of linkedReviewIds(comment.body))
      if (!acks.has(id))
        acks.set(id, { author: comment.author.login, url: comment.url });
  }
  const flagged: T.FlaggedReview[] = [];
  const unread: T.UnreadReview[] = [];
  for (const review of input.reviews) {
    if (!review.author.isBot || review.commitOid !== input.headRefOid) continue;
    const { id } = review;
    const outcome = readBody(review.author.login, review.body);
    if (outcome.kind === "unread")
      unread.push({
        id,
        url: review.url,
        bot: review.author.login,
        excerpt: outcome.excerpt,
      });
    if (outcome.kind !== "flagged") continue;
    const base = {
      id,
      url: review.url,
      bot: review.author.login,
      commitOid: input.headRefOid,
      reading: outcome.reading,
    };
    const ack = acks.get(id);
    flagged.push(
      ack === undefined
        ? { ...base, status: "open" }
        : { ...base, status: "acknowledged", ack }
    );
  }
  return { flagged, unread };
}
