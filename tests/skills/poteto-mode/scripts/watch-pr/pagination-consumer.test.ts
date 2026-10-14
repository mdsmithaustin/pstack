import { describe, expect, it } from "bun:test";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { HEAD, PATCH, verdictBody } from "./merge-gate-fakes.test-helper.ts";

const SOURCE_DIR = join(import.meta.dir, "../../../../../skills/poteto-mode/scripts/watch-pr");

function evaluate(late: "resolved" | "unresolved" | "failed"): {
  readonly result: { ready?: boolean; failed?: readonly string[]; threads?: string; error?: string };
  readonly queries: readonly string[];
} {
  const directory = mkdtempSync(join(tmpdir(), "merge-gate-pages-"));
  try {
    const thread = (id: number, resolved: boolean) => ({
      id: `thread-${id}`, isResolved: resolved,
      comments: { nodes: [{ body: "Please check this", createdAt: "2026-10-02T12:00:00Z", path: "a.ts", line: 1, author: { login: "reviewer", __typename: "User" } }] },
    });
    const response = (nodes: unknown[], hasNextPage: boolean) => ({ data: { repository: { pullRequest: {
      headRefOid: HEAD, author: { login: "mdsmithaustin" },
      reviewThreads: { nodes, pageInfo: { hasNextPage, endCursor: hasNextPage ? "page-2" : null } },
      reviewRequests: { nodes: [] }, reviews: { nodes: [] }, comments: { nodes: [] },
    } } } });
    const conversation = { data: { repository: { pullRequest: {
      author: { login: "mdsmithaustin" },
      reviewRequests: { totalCount: 0 }, reviews: { totalCount: 0 },
      comments: { totalCount: 1, nodes: [{ body: verdictBody(), url: "https://github.com/owner/repo/pull/1#issuecomment-1", createdAt: "2026-10-02T12:00:00Z", authorAssociation: "OWNER", author: { login: "mdsmithaustin", __typename: "User" } }] },
    } } } };
    const fixtures = {
      first: response(Array.from({ length: 100 }, (_, index) => thread(index, true)), true),
      second: response([thread(100, late !== "unresolved")], false),
      conversation,
      facts: { mergeable: "MERGEABLE", mergeStateStatus: "CLEAN", reviewDecision: "APPROVED", headRefOid: HEAD, headRefName: "feature", baseRefName: "main", state: "OPEN", mergedAt: null, isDraft: false },
    };
    writeFileSync(join(directory, "fixtures.json"), JSON.stringify(fixtures));
    writeFileSync(join(directory, "queries"), "");
    writeFileSync(join(directory, "git"), "#!/bin/sh\nprintf '%s\\n' 'https://github.com/owner/repo.git'\n");
    writeFileSync(join(directory, "gh"), `#!${process.execPath}
import { readFileSync, appendFileSync } from "node:fs";
const args = process.argv.slice(2);
const target = args[0] === "api"
  ? args[args.indexOf("--hostname") + 1]
  : args[args.indexOf("--repo") + 1];
if (target !== (args[0] === "api" ? "github.com" : "github.com/owner/repo")) {
  console.error("request reached ambient host"); process.exit(1);
}
const fixtures = JSON.parse(readFileSync(${JSON.stringify(join(directory, "fixtures.json"))}, "utf8"));
const query = args.find(arg => arg.startsWith("query=")) ?? "";
appendFileSync(${JSON.stringify(join(directory, "queries"))}, JSON.stringify(args) + "\\n");
let result;
if (args[0] === "pr" && args[1] === "view") result = fixtures.facts;
else if (args[0] === "pr" && args[1] === "checks") result = [{ name: "tests", state: "SUCCESS", bucket: "pass", link: "https://ci.example/check", description: "passed", workflow: "test" }];
else if (query.includes("query PrCommitStatuses")) result = { data: { repository: { pullRequest: { commits: { nodes: [{ commit: { oid: 'a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1', statusCheckRollup: { state: "SUCCESS" } } }] } } } } };
else if (query.includes("query ReviewThreads")) {
  if (args.includes("after=page-2") && ${JSON.stringify(late)} === "failed") { console.error("HTTP 502 late page"); process.exit(1); }
  result = args.includes("after=page-2") ? fixtures.second : fixtures.first;
} else if (query.includes("query MergeGateConversation")) result = fixtures.conversation;
else if (query.includes("query MergeGateQueue")) result = { data: { repository: { mergeQueue: null } } };
else { console.error("unexpected query"); process.exit(1); }
console.log(JSON.stringify(result));
`);
    chmodSync(join(directory, "git"), 0o755);
    chmodSync(join(directory, "gh"), 0o755);
    const script = `import { GhGitHubReader } from ${JSON.stringify(join(SOURCE_DIR, "github.ts"))};
import { GhGitMergePort } from ${JSON.stringify(join(SOURCE_DIR, "merge-effects.ts"))};
import { evaluateGates } from ${JSON.stringify(join(SOURCE_DIR, "merge-gate.ts"))};
import { parsePrNumber } from ${JSON.stringify(join(SOURCE_DIR, "types.ts"))};
const concrete = new GhGitMergePort();
const port = { conversation: concrete.conversation.bind(concrete), usesMergeQueue: concrete.usesMergeQueue.bind(concrete), patchId: async () => ${JSON.stringify(PATCH)} };
try { const report = await evaluateGates({ reader: new GhGitHubReader(), port, context: { host: "github.com", owner: "owner", repo: "repo", number: parsePrNumber(1) } }); console.log(JSON.stringify({ ready: report.ready, failed: report.gates.filter(gate => !gate.ok).map(gate => gate.gate), threads: report.gates.find(gate => gate.gate === "threads").detail })); }
catch (error) { console.log(JSON.stringify({ error: error.message })); }`;
    const spawned = Bun.spawnSync([process.execPath, "-e", script], { cwd: directory, env: { ...process.env, GH_HOST: "example.invalid", PATH: `${directory}:${process.env.PATH ?? ""}` } });
    if (spawned.exitCode !== 0) throw new Error(new TextDecoder().decode(spawned.stderr));
    return {
      result: JSON.parse(new TextDecoder().decode(spawned.stdout)),
      queries: readFileSync(join(directory, "queries"), "utf8").trimEnd().split("\n"),
    };
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

describe("merge gate with the paginated GitHub reader", () => {
  it("is ready after reading 101 resolved threads across two pages", () => {
    const { result, queries } = evaluate("resolved");
    expect(result).toEqual({ ready: true, failed: [], threads: "no unresolved threads" });
    expect(queries.filter(query => query.includes("after=page-2"))).toHaveLength(1);
  });

  it("blocks an unresolved second-page thread", () => {
    const { result } = evaluate("unresolved");
    expect(result.ready).toBe(false);
    expect(result.failed).toEqual(["threads"]);
    expect(result.threads).toContain("1 unresolved review thread");
  });

  it("refuses readiness when the second-page read fails", () => {
    const { result, queries } = evaluate("failed");
    expect(result).toEqual({ error: "HTTP 502 late page" });
    expect(queries.filter(query => query.includes("after=page-2"))).toHaveLength(1);
  });
});
