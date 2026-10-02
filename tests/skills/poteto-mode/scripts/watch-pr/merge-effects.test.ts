import { describe, expect, it } from "bun:test";
import {
  chmodSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  REVIEW_CONNECTION_LIMITS,
  REVIEW_THREADS_QUERY,
} from "../../../../../skills/poteto-mode/scripts/watch-pr/github.ts";
import { parseConversation } from "../../../../../skills/poteto-mode/scripts/watch-pr/merge-effects.ts";

const SOURCE_DIR = join(
  import.meta.dir,
  "../../../../../skills/poteto-mode/scripts/watch-pr"
);
const decode = (bytes: Uint8Array): string => new TextDecoder().decode(bytes);

function git(cwd: string, ...args: string[]): string {
  const result = Bun.spawnSync(
    [
      "git",
      "-c",
      "user.name=t",
      "-c",
      "user.email=t@example.com",
      "-c",
      "commit.gpgsign=false",
      ...args,
    ],
    {
      cwd,
      env: { ...process.env, GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_SYSTEM: "/dev/null" },
    }
  );
  if (result.exitCode !== 0) throw new Error(decode(result.stderr));
  return decode(result.stdout).trim();
}
function commitFile(cwd: string, name: string, text: string): string {
  writeFileSync(join(cwd, name), text);
  git(cwd, "add", name);
  git(cwd, "commit", "-m", `edit ${name}`);
  return git(cwd, "rev-parse", "HEAD");
}

function portScript(body: string): string {
  return `import { GhGitMergePort } from ${JSON.stringify(join(SOURCE_DIR, "merge-effects.ts"))}; import { parseCommitSha } from ${JSON.stringify(join(SOURCE_DIR, "verdict.ts"))}; import { parsePrNumber } from ${JSON.stringify(join(SOURCE_DIR, "types.ts"))}; const port = new GhGitMergePort(); const context = { host: "github.com", owner: "o", repo: "r", number: parsePrNumber(7) }; try { ${body} } catch (error) { console.log(JSON.stringify({ error: error.message, source: error.source })); }`;
}
function runPort(
  cwd: string,
  body: string,
  path = process.env.PATH ?? ""
): any {
  const result = Bun.spawnSync([process.execPath, "-e", portScript(body)], {
    cwd,
    env: { ...process.env, PATH: path },
  });
  if (result.exitCode !== 0) throw new Error(decode(result.stderr));
  return JSON.parse(decode(result.stdout));
}

describe("GhGitMergePort.patchId against a real repository", () => {
  function scenario(): {
    readonly work: string;
    readonly head: string;
    readonly cleanup: () => void;
  } {
    const root = mkdtempSync(join(tmpdir(), "merge-gate-git-"));
    const origin = join(root, "origin.git");
    const work = join(root, "work");
    mkdirSync(origin);
    git(origin, "init", "--bare", "--initial-branch=main");
    git(root, "clone", origin, "work");
    git(work, "checkout", "-b", "main");
    commitFile(work, "a.txt", "one\ntwo\n");
    git(work, "push", "origin", "main");
    git(work, "checkout", "-b", "feature");
    const head = commitFile(work, "a.txt", "one\ntwo\nthree\n");
    git(work, "push", "origin", "feature");
    git(work, "checkout", "main");
    commitFile(work, "unrelated.txt", "base moved on\n");
    git(work, "push", "origin", "main");
    git(work, "checkout", "feature");
    return { work, head, cleanup: () => rmSync(root, { recursive: true, force: true }) };
  }

  it("hashes the diff against the freshly fetched base, ignoring base movement", () => {
    const { work, head, cleanup } = scenario();
    try {
      const out = runPort(
        work,
        `console.log(JSON.stringify({ id: await port.patchId("main", parseCommitSha(${JSON.stringify(head)}))}));`
      );
      expect(out).toEqual({ id: "e1a9243ae8a08b53e41d07c7bb3ca3a48104a3d9" });
    } finally {
      cleanup();
    }
  });

  it("gives a different patch-id once the head carries a different change", () => {
    const { work, head, cleanup } = scenario();
    try {
      const moved = commitFile(work, "a.txt", "one\ntwo\nthree\nfour\n");
      git(work, "push", "origin", "feature");
      const out = runPort(
        work,
        `console.log(JSON.stringify({ id: await port.patchId("main", parseCommitSha(${JSON.stringify(moved)}))}));`
      );
      expect(out.id).not.toBe("e1a9243ae8a08b53e41d07c7bb3ca3a48104a3d9");
      expect(head).not.toBe(moved);
    } finally {
      cleanup();
    }
  });

  it("names a git failure when the head cannot be fetched", () => {
    const { work, cleanup } = scenario();
    try {
      const missing = "9".repeat(40);
      const out = runPort(
        work,
        `await port.patchId("main", parseCommitSha(${JSON.stringify(missing)}));`
      );
      expect(out.source).toBe("git");
      expect(out.error).toStartWith(`git fetch origin main ${missing} failed:`);
    } finally {
      cleanup();
    }
  });
});

