import { describe, expect, it } from "bun:test";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { HEAD, PATCH, verdictBody } from "./merge-gate-fakes.test-helper.ts";

const SOURCE_DIR = join(import.meta.dir, "../../../../../skills/poteto-mode/scripts/watch-pr");

function evaluate(
  late: "resolved" | "unresolved" | "failed",
  incomplete?: { readonly connection: "contexts" | "reviewThreads"; readonly cursor: string | null; readonly entry: "watcher" | "merge-check" }
): {
  readonly result: { exitCode?: number; output?: string; ready?: boolean; failed?: readonly string[]; threads?: string; error?: string };
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
    if (incomplete?.connection === "reviewThreads") {
      fixtures.first.data.repository.pullRequest.reviewThreads.pageInfo.endCursor = incomplete.cursor;
    }
    const rollup = { data: { repository: { pullRequest: { commits: { nodes: [{ commit: {
      statusCheckRollup: { contexts: { nodes: [], pageInfo: { hasNextPage: true, endCursor: incomplete?.cursor } } },
    } }] } } } } };
    writeFileSync(join(directory, "fixtures.json"), JSON.stringify({ ...fixtures, rollup }));
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
else if (args[0] === "pr" && args[1] === "checks") result = ${incomplete?.connection === "contexts" ? "[]" : '[{ name: "tests", state: "SUCCESS", bucket: "pass", link: "https://ci.example/check", description: "passed", workflow: "test" }]' };
else if (query.includes("query PrCheckRollup")) result = fixtures.rollup;
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
    const cliScript = `import { GhGitHubReader } from ${JSON.stringify(join(SOURCE_DIR, "github.ts"))};
import { GhGitMergePort } from ${JSON.stringify(join(SOURCE_DIR, "merge-effects.ts"))};
import { main } from ${JSON.stringify(join(SOURCE_DIR, incomplete?.entry === "watcher" ? "cli.ts" : "merge-gate-cli.ts"))};
const output = [];
const concrete = new GhGitMergePort();
const runtime = {
  reader: new GhGitHubReader(),
  port: { conversation: concrete.conversation.bind(concrete), usesMergeQueue: concrete.usesMergeQueue.bind(concrete), patchId: async () => ${JSON.stringify(PATCH)} },
  clock: { now: () => 0, observedAt: () => "2026-10-02T12:00:00Z", sleep: async () => { throw new Error("unexpected retry"); } },
  bodyFileReadable: () => false,
  stdout: value => output.push(value), stderr: value => output.push(value),
};
const exitCode = await main(["--owner", "owner", "--repo", "repo", "--pr", "1", ...${JSON.stringify(incomplete?.entry === "watcher" ? ["--max-query-errors", "1"] : ["--check"])}], runtime);
console.log(JSON.stringify({ exitCode, output: output.join("") }));`;
    const spawned = Bun.spawnSync([process.execPath, "-e", incomplete ? cliScript : script], { cwd: directory, env: { ...process.env, GH_HOST: "example.invalid", PATH: `${directory}:${process.env.PATH ?? ""}` } });
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
  for (const entry of ["watcher", "merge-check"] as const) {
    for (const connection of ["contexts", "reviewThreads"] as const) {
      for (const cursor of [null, ""]) {
        it(`${entry} refuses synthetic ${connection} hasNextPage=true plus endCursor=${JSON.stringify(cursor)}`, () => {
          const { result, queries } = evaluate("resolved", { connection, cursor, entry });
          expect(result.exitCode).toBe(entry === "watcher" ? 7 : 1);
          expect(result.output).toContain(`${connection}.pageInfo.endCursor`);
          expect(JSON.parse(result.output ?? "")).toMatchObject(entry === "watcher"
            ? { kind: "BLOCKER", exitCode: 7, blocker: { kind: "status-query" } }
            : { kind: "ERROR", source: "github" });
          expect(queries.some(query => query.includes(connection === "contexts" ? "PrCheckRollup" : "ReviewThreads"))).toBe(true);
        });
      }
    }
  }

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
