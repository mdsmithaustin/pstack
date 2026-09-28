import { describe, expect, it } from "bun:test";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { delimiter, join } from "node:path";

async function readChecks(fixture: {
  code: number;
  stderr: string;
  stdout?: string;
  rollup?: unknown;
}) {
  const directory = await mkdtemp(join(tmpdir(), "watch-pr-gh-"));
  try {
    await writeFile(join(directory, "gh"), `#!${process.execPath}
const fixture = JSON.parse(process.env.WATCH_PR_GH_FIXTURE);
if (process.argv[2] === "pr") {
  process.stdout.write(fixture.stdout ?? "");
  process.stderr.write(fixture.stderr);
  process.exit(fixture.code);
}
process.stdout.write(JSON.stringify(fixture.rollup ?? {
  data: { repository: { pullRequest: { commits: { nodes: [
    { commit: { statusCheckRollup: null } }
  ] } } } }
}));
`, { mode: 0o755 });
    const child = Bun.spawn([
      process.execPath, "-e", `
import { GhGitHubReader, resolveChecks } from "./github.ts";
import { parsePrNumber } from "./types.ts";
try {
  console.log(JSON.stringify(await resolveChecks(new GhGitHubReader(), {
    owner: "owner", repo: "repo", number: parsePrNumber(42)
  })));
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
`,
    ], {
      cwd: import.meta.dir,
      env: {
        ...process.env,
        PATH: `${directory}${delimiter}${process.env.PATH}`,
        WATCH_PR_GH_FIXTURE: JSON.stringify(fixture),
      },
      stdout: "pipe",
      stderr: "pipe",
    });
    const [code, stdout, stderr] = await Promise.all([
      child.exited,
      new Response(child.stdout).text(),
      new Response(child.stderr).text(),
    ]);
    return { code, stdout, stderr };
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

describe("gh check command boundary", () => {
  it("recognizes exit 1 with gh's no-checks diagnostic after a null rollup", async () => {
    const result = await readChecks({
      code: 1,
      stderr: "no checks reported on the 'feature' branch\n",
    });
    expect(result).toEqual({
      code: 0,
      stdout: '{"source":"graphql-rollup","checks":[]}\n',
      stderr: "",
    });
  });

  it("confirms an empty successful JSON response with the rollup", async () => {
    const result = await readChecks({ code: 0, stdout: "[]", stderr: "" });
    expect(result).toEqual({
      code: 0,
      stdout: '{"source":"graphql-rollup","checks":[]}\n',
      stderr: "",
    });
  });

  it("keeps command errors unavailable even when the rollup is empty", async () => {
    for (const fixture of [
      { code: 1, stderr: "HTTP 403: resource not accessible by integration\n" },
      { code: 1, stderr: "HTTP 403\n", stdout: "[]" },
      { code: 1, stderr: "no checks reported on the 'feature' branch\nHTTP 403\n" },
      { code: 8, stderr: "no checks reported on the 'feature' branch\n" },
    ]) {
      const result = await readChecks(fixture);
      expect(result.code).toBe(1);
      expect(result.stderr).toContain("could not read PR checks");
    }
  });

  it("does not prove no checks when the commit is absent", async () => {
    const result = await readChecks({
      code: 1,
      stderr: "no checks reported on the 'feature' branch\n",
      rollup: { data: { repository: { pullRequest: { commits: { nodes: [] } } } } },
    });
    expect(result.code).toBe(1);
    expect(result.stderr).toContain("missing commits.nodes[0]");
  });

  it("does not hide incomplete pagination as an empty rollup", async () => {
    const result = await readChecks({
      code: 1,
      stderr: "no checks reported on the 'feature' branch\n",
      rollup: { data: { repository: { pullRequest: { commits: { nodes: [
        { commit: { statusCheckRollup: { contexts: {
          nodes: [],
          pageInfo: { hasNextPage: true, endCursor: null },
        } } } },
      ] } } } } },
    });
    expect(result.code).toBe(1);
    expect(result.stderr).toContain("missing contexts.pageInfo.endCursor");
  });

  it("does not drop an unknown check kind into a successful empty collection", async () => {
    const result = await readChecks({
      code: 1,
      stderr: "no checks reported on the 'feature' branch\n",
      rollup: { data: { repository: { pullRequest: { commits: { nodes: [
        { commit: { statusCheckRollup: { contexts: {
          nodes: [{ __typename: "FutureCheck" }],
          pageInfo: { hasNextPage: false, endCursor: null },
        } } } },
      ] } } } } },
    });
    expect(result.code).toBe(1);
    expect(result.stderr).toContain("invalid contexts.nodes");
  });
});