describe("GhGitMergePort.patchId with binary files", () => {
  function plainPatchId(cwd: string, range: string): string {
    const diff = Bun.spawnSync(["git", "diff", range], { cwd });
    const hashed = Bun.spawnSync(["git", "patch-id", "--stable"], {
      cwd,
      stdin: diff.stdout,
    });
    return decode(hashed.stdout).split(" ")[0] ?? "";
  }
  function viaPort(cwd: string, head: string): string {
    return runPort(
      cwd,
      `console.log(JSON.stringify({ id: await port.patchId("main", parseCommitSha(${JSON.stringify(head)}))}));`
    ).id;
  }
  function writeBinary(cwd: string, bytes: number[]): void {
    writeFileSync(join(cwd, "image.bin"), Uint8Array.from(bytes));
    git(cwd, "add", "image.bin");
    git(cwd, "commit", "-m", "binary");
  }

  it("tells apart two different binary contents at the same path", () => {
    const root = mkdtempSync(join(tmpdir(), "merge-gate-bin-"));
    try {
      const origin = join(root, "origin.git");
      const work = join(root, "work");
      mkdirSync(origin);
      git(origin, "init", "--bare", "--initial-branch=main");
      git(root, "clone", origin, "work");
      git(work, "checkout", "-b", "main");
      writeBinary(work, [0, 1, 2, 3]);
      git(work, "push", "origin", "main");
      git(work, "checkout", "-b", "first");
      writeBinary(work, [0, 9, 9, 9]);
      const first = git(work, "rev-parse", "HEAD");
      git(work, "push", "origin", "first");
      git(work, "checkout", "main");
      git(work, "checkout", "-b", "second");
      writeBinary(work, [0, 7, 7, 7]);
      const second = git(work, "rev-parse", "HEAD");
      git(work, "push", "origin", "second");
      expect(viaPort(work, first)).not.toBe(viaPort(work, second));
      expect(viaPort(work, first)).toBe(plainPatchId(work, `main...${first}`));
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("keeps a text-only change at the patch-id plain git diff gives", () => {
    const root = mkdtempSync(join(tmpdir(), "merge-gate-text-"));
    try {
      const origin = join(root, "origin.git");
      const work = join(root, "work");
      mkdirSync(origin);
      git(origin, "init", "--bare", "--initial-branch=main");
      git(root, "clone", origin, "work");
      git(work, "checkout", "-b", "main");
      commitFile(work, "a.txt", "one\ntwo\n");
      git(work, "push", "origin", "main");
      git(work, "checkout", "-b", "feature");
      const head = commitFile(work, "a.txt", "one\ntwo\nthree\n");
      git(work, "push", "origin", "feature");
      expect(viaPort(work, head)).toBe(plainPatchId(work, `main...${head}`));
      expect(viaPort(work, head)).toBe("e1a9243ae8a08b53e41d07c7bb3ca3a48104a3d9");
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});

describe("GhGitMergePort gh commands", () => {
  function withFakeGh<T>(
    script: string,
    use: (path: string, argvLog: () => string[]) => T
  ): T {
    const directory = mkdtempSync(join(tmpdir(), "merge-gate-gh-"));
    try {
      const log = join(directory, "argv");
      writeFileSync(join(directory, "gh"), `#!/bin/sh\nprintf '%s\\n' '---' "$@" >> '${log}'\n${script}\n`);
      chmodSync(join(directory, "gh"), 0o755);
      return use(`${directory}:${process.env.PATH ?? ""}`, () => {
        try {
          return readFileSync(log, "utf8").trimEnd().split("\n");
        } catch {
          return [];
        }
      });
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  }
  const HEAD = "a1".repeat(20);

  it("squash-merges pinned to the head commit with the exact subject and body file", () => {
    withFakeGh(
      `case "$2" in view) printf '%s\\n' '{"state":"MERGED","mergedAt":"2026-10-02T17:00:00Z","mergeCommit":{"oid":"${"e5".repeat(20)}"}}';; esac`,
      (path, argv) => {
        const out = runPort(
          process.cwd(),
          `console.log(JSON.stringify(await port.merge({ context, headSha: parseCommitSha(${JSON.stringify(HEAD)}), subject: "fix(x): land (#7)", bodyFile: "/tmp/b.md" })));`,
          path
        );
        expect(out).toEqual({ kind: "merged", mergeCommit: "e5".repeat(20) });
        expect(argv().slice(0, 14)).toEqual([
          "---",
          "pr",
          "merge",
          "7",
          "--repo",
          "o/r",
          "--squash",
          "--match-head-commit",
          HEAD,
          "--subject",
          "fix(x): land (#7)",
          "--body-file",
          "/tmp/b.md",
          "---",
        ]);
      }
    );
  });

  it("reports a queued PR as pending, never merged", () => {
    withFakeGh(
      `case "$2" in view) printf '%s\\n' '{"state":"OPEN","mergedAt":null,"mergeCommit":null}';; esac`,
      (path) => {
        const out = runPort(
          process.cwd(),
          `console.log(JSON.stringify(await port.merge({ context, headSha: parseCommitSha(${JSON.stringify(HEAD)}), subject: "s", bodyFile: "/tmp/b.md" })));`,
          path
        );
        expect(out).toEqual({ kind: "pending", mergeCommit: null, observed: "state=OPEN" });
      }
    );
  });

  it("reports pending when the follow-up read fails, because the merge is unconfirmed", () => {
    withFakeGh(`case "$2" in view) echo 'HTTP 502' >&2; exit 1;; esac`, (path) => {
      const out = runPort(
        process.cwd(),
        `console.log(JSON.stringify(await port.merge({ context, headSha: parseCommitSha(${JSON.stringify(HEAD)}), subject: "s", bodyFile: "/tmp/b.md" })));`,
        path
      );
      expect(out.kind).toBe("pending");
      expect(out.observed).toStartWith("could not confirm the merge:");
    });
  });

  it("names the gh failure when the merge is refused", () => {
    withFakeGh(
      `case "$2" in merge) echo 'Head branch was modified' >&2; exit 1;; esac`,
      (path) => {
        const out = runPort(
          process.cwd(),
          `await port.merge({ context, headSha: parseCommitSha(${JSON.stringify(HEAD)}), subject: "s", bodyFile: "/tmp/b.md" });`,
          path
        );
        expect(out).toEqual({
          error: "gh pr merge failed: Head branch was modified",
          source: "gh",
        });
      }
    );
  });

  it("posts the comment body verbatim", () => {
    withFakeGh("", (path, argv) => {
      runPort(
        process.cwd(),
        `await port.comment(context, "merge-gate override: why\\n\\n- verdict: no verdict block"); console.log("{}");`,
        path
      );
      expect(argv()).toEqual([
        "---",
        "pr",
        "comment",
        "7",
        "--repo",
        "o/r",
        "--body",
        "merge-gate override: why",
        "",
        "- verdict: no verdict block",
      ]);
    });
  });
});

describe("parseConversation truncation", () => {
  const page = (counts: Record<string, number>) => ({
    data: {
      repository: {
        pullRequest: {
          author: { login: "a" },
          comments: { totalCount: counts.comments ?? 0, nodes: [] },
          reviewThreads: { totalCount: counts.reviewThreads ?? 0 },
          reviewRequests: { totalCount: counts.reviewRequests ?? 0 },
          reviews: { totalCount: counts.reviews ?? 0 },
        },
      },
    },
  });

  it("reports each connection whose total exceeds what the reads fetch", () => {
    expect(
      parseConversation(
        page({ reviewThreads: 101, reviewRequests: 51, reviews: 101, comments: 101 })
      ).truncated
    ).toEqual([
      { connection: "reviewThreads", total: 101, limit: 100 },
      { connection: "reviewRequests", total: 51, limit: 50 },
      { connection: "reviews", total: 101, limit: 100 },
      { connection: "comments", total: 101, limit: 100 },
    ]);
  });

  it("reports nothing at exactly the limit", () => {
    expect(
      parseConversation(
        page({ reviewThreads: 100, reviewRequests: 50, reviews: 100, comments: 100 })
      ).truncated
    ).toEqual([]);
  });

  it("uses the same limits as the watcher's review query", () => {
    expect(REVIEW_THREADS_QUERY).toContain("reviewThreads(first: 100)");
    expect(REVIEW_THREADS_QUERY).toContain("reviewRequests(first: 50)");
    expect(REVIEW_THREADS_QUERY).toContain("reviews(last: 100)");
    expect(REVIEW_THREADS_QUERY).toContain("comments(last: 100)");
    expect(REVIEW_CONNECTION_LIMITS).toEqual({
      reviewThreads: 100,
      reviewRequests: 50,
      reviews: 100,
      comments: 100,
    });
  });
});

describe("parseConversation", () => {
  it("keeps createdAt and association, and drops comments from deleted accounts", () => {
    const conversation = parseConversation({
      data: {
        repository: {
          pullRequest: {
            author: { login: "mdsmithaustin" },
            reviewThreads: { totalCount: 0 },
            reviewRequests: { totalCount: 0 },
            reviews: { totalCount: 0 },
            comments: {
              totalCount: 2,
              nodes: [
                {
                  body: "Verdict: PASS",
                  url: "https://github.com/o/r/pull/7#issuecomment-1",
                  createdAt: "2026-10-02T11:00:00Z",
                  authorAssociation: "OWNER",
                  author: { login: "mdsmithaustin", __typename: "User" },
                },
                {
                  body: "ghost",
                  url: "https://github.com/o/r/pull/7#issuecomment-2",
                  createdAt: "2026-10-02T11:01:00Z",
                  authorAssociation: "NONE",
                  author: null,
                },
              ],
            },
          },
        },
      },
    });
    expect(conversation).toEqual({
      prAuthor: "mdsmithaustin",
      truncated: [],
      comments: [
        {
          url: "https://github.com/o/r/pull/7#issuecomment-1",
          createdAt: "2026-10-02T11:00:00Z",
          author: { login: "mdsmithaustin", isBot: false },
          association: "OWNER",
          body: "Verdict: PASS",
        },
      ],
    });
  });
});
