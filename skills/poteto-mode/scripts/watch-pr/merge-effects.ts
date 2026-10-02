import {
  MergeGateError,
  type Conversation,
  type MergePort,
  type MergeReceipt,
  type MergeRequest,
} from "./merge-gate.ts";
import {
  at,
  graphqlArgs,
  list,
  optionalString,
  parseAccount,
  record,
  repoArg,
  run,
  runJson,
  string,
  type CommandResult,
} from "./github.ts";
import { commentAssociation } from "./review-bodies.ts";
import type * as T from "./types.ts";
import { parsePatchId, type CommitSha, type IssueComment, type PatchId } from "./verdict.ts";

export const CONVERSATION_QUERY =
  "\nquery MergeGateConversation($owner: String!, $repo: String!, $pr: Int!) {\n  repository(owner: $owner, name: $repo) {\n    pullRequest(number: $pr) {\n      author { login }\n      comments(last: 100) {\n        nodes {\n          body\n          url\n          createdAt\n          authorAssociation\n          author { login __typename }\n        }\n      }\n    }\n  }\n}\n";

const firstLine = (value: string): string =>
  value.trim().split(/\r?\n/, 1)[0]?.slice(0, 240) ?? "";

async function exec(
  source: "git" | "gh",
  argv: readonly [string, ...string[]],
  input?: string
): Promise<CommandResult> {
  try {
    return await run(argv, input);
  } catch (error) {
    throw new MergeGateError(
      source,
      `${argv.slice(0, 3).join(" ")} could not start: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}

export function parseConversation(value: unknown): Conversation {
  const pullRequest = record(
    at(value, ["data", "repository", "pullRequest"]),
    "pullRequest"
  );
  const author = at(pullRequest, ["author"]);
  const comments = list(
    at(pullRequest, ["comments", "nodes"]),
    "comments.nodes"
  ).flatMap((node, index): readonly IssueComment[] => {
    const path = `comments.nodes[${index}]`;
    const fields = record(node, path);
    const account = parseAccount(at(fields, ["author"]), `${path}.author`);
    if (account === null) return [];
    return [
      {
        url: string(fields.url, `${path}.url`),
        createdAt: string(fields.createdAt, `${path}.createdAt`),
        author: account,
        association: commentAssociation(
          string(fields.authorAssociation, `${path}.authorAssociation`)
        ),
        body: string(fields.body, `${path}.body`),
      },
    ];
  });
  return {
    prAuthor:
      author === null
        ? null
        : optionalString(
            record(author, "pullRequest.author").login,
            "pullRequest.author.login"
          ),
    comments,
  };
}

export class GhGitMergePort implements MergePort {
  async conversation(context: T.PrContext): Promise<Conversation> {
    return parseConversation(
      await runJson(graphqlArgs(CONVERSATION_QUERY, context))
    );
  }

  /**
   * Stable patch-id of `git diff <base>...<head>` in the cwd repo. The base
   * is read back from FETCH_HEAD, whose first entry is the first ref named on
   * the fetch, so it is the freshly fetched base even when no remote-tracking
   * ref was updated.
   */
  async patchId(baseRef: string, headSha: CommitSha): Promise<PatchId> {
    const fetch = await exec("git", ["git", "fetch", "origin", baseRef, headSha]);
    if (fetch.code !== 0)
      throw new MergeGateError(
        "git",
        `git fetch origin ${baseRef} ${headSha} failed: ${firstLine(fetch.stderr)}`
      );
    const base = await exec("git", [
      "git",
      "rev-parse",
      "--verify",
      "FETCH_HEAD^{commit}",
    ]);
    const baseOid = base.stdout.trim();
    if (base.code !== 0 || baseOid === "")
      throw new MergeGateError(
        "git",
        `could not resolve fetched ${baseRef}: ${firstLine(base.stderr)}`
      );
    const diff = await exec("git", [
      "git",
      "diff",
      "--no-ext-diff",
      "--no-color",
      `${baseOid}...${headSha}`,
    ]);
    if (diff.code !== 0)
      throw new MergeGateError(
        "git",
        `git diff ${baseOid}...${headSha} failed: ${firstLine(diff.stderr)}`
      );
    const hashed = await exec("git", ["git", "patch-id", "--stable"], diff.stdout);
    const id = parsePatchId(hashed.stdout.trim().split(/\s+/, 1)[0] ?? null);
    if (hashed.code !== 0 || id === null)
      throw new MergeGateError(
        "git",
        `git patch-id --stable produced no patch-id for ${baseRef}...${headSha}: ${firstLine(hashed.stderr) || "empty diff"}`
      );
    return id;
  }

  async merge(request: MergeRequest): Promise<MergeReceipt> {
    const merged = await exec("gh", [
      "gh",
      "pr",
      "merge",
      String(request.context.number),
      "--repo",
      repoArg(request.context),
      "--squash",
      "--match-head-commit",
      request.headSha,
      "--subject",
      request.subject,
      "--body-file",
      request.bodyFile,
    ]);
    if (merged.code !== 0)
      throw new MergeGateError(
        "gh",
        `gh pr merge failed: ${firstLine(merged.stderr) || `exit ${merged.code}`}`
      );
    return { mergeCommit: await this.mergeCommit(request.context) };
  }

  async comment(context: T.PrContext, body: string): Promise<void> {
    const posted = await exec("gh", [
      "gh",
      "pr",
      "comment",
      String(context.number),
      "--repo",
      repoArg(context),
      "--body",
      body,
    ]);
    if (posted.code !== 0)
      throw new MergeGateError(
        "gh",
        `gh pr comment failed: ${firstLine(posted.stderr) || `exit ${posted.code}`}`
      );
  }

  private async mergeCommit(context: T.PrContext): Promise<string | null> {
    try {
      const view = await runJson([
        "gh",
        "pr",
        "view",
        String(context.number),
        "--repo",
        repoArg(context),
        "--json",
        "mergeCommit",
      ]);
      const commit = at(view, ["mergeCommit"]);
      return commit === null
        ? null
        : string(record(commit, "mergeCommit").oid, "mergeCommit.oid");
    } catch {
      return null;
    }
  }
}
