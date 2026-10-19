import { afterEach, describe, expect, it } from "bun:test";
import {
  chmod,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  NotFoundError,
  UsageError,
  UserError,
  openStore,
  parseVerdict,
  type OpenStoreOptions,
  type Store,
} from "../../../../../skills/poteto-mode/scripts/orch/store.ts";

const SCRIPT = join(import.meta.dir, "../../../../../skills/poteto-mode/scripts/orch/orch.ts");
const directories: string[] = [];
const handles: Store[] = [];
const GT_CALLS = "gt-calls.txt";

interface RunResult {
  readonly code: number;
  readonly stdout: string;
  readonly stderr: string;
}

async function makeDirectory(): Promise<string> {
  const directory = await mkdtemp(join(tmpdir(), "orch-test-"));
  directories.push(directory);
  return directory;
}

function useStore(
  directory: string,
  options?: OpenStoreOptions
): Store {
  const store = openStore(directory, options);
  handles.push(store);
  return store;
}

async function initializedStore(): Promise<{
  readonly directory: string;
  readonly store: Store;
}> {
  const directory = await makeDirectory();
  const store = useStore(directory);
  await store.init();
  return { directory, store };
}

function git({
  args,
  repo,
}: {
  args: readonly string[];
  repo: string;
}): string {
  const result = Bun.spawnSync(["git", "-C", repo, ...args]);
  if (result.exitCode !== 0) {
    throw new Error(
      `git ${args.join(" ")} failed: ${result.stderr.toString()}`
    );
  }
  return result.stdout.toString().trim();
}

async function makeGitStack(directory: string): Promise<{
  readonly repo: string;
  readonly mergedSha: string;
  readonly closedSha: string;
  readonly openSha: string;
  readonly draftSha: string;
}> {
  const repo = join(directory, "repo");
  await mkdir(repo);
  git({ repo, args: ["init", "--initial-branch=main"] });
  git({
    repo,
    args: ["remote", "add", "origin", "https://github.com/personal/project.git"],
  });
  git({ repo, args: ["config", "user.name", "Orch Test"] });
  git({ repo, args: ["config", "user.email", "orch@example.com"] });
  await writeFile(join(repo, "main.txt"), "main\n");
  git({ repo, args: ["add", "."] });
  git({ repo, args: ["commit", "-m", "main"] });

  const branches = [
    "stack/merged",
    "stack/closed",
    "stack/open",
    "stack/draft",
  ];
  for (const [index, branch] of branches.entries()) {
    git({ repo, args: ["checkout", "-b", branch] });
    await writeFile(join(repo, `stack-${index}.txt`), `${branch}\n`);
    git({ repo, args: ["add", "."] });
    git({ repo, args: ["commit", "-m", branch] });
  }
  git({ repo, args: ["checkout", "stack/open"] });

  return {
    repo,
    mergedSha: git({ repo, args: ["rev-parse", "stack/merged"] }),
    closedSha: git({ repo, args: ["rev-parse", "stack/closed"] }),
    openSha: git({ repo, args: ["rev-parse", "stack/open"] }),
    draftSha: git({ repo, args: ["rev-parse", "stack/draft"] }),
  };
}

type OriginFixtureState = "open" | "draft" | "merged" | "closed";

function originRows(
  prs: readonly {
    number: number;
    state: OriginFixtureState;
    head: string;
    base: string;
  }[]
): string {
  return JSON.stringify(
    prs.map(({ number, state, head, base }) => ({
      number,
      status: state,
      headRef: head,
      baseRef: base,
    }))
  );
}

async function overrideOriginRoute({
  directory,
  filter,
  branch,
  rows,
}: {
  directory: string;
  filter: "--head" | "--base";
  branch: string;
  rows: string;
}): Promise<void> {
  const routes = join(directory, "origin-routes");
  await mkdir(routes, { recursive: true });
  await writeFile(join(routes, `${filter}-${branch}`.replaceAll("/", "_")), `${rows}\n`);
}

async function withFakeOrigin<T>({
  directory,
  operation,
  currentRows,
}: {
  directory: string;
  operation: () => Promise<T>;
  currentRows?: string;
}): Promise<T> {
  const bin = join(directory, "origin-bin");
  const outputPath = join(directory, "origin-output.txt");
  await mkdir(bin, { recursive: true });
  await writeFile(
    outputPath,
    `${
      currentRows ??
      originRows([
        { number: 11, state: "open", head: "stack/open", base: "stack/closed" },
      ])
    }\n`
  );
  const list = (filter: string, branch: string): string =>
    `pr list ${filter} ${branch} --state all --json number,status,headRef,baseRef`;
  const fake = join(bin, "origin");
  await writeFile(
    fake,
    `#!/usr/bin/env bash
set -euo pipefail
if [ "$(pwd -P)" != "${realpathSync(join(directory, "repo"))}" ]; then
  printf 'origin ran outside the fixture repo: %s\\n' "$(pwd -P)" >&2
  exit 2
fi
route="$3-$4"
override="${join(directory, "origin-routes")}/\${route//\\//_}"
if [ -f "$override" ]; then
  cat "$override"
  exit 0
fi
case "$*" in
  "${list("--head", "stack/open")}")
    cat "${outputPath}"
    ;;
  "${list("--head", "stack/closed")}")
    printf '%s\\n' '${originRows([{ number: 13, state: "closed", head: "stack/closed", base: "stack/merged" }])}'
    ;;
  "${list("--head", "stack/merged")}")
    printf '%s\\n' '${originRows([{ number: 10, state: "merged", head: "stack/merged", base: "main" }])}'
    ;;
  "${list("--base", "stack/open")}")
    printf '%s\\n' '${originRows([
      { number: 14, state: "draft", head: "stack/draft", base: "stack/open" },
      { number: 15, state: "closed", head: "stack/abandoned", base: "stack/open" },
    ])}'
    ;;
  "${list("--base", "stack/draft")}")
    printf '[]\\n'
    ;;
  "${list("--head", "main")}")
    printf '[]\\n'
    ;;
  *)
    printf 'unexpected origin arguments: %s\\n' "$*" >&2
    exit 2
    ;;
esac
`
  );
  await chmod(fake, 0o755);
  await writeFile(
    join(bin, "gh"),
    `#!/usr/bin/env bash
printf 'gh must not run for --forge origin\\n' >&2
exit 2
`
  );
  await chmod(join(bin, "gh"), 0o755);

  const originalPath = process.env.PATH;
  process.env.PATH = `${bin}:${originalPath ?? ""}`;
  try {
    return await operation();
  } finally {
    if (originalPath === undefined) {
      delete process.env.PATH;
    } else {
      process.env.PATH = originalPath;
    }
  }
}

