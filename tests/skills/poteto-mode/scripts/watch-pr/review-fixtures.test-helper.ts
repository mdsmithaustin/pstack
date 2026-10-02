import { readFileSync } from "node:fs";
import { join } from "node:path";

export interface RestReview {
  readonly id: number;
  readonly user: { readonly login: string; readonly type: string };
  readonly body: string;
  readonly commit_id: string;
  readonly state: string;
  readonly html_url: string;
}
export interface RestComment {
  readonly html_url: string;
  readonly author_association: string;
  readonly user: { readonly login: string; readonly type: string };
  readonly body: string;
}

export const HEADS = {
  104: "211594515de11ac3849329d1f9f8de87fee3b72a",
  107: "5bb33dccdd0b56b11dc87cec527c0d05144b7a23",
  108: "3e3260b7d4b7b93caf3f5d3990335a69ba94f9ba",
} as const;

export function restReviews(pr: keyof typeof HEADS): readonly RestReview[] {
  const rows: RestReview[] = JSON.parse(
    readFileSync(join(import.meta.dir, "fixtures", `reviews-${pr}.json`), "utf8")
  );
  return rows;
}
export function realAckComment(): RestComment {
  const comment: RestComment = JSON.parse(
    readFileSync(join(import.meta.dir, "fixtures", "comment-108-ack.json"), "utf8")
  );
  return comment;
}

/** GraphQL logins carry no `[bot]` suffix. */
export function reviewNode(rest: RestReview): unknown {
  return {
    url: rest.html_url,
    body: rest.body,
    state: rest.state,
    commit: { oid: rest.commit_id },
    author: {
      login: rest.user.login.replace(/\[bot\]$/, ""),
      __typename: rest.user.type,
    },
  };
}
export function commentNode(rest: RestComment): unknown {
  return {
    url: rest.html_url,
    body: rest.body,
    authorAssociation: rest.author_association,
    author: { login: rest.user.login, __typename: rest.user.type },
  };
}
export function botReview(args: {
  readonly id: number;
  readonly commit: string;
  readonly body: string;
  readonly login?: string;
  readonly state?: string;
}): RestReview {
  return {
    id: args.id,
    user: {
      login: `${args.login ?? "copilot-pull-request-reviewer"}[bot]`,
      type: "Bot",
    },
    body: args.body,
    commit_id: args.commit,
    state: args.state ?? "COMMENTED",
    html_url: `https://github.com/owner/repo/pull/1#pullrequestreview-${args.id}`,
  };
}
export function comment(args: {
  readonly id: number;
  readonly body: string;
  readonly login: string;
  readonly association: string;
  readonly type?: string;
}): RestComment {
  return {
    html_url: `https://github.com/owner/repo/pull/1#issuecomment-${args.id}`,
    author_association: args.association,
    user: { login: args.login, type: args.type ?? "User" },
    body: args.body,
  };
}

export function reviewBodiesResponse(args: {
  readonly headRefOid: string;
  readonly prAuthor?: string | null;
  readonly reviews?: readonly RestReview[];
  readonly comments?: readonly RestComment[];
}): unknown {
  return {
    data: {
      repository: {
        pullRequest: {
          headRefOid: args.headRefOid,
          author:
            args.prAuthor === null
              ? null
              : { login: args.prAuthor ?? "mdsmithaustin" },
          reviewThreads: { nodes: [] },
          reviewRequests: { nodes: [] },
          reviews: { nodes: (args.reviews ?? []).map(reviewNode) },
          comments: { nodes: (args.comments ?? []).map(commentNode) },
        },
      },
    },
  };
}