async function withFakeGt<T>({
  directory,
  operation,
  output,
}: {
  directory: string;
  operation: (outputPath: string) => Promise<T>;
  output: string;
}): Promise<T> {
  const bin = join(directory, "bin");
  const outputPath = join(directory, "gt-output.txt");
  await mkdir(bin);
  await writeFile(outputPath, output);
  const gt = join(bin, "gt");
  await writeFile(
    gt,
    `#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "${join(directory, GT_CALLS)}"
if [ "$(pwd -P)" != "${realpathSync(join(directory, "repo"))}" ]; then
  printf 'gt ran outside the fixture repo: %s\\n' "$(pwd -P)" >&2
  exit 2
fi
case "$*" in
  "--version")
    printf 'gt test fixture\\n'
    ;;
  "--no-interactive log short --stack --reverse")
    cat "${outputPath}"
    ;;
  "--no-interactive info stack/merged")
    printf 'stack/merged\\nPR #10 (Merged) merged change\\n'
    ;;
  "--no-interactive info stack/closed")
    printf 'stack/closed\\nPR #13 (Closed) closed change\\n'
    ;;
  "--no-interactive info stack/open")
    printf 'stack/open\\nPR #11 (Needs approvals) open change\\n'
    ;;
  *)
    printf 'unexpected gt arguments: %s\\n' "$*" >&2
    exit 2
    ;;
esac
`
  );
  await writeFile(
    join(bin, "gh"),
    `#!/usr/bin/env bash
printf 'gh must not run while gt is available\\n' >&2
exit 2
`
  );
  await chmod(gt, 0o755);
  await chmod(join(bin, "gh"), 0o755);

  const originalPath = process.env.PATH;
  process.env.PATH = `${bin}:${originalPath ?? ""}`;
  try {
    return await operation(outputPath);
  } finally {
    if (originalPath === undefined) {
      delete process.env.PATH;
    } else {
      process.env.PATH = originalPath;
    }
  }
}

async function withFakeGithub<T>({
  directory,
  operation,
  output,
  upstreamOutput = output,
}: {
  directory: string;
  operation: () => Promise<T>;
  output: string;
  upstreamOutput?: string;
}): Promise<T> {
  const bin = join(directory, "github-bin");
  const outputPath = join(directory, "github-output.json");
  await mkdir(bin);
  await writeFile(outputPath, output);
  const upstreamPath = join(directory, "upstream-output.json");
  await writeFile(upstreamPath, upstreamOutput);
  const gh = join(bin, "gh");
  await writeFile(
    gh,
    `#!/usr/bin/env bash
set -euo pipefail
if [ "$(pwd -P)" != "${realpathSync(join(directory, "repo"))}" ]; then
  printf 'gh ran outside the fixture repo: %s\\n' "$(pwd -P)" >&2
  exit 2
fi
case "$*" in
  "pr list --state all --limit 1000 --json number,state,headRefName,headRefOid,baseRefName,isCrossRepository")
    cat "${upstreamPath}"
    ;;
  "pr list --repo github.com/personal/project --state all --limit 1000 --json number,state,headRefName,headRefOid,baseRefName,isCrossRepository")
    cat "${outputPath}"
    ;;
  *)
    printf 'unexpected gh arguments: %s\\n' "$*" >&2
    exit 2
    ;;
esac
`
  );
  await chmod(gh, 0o755);

  const originalPath = process.env.PATH;
  process.env.PATH = `${bin}:${originalPath ?? "/usr/bin:/bin"}`;
  try {
    return await operation();
  } finally {
    if (originalPath === undefined) {
      delete process.env.PATH;
    } else {
      process.env.PATH = originalPath;
    }
  }
}

async function withoutGtOrGh<T>({
  directory,
  operation,
}: {
  directory: string;
  operation: () => Promise<T>;
}): Promise<T> {
  const bin = join(directory, "no-frontier-bin");
  const gitPath = Bun.which("git");
  if (gitPath === null) {
    throw new Error("git is required for the fixture");
  }
  await mkdir(bin);
  await symlink(gitPath, join(bin, "git"));
  const originalPath = process.env.PATH;
  process.env.PATH = bin;
  try {
    return await operation();
  } finally {
    if (originalPath === undefined) {
      delete process.env.PATH;
    } else {
      process.env.PATH = originalPath;
    }
  }
}

function runCli(
  args: readonly string[],
  env: Readonly<Record<string, string | undefined>> = process.env
): RunResult {
  const result = Bun.spawnSync([process.execPath, SCRIPT, ...args], { env });
  return {
    code: result.exitCode,
    stdout: result.stdout.toString(),
    stderr: result.stderr.toString(),
  };
}

afterEach(async () => {
  for (const store of handles.splice(0).reverse()) {
    await store.close();
  }
  for (const directory of directories.splice(0)) {
    await rm(directory, { recursive: true, force: true });
  }
});

describe("Store", () => {
  it("initializes an idempotent plain-file store and releases its lock", async () => {
    const directory = await makeDirectory();
    const store = useStore(directory);

    expect(await store.init()).toEqual({ store: directory });
    const firstUnits = await readFile(join(directory, "units.tsv"), "utf8");
    const firstLedger = await readFile(
      join(directory, "ledger.tsv"),
      "utf8"
    );

    expect(await store.init()).toEqual({ store: directory });
    expect(await readFile(join(directory, "units.tsv"), "utf8")).toBe(
      firstUnits
    );
    expect(await readFile(join(directory, "ledger.tsv"), "utf8")).toBe(
      firstLedger
    );
    expect((await readdir(directory)).sort()).toEqual([
      ".orch.lock",
      "frontier.json",
      "gates.md",
      "inbox",
      "ledger.tsv",
      "preferences.md",
      "units.tsv",
    ]);

    await store.close();
    expect(await readdir(directory)).not.toContain(".orch.lock");
  });

  it("composes unit add, set, get, list, and counts", async () => {
    const { store } = await initializedStore();

    expect(
      await store.units.add({
        id: "u1",
        track: "build",
        brief: "briefs/u1.md",
      })
    ).toMatchObject({ id: "u1", state: "pending" });
    expect(
      await store.units.add({ id: "=SUM(A1)", track: "+build" })
    ).toMatchObject({ id: "'=SUM(A1)", track: "'+build" });

    const updated = await store.units.set({
      id: "u1",
      state: "done",
      branch: "poteto/u1",
      pr: 184530,
      sha: "abc123",
    });
    expect(updated).toEqual({
      id: "u1",
      track: "build",
      state: "done",
      branch: "poteto/u1",
      pr: "184530",
      sha: "abc123",
      brief: "briefs/u1.md",
    });
    expect(await store.units.get("u1")).toEqual(updated);
    expect(
      await store.units.list({ state: "done", track: "build" })
    ).toEqual([updated]);
    expect(await store.units.counts()).toEqual({ done: 1, pending: 1 });
    await expect(
      store.units.add({ id: "u1", track: "build" })
    ).rejects.toThrow("unit u1 already exists");
    await expect(
      store.units.set({ id: "missing", state: "done" })
    ).rejects.toBeInstanceOf(NotFoundError);
  });

  it("records, replaces, checks, and summarizes typed ledger verdicts", async () => {
    const { store } = await initializedStore();

    try {
      await store.ledger.check({ pr: 184530, sha: "abc123" });
      throw new Error("expected ledger check to fail");
    } catch (error) {
      expect(error).toBeInstanceOf(NotFoundError);
      if (error instanceof NotFoundError) {
        expect(error.output).toEqual({
          compact: "NOT-VERIFIED",
          json: {
            pr: "184530",
            sha: "abc123",
            verdict: "NOT-VERIFIED",
          },
        });
      }
    }
    expect(() => parseVerdict("looks-good")).toThrow("verdict must be");

    const recorded = await store.ledger.record({
      pr: 184530,
      sha: "abc123",
      verdict: "unit-test-verified",
      evidence: "reports/verify.md",
      verifier: "opus",
    });
    expect(await store.ledger.check({ pr: 184530, sha: "abc123" })).toEqual(
      recorded
    );
    expect(await store.ledger.summary()).toEqual({
      "unit-test-verified": 1,
    });

    await store.ledger.record({
      pr: 184530,
      sha: "abc123",
      verdict: "live-ui-verified",
      evidence: "reports/live.md",
      verifier: "sol",
    });
    expect(await store.ledger.summary()).toEqual({
      "live-ui-verified": 1,
    });
  });

  it("pushes, peeks, and atomically drains inbox pointers", async () => {
    const { directory, store } = await initializedStore();

    const first = await store.inbox.push({
      agent: "worker-1",
      unit: "u1",
      status: "done",
      report: "reports/u1.md",
    });
    expect(first.pointer).toMatchObject({ unit: "u1", status: "done" });
    expect(first.filename).toEndWith(".tsv");
    await store.inbox.push({
      agent: "worker-2",
      unit: "u2",
      status: "failed",
    });

    expect(await store.inbox.count()).toBe(2);
    expect(await store.inbox.peek()).toHaveLength(2);
    expect(await store.inbox.count()).toBe(2);
    expect(await store.inbox.drain()).toHaveLength(2);
    expect(await store.inbox.count()).toBe(2);
    const batch = await store.inbox.claim();
    if (batch === null) throw new Error("expected the retained batch");
    await store.inbox.ack(
      batch.id,
      batch.events.map((event) => ({
        event: event.id,
        outcome: { kind: "discard", reason: "reviewed" },
      })),
    );
    expect(await store.inbox.count()).toBe(0);
    expect(await readdir(join(directory, "inbox"))).toEqual([]);
    expect(
      (await readdir(directory)).filter((name) =>
        name.startsWith(".inbox-drain-")
      )
    ).toEqual([]);
  });

  it("replaces a stale lock whose holder pid is dead", async () => {
    const { directory } = await initializedStore();
    const exited = Bun.spawn(["true"]);
    await exited.exited;
    await writeFile(join(directory, ".orch.lock"), `${exited.pid}\n`);

    const stale: string[] = [];
    const recovered = useStore(directory, {
      onStaleLock: (holder) => stale.push(holder),
    });
    expect(
      await recovered.units.add({ id: "u1", track: "build" })
    ).toMatchObject({ id: "u1" });
    expect(stale).toEqual([String(exited.pid)]);
    await recovered.close();
    expect(await readdir(directory)).not.toContain(".orch.lock");
  });

  it("blocks a writer and steals the pid lock only with force", async () => {
    const { directory, store } = await initializedStore();
    await store.close();
    await writeFile(join(directory, ".orch.lock"), `${process.pid}\n`);

    const blocked = useStore(directory);
    await expect(
      blocked.units.add({ id: "u1", track: "build" })
    ).rejects.toThrow(`store lock held by pid ${process.pid}`);

    const stolen: string[] = [];
    const forced = useStore(directory, {
      force: true,
      onLockStolen: (holder) => stolen.push(holder),
    });
    expect(
      await forced.units.add({ id: "u1", track: "build" })
    ).toMatchObject({ id: "u1" });
    expect(stolen).toEqual([String(process.pid)]);
    await forced.close();
    expect(await readdir(directory)).not.toContain(".orch.lock");
  });

  it("parks gates, stores standing orders, and renders status", async () => {
    const { directory, store } = await initializedStore();
    await store.units.add({ id: "u1", track: "build" });
    expect(
      await store.gates.park({
        id: "release",
        question: "Ship now?",
        options: "ship,wait",
        defaultAnswer: "wait",
      })
    ).toMatchObject({ kind: "open", id: "release" });
    expect(
      await store.standing.add({ line: "Never force push." })
    ).toEqual({ number: 1, line: "Never force push." });

    const first = await store.status.render();
    expect(first.changed).toBe("first render");
    expect(first.summary.openGateIds).toEqual(["release"]);
    expect(await readFile(join(directory, "status.md"), "utf8")).toContain(
      "| release | open | Ship now? |"
    );
    expect((await store.status.render()).changed).toBe("no derived changes");

    expect(
      await store.gates.resolve({ id: "release", answer: "ship" })
    ).toMatchObject({ kind: "resolved", answer: "ship" });
    expect((await store.status.render()).changed).toBe("open gates 1->0");
    expect(await store.gates.list()).toEqual([]);
    expect(await store.standing.show()).toEqual([
      { number: 1, line: "Never force push." },
    ]);
  });

  it("resolves the ordered Graphite frontier and validates an optional pin", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);
    const output = `◯ main
◯ stack/merged
◯ stack/closed
◉ stack/open (current)
`;

    await withFakeGt({
      directory,
      output,
      operation: async () => {
        expect(
          await store.frontier.set({ repo: stack.repo, discovery: "graphite" })
        ).toEqual({
          generation: 1,
          prs: [
            {
              pr: 10,
              branches: "stack/merged",
              sha: stack.mergedSha,
              state: "MERGED",
            },
            {
              pr: 13,
              branches: "stack/closed",
              sha: stack.closedSha,
              state: "CLOSED",
            },
            {
              pr: 11,
              branches: "stack/open",
              sha: stack.openSha,
              state: "OPEN",
            },
          ],
          lowestUnmerged: 11,
        });
        expect(
          (
            await store.frontier.set({
              repo: stack.repo,
              discovery: "graphite",
              prs: [10, 13, 11],
            })
          ).generation
        ).toBe(2);
        expect((await store.frontier.show()).generation).toBe(2);
        await expect(
          store.frontier.set({
            repo: stack.repo,
            discovery: "graphite",
            prs: [10, 11, 12],
          })
        ).rejects.toThrow(
          "frontier pin mismatch: missing from gt: 12; extra in gt: 13"
        );
        await expect(
          store.frontier.set({
            repo: stack.repo,
            discovery: "graphite",
            prs: [13, 10, 11],
          })
        ).rejects.toThrow(
          "frontier pin mismatch: order differs: expected 13,10,11; gt 10,13,11"
        );
        await expect(
          store.frontier.set({
            repo: stack.repo,
            discovery: "graphite",
            prs: [10, 10],
          })
        ).rejects.toThrow("--prs must not contain duplicates");
      },
    });
  });

  it("discovers the checked-out GitHub stack by default", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);

    await withFakeGithub({
      directory,
      output: JSON.stringify([
        {
          number: 11,
          state: "OPEN",
          headRefName: "stack/open",
          headRefOid: stack.openSha,
          baseRefName: "stack/closed",
          isCrossRepository: false,
        },
        {
          number: 10,
          state: "MERGED",
          headRefName: "stack/merged",
          headRefOid: stack.mergedSha,
          baseRefName: "main",
          isCrossRepository: false,
        },
        {
          number: 13,
          state: "CLOSED",
          headRefName: "stack/closed",
          headRefOid: stack.closedSha,
          baseRefName: "stack/merged",
          isCrossRepository: false,
        },
      ]),
      operation: async () => {
        expect(await store.frontier.set({ repo: stack.repo })).toEqual({
          generation: 1,
          prs: [
            {
              pr: 10,
              branches: "stack/merged",
              sha: stack.mergedSha,
              state: "MERGED",
            },
            {
              pr: 13,
              branches: "stack/closed",
              sha: stack.closedSha,
              state: "CLOSED",
            },
            {
              pr: 11,
              branches: "stack/open",
              sha: stack.openSha,
              state: "OPEN",
            },
          ],
          lowestUnmerged: 11,
        });
        await expect(
          store.frontier.set({ repo: stack.repo, prs: [10, 11, 12] })
        ).rejects.toThrow(
          "frontier pin mismatch: missing from GitHub: 12; extra in GitHub: 13"
        );
      },
    });
  });

  it("resolves a personal fork through the CLI despite upstream history and GH_REPO", async () => {
    const directory = await makeDirectory();
    const stack = await makeGitStack(directory);
    const storeDirectory = join(directory, "store");
    const rows = [
      {
        number: 10,
        state: "MERGED",
        headRefName: "stack/merged",
        headRefOid: stack.mergedSha,
        baseRefName: "main",
        isCrossRepository: false,
      },
      {
        number: 13,
        state: "CLOSED",
        headRefName: "stack/closed",
        headRefOid: stack.closedSha,
        baseRefName: "stack/merged",
        isCrossRepository: false,
      },
      {
        number: 11,
        state: "OPEN",
        headRefName: "stack/open",
        headRefOid: stack.openSha,
        baseRefName: "stack/closed",
        isCrossRepository: false,
      },
    ];
    git({
      repo: stack.repo,
      args: ["remote", "add", "upstream", "https://github.com/upstream/project.git"],
    });
    git({ repo: stack.repo, args: ["config", "remote.upstream.gh-resolved", "base"] });
    await withFakeGithub({
      directory,
      output: JSON.stringify(rows),
      upstreamOutput: JSON.stringify(
        Array.from({ length: 1000 }, (_, index) => ({
          ...rows[0],
          number: index + 100,
          headRefName: `upstream/${index}`,
        }))
      ),
      operation: async () => {
        const env = { ...process.env, GH_REPO: "unrelated/project" };
        expect(runCli(["--store", storeDirectory, "init"], env).code).toBe(0);
        const result = runCli(
          ["--store", storeDirectory, "--json", "frontier", "set", "--repo", stack.repo],
          env
        );
        expect(result.code).toBe(0);
        expect(result.stderr).toBe("");
        const expected = {
          generation: 1,
          prs: [
            { pr: 10, branches: "stack/merged", sha: stack.mergedSha, state: "MERGED" },
            { pr: 13, branches: "stack/closed", sha: stack.closedSha, state: "CLOSED" },
            { pr: 11, branches: "stack/open", sha: stack.openSha, state: "OPEN" },
          ],
          lowestUnmerged: 11,
        };
        expect(JSON.parse(result.stdout)).toEqual(expected);
        expect(
          JSON.parse(await readFile(join(storeDirectory, "frontier.json"), "utf8"))
        ).toEqual(expected);
      },
    });
  });

  it("rejects incomplete origin history even when upstream history is small", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);
    const selected = {
      number: 11,
      state: "OPEN",
      headRefName: "stack/open",
      headRefOid: stack.openSha,
      baseRefName: "main",
      isCrossRepository: false,
    };
    const rows = Array.from({ length: 999 }, (_, index) => ({
      ...selected,
      number: index + 100,
      headRefName: `unrelated/${index}`,
    }));
    await withFakeGithub({
      directory,
      output: JSON.stringify([selected, ...rows]),
      upstreamOutput: JSON.stringify([selected]),
      operation: async () => {
        await expect(store.frontier.set({ repo: stack.repo })).rejects.toThrow(
          "gh pr list reached its 1000 PR limit"
        );
        expect(await readFile(join(directory, "frontier.json"), "utf8")).toBe("{}\n");
      },
    });
  });

  it("resolves origin history below the limit", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);
    const selected = {
      number: 11,
      state: "OPEN",
      headRefName: "stack/open",
      headRefOid: stack.openSha,
      baseRefName: "main",
      isCrossRepository: false,
    };
    const rows = Array.from({ length: 998 }, (_, index) => ({
      ...selected,
      number: index + 100,
      headRefName: `unrelated/${index}`,
    }));
    await withFakeGithub({
      directory,
      output: JSON.stringify([selected, ...rows]),
      operation: async () => {
        expect(await store.frontier.set({ repo: stack.repo })).toEqual({
          generation: 1,
          prs: [{ pr: 11, branches: "stack/open", sha: stack.openSha, state: "OPEN" }],
          lowestUnmerged: 11,
        });
      },
    });
  });

  it("rejects unsafe origin identities through the CLI without leaking them or changing store bytes", async () => {
    const directory = await makeDirectory();
    const stack = await makeGitStack(directory);
    const storeDirectory = join(directory, "store");
    const selected = {
      number: 11,
      state: "OPEN",
      headRefName: "stack/open",
      headRefOid: stack.openSha,
      baseRefName: "main",
      isCrossRepository: false,
    };
    await withFakeGithub({
      directory,
      output: JSON.stringify([selected]),
      operation: async () => {
        const callsPath = join(directory, "gh-calls.txt");
        await writeFile(join(directory, "github-bin", "gh"), `#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$@" >> "${callsPath}"
case "$4" in
  https://github.com/personal/project.git|github.com/personal/project) cat "${join(directory, "github-output.json")}" ;;
  *) printf 'repository rejected: %s\\n' "$4" >&2; exit 2 ;;
esac
`);
        expect(runCli(["--store", storeDirectory, "init"]).code).toBe(0);
        const args = ["--store", storeDirectory, "--json", "frontier", "set", "--repo", stack.repo];
        const valid = runCli(args);
        expect(valid.code).toBe(0);
        expect(JSON.parse(valid.stdout)).toEqual({
          generation: 1,
          prs: [{ pr: 11, branches: "stack/open", sha: stack.openSha, state: "OPEN" }],
          lowestUnmerged: 11,
        });
        const entries = (await readdir(storeDirectory)).sort();
        const names = (await readdir(storeDirectory, { withFileTypes: true }))
          .filter((entry) => entry.isFile())
          .map((entry) => entry.name).sort();
        const before = await Promise.all(names.map((name) => readFile(join(storeDirectory, name))));
        const marker = "PUBLIC_TEST_SENTINEL";
        const host = "github.com";
        for (const origin of [
          `https://user:${marker}@${host}/personal/project.git`,
          `https://${marker}@${host}/personal/project.git`,
          `https://@github.com/personal/project.git`,
          `ssh://git:${marker}@${host}/personal/project.git`,
          `https://github.com/personal/project.git?token=${marker}`,
          `https://github.com/personal/project.git#${marker}`,
          `https://github.com/personal/%2F${marker}.git`,
          `https://github.com/%${marker}/project.git`,
          `https://github.com/personal/${marker}\\project.git`,
          `https://github.com:8443/personal/${marker}.git`,
          `file:///personal/${marker}.git`,
          `${marker}@${host}:personal/project.git`,
          "https://github.com/personal//project.git",
          "https://github.com/other/../personal/project.git",
          " ",
          "\t",
          "",
        ]) {
          await writeFile(callsPath, "");
          git({ repo: stack.repo, args: ["config", "remote.origin.url", origin] });
          const result = runCli(args);
          expect(result.code).toBe(1);
          expect(result.stdout).toBe("");
          expect(result.stderr).not.toContain(marker);
          expect(result.stderr).toContain("GitHub frontier discovery requires");
          expect(await readFile(callsPath, "utf8")).toBe("");
          expect((await readdir(storeDirectory)).sort()).toEqual(entries);
          expect(await readdir(join(storeDirectory, "inbox"))).toEqual([]);
          expect(await Promise.all(names.map((name) => readFile(join(storeDirectory, name))))).toEqual(before);
        }
        git({ repo: stack.repo, args: ["remote", "remove", "origin"] });
        expect(runCli(args).code).toBe(1);
        expect(await readFile(callsPath, "utf8")).toBe("");
        expect(await Promise.all(names.map((name) => readFile(join(storeDirectory, name))))).toEqual(before);
      },
    });
  });

  it("uses a credential-free fetch identity for supported transports, rewrites, and gh failures", async () => {
    const directory = await makeDirectory();
    const stack = await makeGitStack(directory);
    const storeDirectory = join(directory, "store");
    const selected = {
      number: 11,
      state: "OPEN",
      headRefName: "stack/open",
      headRefOid: stack.openSha,
      baseRefName: "main",
      isCrossRepository: false,
    };
    await withFakeGithub({
      directory,
      output: JSON.stringify([selected]),
      operation: async () => {
        const callsPath = join(directory, "gh-calls.txt");
        const failurePath = join(directory, "gh-fails");
        await writeFile(join(directory, "github-bin", "gh"), `#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$@" >> "${callsPath}"
if [ "$#" -ne 10 ] || [ "$3" != "--repo" ] || [ "\${GH_REPO+x}" = x ] || [ "$(pwd -P)" != "${realpathSync(stack.repo)}" ]; then exit 2; fi
case "$4" in
  github.com/personal/project|example.com/personal/project) ;;
  *) exit 2 ;;
esac
if [ -f "${failurePath}" ]; then printf 'ordinary fixture query failure\\n' >&2; exit 3; fi
cat "${join(directory, "github-output.json")}"
`);
        expect(runCli(["--store", storeDirectory, "init"]).code).toBe(0);
        git({ repo: stack.repo, args: ["config", "remote.origin.pushurl", "https://github.com/upstream/project.git"] });
        git({ repo: stack.repo, args: ["config", "url.https://github.com/.insteadOf", "pstack-fixture:"] });
        const args = ["--store", storeDirectory, "--json", "frontier", "set", "--repo", stack.repo];
        let generation = 0;
        for (const [origin, identity] of [
          ["https://github.com/personal/project.git", "github.com/personal/project"],
          ["git@github.com:personal/project.git", "github.com/personal/project"],
          ["ssh://git@github.com/personal/project.git", "github.com/personal/project"],
          ["https://example.com/personal/project", "example.com/personal/project"],
          ["pstack-fixture:personal/project.git", "github.com/personal/project"],
        ]) {
          git({ repo: stack.repo, args: ["config", "remote.origin.url", origin] });
          await writeFile(callsPath, "");
          const result = runCli(args, { ...process.env, GH_REPO: "ambient/wrong", GH_HOST: "wrong.example.com" });
          expect(result.code).toBe(0);
          expect(result.stderr).toBe("");
          expect(JSON.parse(result.stdout)).toEqual({
            generation: ++generation,
            prs: [{ pr: 11, branches: "stack/open", sha: stack.openSha, state: "OPEN" }],
            lowestUnmerged: 11,
          });
          expect(await readFile(callsPath, "utf8")).toBe(
            `pr\nlist\n--repo\n${identity}\n--state\nall\n--limit\n1000\n--json\nnumber,state,headRefName,headRefOid,baseRefName,isCrossRepository\n`
          );
        }
        const before = await readFile(join(storeDirectory, "frontier.json"));
        await writeFile(failurePath, "");
        const failed = runCli(args);
        expect(failed.code).toBe(1);
        expect(failed.stdout).toBe("");
        expect(failed.stderr).toContain("gh pr list failed");
        expect(failed.stderr).toContain("ordinary fixture query failure");
        expect(failed.stderr).toContain("github.com/personal/project");
        expect(failed.stderr).not.toContain("pstack-fixture:");
        expect(await readFile(join(storeDirectory, "frontier.json"))).toEqual(before);
      },
    });
  });

  it("rejects missing and empty origin identities without recording a frontier", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);
    await withFakeGithub({
      directory,
      output: JSON.stringify([{
        number: 11,
        state: "OPEN",
        headRefName: "stack/open",
        headRefOid: stack.openSha,
        baseRefName: "main",
        isCrossRepository: false,
      }]),
      operation: async () => {
        git({ repo: stack.repo, args: ["remote", "remove", "origin"] });
        await expect(store.frontier.set({ repo: stack.repo })).rejects.toThrow(
          "GitHub frontier discovery requires an origin remote"
        );
        git({ repo: stack.repo, args: ["config", "remote.origin.url", ""] });
        expect(git({ repo: stack.repo, args: ["remote", "get-url", "origin"] })).toBe("origin");
        await expect(store.frontier.set({ repo: stack.repo })).rejects.toThrow(
          "GitHub frontier discovery requires a supported credential-free origin URL"
        );
        expect(await readFile(join(directory, "frontier.json"), "utf8")).toBe("{}\n");
      },
    });
  });

  for (const [name, origin] of [["space", " "], ["tab", "\t"]] as const) {
    it(`rejects a ${name}-only origin through the CLI before gh can select upstream`, async () => {
      const directory = await makeDirectory();
      const stack = await makeGitStack(directory);
      const storeDirectory = join(directory, "store");
      const selected = {
        number: 11,
        state: "OPEN",
        headRefName: "stack/open",
        headRefOid: stack.openSha,
        baseRefName: "main",
        isCrossRepository: false,
      };
      git({ repo: stack.repo, args: ["remote", "add", "upstream", "https://github.com/upstream/project.git"] });
      git({ repo: stack.repo, args: ["config", "remote.upstream.gh-resolved", "base"] });
      await withFakeGithub({
        directory,
        output: JSON.stringify([selected]),
        upstreamOutput: JSON.stringify([{ ...selected, number: 911 }]),
        operation: async () => {
          const callsPath = join(directory, "gh-calls.txt");
          await writeFile(join(directory, "github-bin", "gh"), `#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$4" >> "${callsPath}"
if [ "$#" -ne 10 ] || [ "$3" != "--repo" ]; then
  exit 2
fi
case "$4" in
  github.com/personal/project) cat "${join(directory, "github-output.json")}" ;;
  "") cat "${join(directory, "upstream-output.json")}" ;;
  *) exit 2 ;;
esac
`);
          expect(runCli(["--store", storeDirectory, "init"]).code).toBe(0);
          const args = ["--store", storeDirectory, "--json", "frontier", "set", "--repo", stack.repo];
          const valid = runCli(args);
          expect(valid.code).toBe(0);
          expect(JSON.parse(valid.stdout)).toEqual({
            generation: 1,
            prs: [{ pr: 11, branches: "stack/open", sha: stack.openSha, state: "OPEN" }],
            lowestUnmerged: 11,
          });
          expect(await readFile(callsPath, "utf8")).toBe("github.com/personal/project\n");
          const before = await readFile(join(storeDirectory, "frontier.json"), "utf8");
          await writeFile(callsPath, "");
          git({ repo: stack.repo, args: ["config", "remote.origin.url", origin] });
          const result = runCli(args);
          expect(result.code).toBe(1);
          expect(result.stderr).toContain("GitHub frontier discovery requires a nonempty origin URL");
          expect(result.stdout).toBe("");
          expect(await readFile(callsPath, "utf8")).toBe("");
          expect(await readFile(join(storeDirectory, "frontier.json"), "utf8")).toBe(before);
        },
      });
    });
  }

  it("keeps historical ambiguity and topology checks after repository selection", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);
    const selected = {
      number: 11,
      state: "OPEN",
      headRefName: "stack/open",
      headRefOid: stack.openSha,
      baseRefName: "stack/merged",
      isCrossRepository: false,
    };
    const parent = {
      ...selected,
      number: 10,
      state: "MERGED",
      headRefName: "stack/merged",
      headRefOid: stack.mergedSha,
      baseRefName: "main",
    };
    const cases = [
      {
        rows: [selected, parent, { ...parent, number: 12, state: "CLOSED" }],
        error: "multiple PRs for base branch stack/merged",
      },
      {
        rows: [selected, { ...selected, number: 12, state: "MERGED" }],
        error: "multiple PRs for checked out branch stack/open",
      },
      {
        rows: [selected, parent, { ...selected, number: 12, headRefName: "stack/sibling" }],
        error: "branched stack above stack/merged",
      },
      {
        rows: [selected, { ...parent, baseRefName: "stack/open" }],
        error: "cyclic stack",
      },
      {
        rows: [selected, { ...parent, isCrossRepository: true }],
        error: "does not support cross-repository stacks",
      },
      {
        rows: [selected, { ...parent, number: 11 }],
        error: "duplicate PR #11",
      },
    ];
    await withFakeGithub({
      directory,
      output: "[]",
      operation: async () => {
        for (const { rows, error } of cases) {
          await writeFile(
            join(directory, "github-output.json"),
            JSON.stringify(rows)
          );
          await expect(store.frontier.set({ repo: stack.repo })).rejects.toThrow(
            error
          );
          expect(await readFile(join(directory, "frontier.json"), "utf8")).toBe("{}\n");
        }
      },
    });
  });

  it("never invokes gt for the default frontier even when gt is installed", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);

    await withFakeGt({
      directory,
      output: "",
      operation: () =>
        withFakeGithub({
          directory,
          output: JSON.stringify([
            {
              number: 11,
              state: "OPEN",
              headRefName: "stack/open",
              headRefOid: stack.openSha,
              baseRefName: "main",
              isCrossRepository: false,
            },
          ]),
          operation: async () => {
            const frontier = await store.frontier.set({ repo: stack.repo });
            expect(frontier.prs).toEqual([
              {
                pr: 11,
                branches: "stack/open",
                sha: stack.openSha,
                state: "OPEN",
              },
            ]);
            expect(
              await readdir(directory).then((names) =>
                names.includes(GT_CALLS)
                  ? readFile(join(directory, GT_CALLS), "utf8")
                  : ""
              )
            ).toBe("");
          },
        }),
    });
  });

  it("fails a Graphite frontier request with a usage error when gt is missing", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);

    await withoutGtOrGh({
      directory,
      operation: async () => {
        const failure = await store.frontier
          .set({ repo: stack.repo, discovery: "graphite" })
          .then(
            () => undefined,
            (error: unknown) => error
          );
        expect(failure).toBeInstanceOf(UsageError);
        expect((failure as Error).message).toBe(
          "--graphite requires gt; install Graphite or omit --graphite to discover the frontier through GitHub"
        );
      },
    });
  });

  it("rejects a cross-repository base in the GitHub fallback", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);

    await withFakeGithub({
      directory,
      output: JSON.stringify([
        {
          number: 11,
          state: "OPEN",
          headRefName: "stack/open",
          headRefOid: stack.openSha,
          baseRefName: "stack/closed",
          isCrossRepository: false,
        },
        {
          number: 13,
          state: "OPEN",
          headRefName: "stack/closed",
          headRefOid: stack.closedSha,
          baseRefName: "main",
          isCrossRepository: true,
        },
      ]),
      operation: async () => {
        await expect(store.frontier.set({ repo: stack.repo })).rejects.toThrow(
          "GitHub frontier discovery does not support cross-repository stacks; pass --graphite for a stack Graphite tracks"
        );
      },
    });
  });

  it("explains how to resolve a missing GitHub CLI fallback", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);

    await withoutGtOrGh({
      directory,
      operation: async () => {
        await expect(store.frontier.set({ repo: stack.repo })).rejects.toThrow(
          "GitHub frontier discovery requires gh; install GitHub CLI, or pass --graphite for a stack Graphite tracks"
        );
      },
    });
  });

  it("rejects unparseable Graphite output loudly", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);

    await withFakeGt({
      directory,
      output: "◯ main\nthis line is not Graphite output\n",
      operation: async () => {
        await expect(
          store.frontier.set({ repo: stack.repo, discovery: "graphite" })
        ).rejects.toThrow(
          'gt log short output has an unparseable line 2: "this line is not Graphite output"'
        );
      },
    });
  });

  it("resolves the ordered frontier from the Origin base chain and validates an optional pin", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);

    await withFakeOrigin({
      directory,
      operation: async () => {
        expect(
          await store.frontier.set({ repo: stack.repo, forge: "origin" })
        ).toEqual({
          generation: 1,
          prs: [
            { pr: 10, branches: "stack/merged", sha: stack.mergedSha, state: "MERGED" },
            { pr: 13, branches: "stack/closed", sha: stack.closedSha, state: "CLOSED" },
            { pr: 11, branches: "stack/open", sha: stack.openSha, state: "OPEN" },
            { pr: 14, branches: "stack/draft", sha: stack.draftSha, state: "OPEN" },
          ],
          lowestUnmerged: 11,
        });
        expect(
          (
            await store.frontier.set({
              repo: stack.repo,
              forge: "origin",
              prs: [10, 13, 11, 14],
            })
          ).generation
        ).toBe(2);
        await expect(
          store.frontier.set({ repo: stack.repo, forge: "origin", prs: [10, 11, 12] })
        ).rejects.toThrow(
          "frontier pin mismatch: missing from Origin: 12; extra in Origin: 13,14"
        );
        await expect(
          store.frontier.set({ repo: stack.repo, forge: "origin", prs: [13, 10, 11, 14] })
        ).rejects.toThrow(
          "frontier pin mismatch: order differs: expected 13,10,11,14; Origin 10,13,11,14"
        );
      },
    });
  });

  it("rejects unparseable Origin output loudly", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);

    await withFakeOrigin({
      directory,
      currentRows: "this line is not forge output",
      operation: async () => {
        await expect(
          store.frontier.set({ repo: stack.repo, forge: "origin" })
        ).rejects.toThrow(
          "origin pr list --head stack/open output is not valid JSON"
        );
      },
    });
  });

  it("names the missing Origin pull request when a chain branch has none", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);

    await withFakeOrigin({
      directory,
      currentRows: "[]",
      operation: async () => {
        await expect(
          store.frontier.set({ repo: stack.repo, forge: "origin" })
        ).rejects.toThrow(
          "branch stack/open has no pull request; open one with origin pr create"
        );
        expect(await readFile(join(directory, "frontier.json"), "utf8")).toBe("{}\n");
      },
    });
  });

  it("rejects malformed Origin protocol rows without overwriting the saved frontier", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);
    const valid = { number: 11, status: "open", headRef: "stack/open", baseRef: "stack/closed" };
    const invalid = [
      null, {}, [null], [{}],
      ...[0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1, "11", null].map((number) => [{ ...valid, number }]),
      ...["unknown", "OPEN", null, 1].map((status) => [{ ...valid, status }]),
      ...["", null, 1].map((headRef) => [{ ...valid, headRef }]),
      ...["", null, 1].map((baseRef) => [{ ...valid, baseRef }]),
    ];
    await withFakeOrigin({ directory, operation: async () => {
      await store.frontier.set({ repo: stack.repo, forge: "origin" });
      const saved = await readFile(join(directory, "frontier.json"), "utf8");
      for (const value of invalid) {
        await overrideOriginRoute({ directory, filter: "--head", branch: "stack/open", rows: JSON.stringify(value) });
        await expect(store.frontier.set({ repo: stack.repo, forge: "origin" })).rejects.toThrow(
          Array.isArray(value) ? "output has an invalid PR row" : "output is not a JSON array"
        );
        expect(await readFile(join(directory, "frontier.json"), "utf8")).toBe(saved);
      }
    } });
  });

  it("fails an Origin frontier request with a usage error when origin is missing", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);

    await withoutGtOrGh({
      directory,
      operation: async () => {
        const failure = await store.frontier
          .set({ repo: stack.repo, forge: "origin" })
          .then(
            () => undefined,
            (error: unknown) => error
          );
        expect(failure).toBeInstanceOf(UsageError);
        expect((failure as Error).message).toContain(
          "--forge origin requires the origin CLI"
        );
      },
    });
  });

  it("reports an Origin command failure without falling back or overwriting the frontier", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);
    await withFakeOrigin({ directory, operation: async () => {
      await store.frontier.set({ repo: stack.repo, forge: "origin" });
      const saved = await readFile(join(directory, "frontier.json"), "utf8");
      await writeFile(join(directory, "origin-bin", "origin"), "#!/bin/sh\nexit 7\n");
      await expect(store.frontier.set({ repo: stack.repo, forge: "origin" })).rejects.toThrow(
        "origin pr list --head stack/open --state all --json number,status,headRef,baseRef failed"
      );
      expect(await readFile(join(directory, "frontier.json"), "utf8")).toBe(saved);
    } });
  });

  it("records each Origin branch tip even when a same-named tag points elsewhere", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);
    for (const branch of ["stack/merged", "stack/closed", "stack/open", "stack/draft"]) {
      git({ repo: stack.repo, args: ["tag", branch, "main"] });
    }

    await withFakeOrigin({
      directory,
      operation: async () => {
        const frontier = await store.frontier.set({ repo: stack.repo, forge: "origin" });
        expect(frontier.prs.map((row) => row.sha)).toEqual([
          stack.mergedSha,
          stack.closedSha,
          stack.openSha,
          stack.draftSha,
        ]);
      },
    });
  });

  it("does not need a local branch for a merged or closed Origin ancestor", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);
    git({ repo: stack.repo, args: ["branch", "-D", "stack/merged", "stack/closed"] });

    await withFakeOrigin({
      directory,
      operation: async () => {
        expect(
          await store.frontier.set({ repo: stack.repo, forge: "origin" })
        ).toEqual({
          generation: 1,
          prs: [
            { pr: 10, branches: "stack/merged", sha: "", state: "MERGED" },
            { pr: 13, branches: "stack/closed", sha: "", state: "CLOSED" },
            { pr: 11, branches: "stack/open", sha: stack.openSha, state: "OPEN" },
            { pr: 14, branches: "stack/draft", sha: stack.draftSha, state: "OPEN" },
          ],
          lowestUnmerged: 11,
        });
      },
    });
  });

  it("names the missing local branch when an open Origin pull request has none", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);
    git({ repo: stack.repo, args: ["branch", "-D", "stack/draft"] });

    await withFakeOrigin({
      directory,
      operation: async () => {
        await expect(
          store.frontier.set({ repo: stack.repo, forge: "origin" })
        ).rejects.toThrow("branch stack/draft has no local ref refs/heads/stack/draft");
        expect(await readFile(join(directory, "frontier.json"), "utf8")).toBe("{}\n");
      },
    });
  });

  it("rejects Origin chains that loop, branch, repeat a head, or repeat a pull request", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);
    const draft = { number: 14, state: "draft", head: "stack/draft", base: "stack/open" } as const;
    const cases = [
      {
        route: { filter: "--head", branch: "stack/merged" },
        rows: [{ number: 10, state: "merged", head: "stack/merged", base: "stack/open" }],
        error: "pull request base chain loops at branch stack/open",
      },
      {
        route: { filter: "--base", branch: "stack/open" },
        rows: [{ number: 10, state: "open", head: "stack/merged", base: "stack/open" }],
        error: "pull request base chain loops at branch stack/merged",
      },
      {
        route: { filter: "--base", branch: "stack/open" },
        rows: [draft, { number: 16, state: "open", head: "stack/sibling", base: "stack/open" }],
        error: "stack is not linear: branches stack/draft, stack/sibling all target stack/open",
      },
      {
        route: { filter: "--head", branch: "stack/open" },
        rows: [
          { number: 11, state: "open", head: "stack/open", base: "stack/closed" },
          { number: 12, state: "closed", head: "stack/open", base: "stack/closed" },
        ],
        error: "branch stack/open has multiple pull requests (#11, #12); close the stale ones first",
      },
      {
        route: { filter: "--head", branch: "stack/closed" },
        rows: [
          { number: 13, state: "closed", head: "stack/closed", base: "stack/merged" },
          { number: 17, state: "open", head: "stack/closed", base: "stack/merged" },
        ],
        error: "branch stack/closed has multiple pull requests (#13, #17)",
      },
      {
        route: { filter: "--base", branch: "stack/open" },
        rows: [{ ...draft, number: 11 }],
        error: "pull request base chain contains duplicate pull requests",
      },
    ] as const;

    await withFakeOrigin({
      directory,
      operation: async () => {
        for (const { route, rows, error } of cases) {
          await overrideOriginRoute({ directory, ...route, rows: originRows(rows) });
          await expect(
            store.frontier.set({ repo: stack.repo, forge: "origin" })
          ).rejects.toThrow(error);
          expect(await readFile(join(directory, "frontier.json"), "utf8")).toBe("{}\n");
          await rm(join(directory, "origin-routes"), { recursive: true, force: true });
        }
      },
    });
  });

  it("reaches the Origin forge only through --forge origin on the CLI", async () => {
    const { directory } = await initializedStore();
    const stack = await makeGitStack(directory);
    const storeDirectory = await makeDirectory();

    await withFakeOrigin({
      directory,
      operation: async () => {
        expect(runCli(["--store", storeDirectory, "init"]).code).toBe(0);
        const result = runCli([
          "--store",
          storeDirectory,
          "--json",
          "frontier",
          "set",
          "--repo",
          stack.repo,
          "--forge",
          "origin",
        ]);
        expect(result.stderr).toBe("");
        expect(result.code).toBe(0);
        expect(JSON.parse(result.stdout)).toEqual({
          generation: 1,
          prs: [
            { pr: 10, branches: "stack/merged", sha: stack.mergedSha, state: "MERGED" },
            { pr: 13, branches: "stack/closed", sha: stack.closedSha, state: "CLOSED" },
            { pr: 11, branches: "stack/open", sha: stack.openSha, state: "OPEN" },
            { pr: 14, branches: "stack/draft", sha: stack.draftSha, state: "OPEN" },
          ],
          lowestUnmerged: 11,
        });
      },
    });
  });

  it("keeps gh as the default forge on the CLI even when an origin binary is on PATH", async () => {
    const { directory } = await initializedStore();
    const stack = await makeGitStack(directory);
    const storeDirectory = await makeDirectory();
    const decoy = join(directory, "decoy-bin");
    await mkdir(decoy);
    await writeFile(
      join(decoy, "origin"),
      `#!/usr/bin/env bash
printf 'origin must not run without --forge origin\\n' >&2
exit 2
`
    );
    await chmod(join(decoy, "origin"), 0o755);

    await withFakeGithub({
      directory,
      output: JSON.stringify([
        {
          number: 11,
          state: "OPEN",
          headRefName: "stack/open",
          headRefOid: stack.openSha,
          baseRefName: "main",
          isCrossRepository: false,
        },
      ]),
      operation: async () => {
        const originalPath = process.env.PATH;
        process.env.PATH = `${decoy}:${originalPath ?? ""}`;
        try {
          expect(runCli(["--store", storeDirectory, "init"]).code).toBe(0);
          const result = runCli([
            "--store",
            storeDirectory,
            "--json",
            "frontier",
            "set",
            "--repo",
            stack.repo,
          ]);
          expect(result.stderr).toBe("");
          expect(result.code).toBe(0);
          expect(JSON.parse(result.stdout).prs).toEqual([
            { pr: 11, branches: "stack/open", sha: stack.openSha, state: "OPEN" },
          ]);
        } finally {
          process.env.PATH = originalPath;
        }
      },
    });
  });

  it("refuses an Origin frontier from the trunk branch instead of recording an empty one", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);
    git({ repo: stack.repo, args: ["checkout", "main"] });

    await withFakeOrigin({
      directory,
      operation: async () => {
        await expect(
          store.frontier.set({ repo: stack.repo, forge: "origin" })
        ).rejects.toThrow(
          "found no PR for checked out branch main"
        );
        expect(await readFile(join(directory, "frontier.json"), "utf8")).toBe("{}\n");
      },
    });
  });

  it("reports a missing origin CLI before the trunk branch can short-circuit", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);
    git({ repo: stack.repo, args: ["checkout", "main"] });

    await withoutGtOrGh({
      directory,
      operation: async () => {
        const failure = await store.frontier
          .set({ repo: stack.repo, forge: "origin" })
          .then(
            () => undefined,
            (error: unknown) => error
          );
        expect(failure).toBeInstanceOf(UsageError);
        expect((failure as Error).message).toContain(
          "--forge origin requires the origin CLI"
        );
      },
    });
  });

  it("rejects combining Graphite discovery with the Origin forge", async () => {
    const { directory, store } = await initializedStore();
    const stack = await makeGitStack(directory);
    await expect(
      store.frontier.set({ repo: stack.repo, discovery: "graphite", forge: "origin" })
    ).rejects.toBeInstanceOf(UsageError);
  });

  it("rejects malformed TSV, verdict, frontier, and inbox data", async () => {
    const { directory, store } = await initializedStore();

    await writeFile(join(directory, "units.tsv"), "wrong\n");
    await expect(store.units.list()).rejects.toThrow(
      "units.tsv has an invalid header"
    );
    await writeFile(
      join(directory, "units.tsv"),
      "id\ttrack\tstate\tbranch\tpr\tsha\tbrief\nshort\trow\n"
    );
    await expect(store.units.list()).rejects.toThrow(
      "units.tsv has a malformed row"
    );

    await writeFile(
      join(directory, "ledger.tsv"),
      "pr\tsha\tverdict\tevidence\tverifier\tts\n1\tsha\tinvalid\treport\tme\tnow\n"
    );
    await expect(store.ledger.summary()).rejects.toThrow(
      "ledger.tsv has invalid verdict invalid"
    );

    await writeFile(join(directory, "frontier.json"), '{"generation":"1"}\n');
    await expect(store.frontier.show()).rejects.toThrow(
      "frontier.json has an invalid shape"
    );

    await writeFile(join(directory, "inbox", "bad.tsv"), "too\tshort\n");
    await expect(store.inbox.peek()).rejects.toThrow(
      "inbox pointer bad.tsv is malformed"
    );
  });

  it("rejects operations after close", async () => {
    const { store } = await initializedStore();
    await store.close();
    await expect(store.units.list()).rejects.toThrow("store is closed");
    await expect(store.status.render()).rejects.toBeInstanceOf(UserError);
  });
});

describe("orch CLI", () => {
  it("prints commander help and rejects invalid parsing with exit 1", async () => {
    const help = runCli(["--help"]);
    expect(help.code).toBe(0);
    expect(help.stdout).toContain("Commands:");
    expect(help.stdout).toContain("unit");
    expect(help.stdout).toContain("ledger");

    const frontierHelp = runCli(["frontier", "set", "--help"]);
    expect(frontierHelp.code).toBe(0);
    expect(frontierHelp.stdout).toContain("--repo <dir>");
    expect(frontierHelp.stdout).toContain("--prs <n,...>");
    expect(frontierHelp.stdout).toContain("--graphite");
    expect(frontierHelp.stdout).toContain("--forge <forge>");

    const directory = await makeDirectory();
    const invalid = runCli(["--store", directory, "unit", "add", "u1"]);
    expect(invalid.code).toBe(1);
    expect(invalid.stderr).toContain("required option '--track <track>'");

    const badForge = runCli([
      "--store",
      directory,
      "frontier",
      "set",
      "--repo",
      directory,
      "--forge",
      "gt",
    ]);
    expect(badForge.code).toBe(1);
    expect(badForge.stderr).toContain("Allowed choices are gh, origin");

    const conflicting = runCli([
      "--store",
      directory,
      "frontier",
      "set",
      "--repo",
      directory,
      "--graphite",
      "--forge",
      "origin",
    ]);
    expect(conflicting.code).toBe(1);
    expect(conflicting.stderr).toContain("cannot be used with option '--forge <forge>'");
  });

  it("accepts ORCH_STORE and emits complete JSON", async () => {
    const directory = await makeDirectory();
    const env = { ...process.env, ORCH_STORE: directory };
    expect(runCli(["init"], env).code).toBe(0);

    const added = runCli(
      ["unit", "add", "u1", "--track", "build", "--json"],
      env
    );
    expect(added.code).toBe(0);
    expect(JSON.parse(added.stdout)).toEqual({
      id: "u1",
      track: "build",
      state: "pending",
      branch: "",
      pr: "",
      sha: "",
      brief: "",
    });
  });

  it("maps user and not-found outcomes to the preserved exit codes", async () => {
    const directory = await makeDirectory();
    expect(runCli(["--store", directory, "init"]).code).toBe(0);

    const missingRepo = runCli([
      "--store",
      directory,
      "frontier",
      "set",
    ]);
    expect(missingRepo.code).toBe(1);
    expect(missingRepo.stderr).toContain(
      "set --repo <dir> or ORCH_REPO"
    );

    const userError = runCli([
      "--store",
      directory,
      "unit",
      "add",
      "",
      "--track",
      "build",
    ]);
    expect(userError.code).toBe(1);
    expect(userError.stderr).toContain("unit id must not be empty");

    const missingUnit = runCli([
      "--store",
      directory,
      "unit",
      "get",
      "missing",
    ]);
    expect(missingUnit.code).toBe(2);
    expect(missingUnit.stderr).toContain("unit missing not found");

    const missingLedger = runCli([
      "--store",
      directory,
      "--json",
      "ledger",
      "check",
      "184530",
      "abc123",
    ]);
    expect(missingLedger.code).toBe(2);
    expect(JSON.parse(missingLedger.stdout)).toEqual({
      pr: "184530",
      sha: "abc123",
      verdict: "NOT-VERIFIED",
    });
    expect(missingLedger.stderr).toBe("");
  });
});
