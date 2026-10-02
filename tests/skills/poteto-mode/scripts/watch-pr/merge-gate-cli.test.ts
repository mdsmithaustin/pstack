import { describe, expect, it } from "bun:test";
import {
  main,
  parseArgs,
} from "../../../../../skills/poteto-mode/scripts/watch-pr/merge-gate-cli.ts";
import { MergeGateError } from "../../../../../skills/poteto-mode/scripts/watch-pr/merge-gate.ts";
import {
  CONTEXT,
  HEAD,
  MOVED_HEAD,
  OTHER_PATCH,
  PATCH,
  failureThrownByGitHub,
  issueComment,
  testRuntime,
  unresolvedThread,
  verdictBody,
  world,
  type WorldOptions,
} from "./merge-gate-fakes.test-helper.ts";
import type { GitHubReader } from "../../../../../skills/poteto-mode/scripts/watch-pr/types.ts";

const MERGE_ARGS = [
  "--owner",
  "owner",
  "--repo",
  "repo",
  "--pr",
  "1",
  "--subject",
  "fix(x): land it (#1)",
  "--body-file",
  "/tmp/body.md",
];

async function run(
  argv: readonly string[],
  options: WorldOptions = {},
  extra: { readonly bodyFileReadable?: boolean } = {}
) {
  const built = world(options);
  const harness = testRuntime({ ...built, ...extra });
  const exitCode = await main(argv, harness.runtime);
  return { exitCode, ...harness, port: built.port };
}
const mergeCalls = (port: ReturnType<typeof world>["port"]) =>
  port.calls.flatMap((call) => (call.kind === "merge" ? [call.request] : []));
const commentCalls = (port: ReturnType<typeof world>["port"]) =>
  port.calls.flatMap((call) => (call.kind === "comment" ? [call.body] : []));
const parsed = (stdout: readonly string[]): any => JSON.parse(stdout.join(""));

const brokenWorld: WorldOptions = {
  threads: [unresolvedThread()],
  port: { comments: [] },
};

describe("merge-gate", () => {
  it("merges a ready PR with the head match, subject and body file, and prints a receipt", async () => {
    const result = await run(MERGE_ARGS);
    expect(result.exitCode).toBe(0);
    expect(mergeCalls(result.port)).toEqual([
      {
        context: CONTEXT,
        headSha: HEAD,
        subject: "fix(x): land it (#1)",
        bodyFile: "/tmp/body.md",
      },
    ]);
    const out = parsed(result.stdout);
    expect(out).toMatchObject({
      schemaVersion: 1,
      kind: "MERGED",
      override: null,
      receipt: {
        pr: 1,
        mergeCommit: "e5".repeat(20),
        head: HEAD,
        patchId: PATCH,
        verdictUrl: expect.stringContaining("issuecomment-"),
      },
    });
  });

  it("prints a one-line receipt in pretty mode", async () => {
    const result = await run([...MERGE_ARGS, "--pretty"]);
    const text = result.stdout.join("");
    expect(text.trimEnd().split("\n")).toHaveLength(1);
    expect(text).toContain(`MERGED: pr=#1 commit=${"e5".repeat(20)} head=${HEAD}`);
    expect(text).toContain(`patch-id=${PATCH}`);
  });

  it("refuses an unready PR, merges nothing, and exits 10 naming every failing gate", async () => {
    const result = await run(MERGE_ARGS, brokenWorld);
    expect(result.exitCode).toBe(10);
    expect(mergeCalls(result.port)).toEqual([]);
    expect(commentCalls(result.port)).toEqual([]);
    const out = parsed(result.stdout);
    expect(out.kind).toBe("REFUSED");
    expect(out.report.ready).toBe(false);
    expect(
      out.report.gates
        .filter((gate: { ok: boolean }) => !gate.ok)
        .map((gate: { gate: string }) => gate.gate)
    ).toEqual(["verdict", "head", "patch-id", "threads"]);
  });

  it("renders failing gates as human text with --pretty", async () => {
    const result = await run([...MERGE_ARGS, "--pretty"], brokenWorld);
    expect(result.exitCode).toBe(10);
    const text = result.stdout.join("");
    expect(text).toContain("REFUSED: pr=#1 NOT READY");
    expect(text).toContain("FAIL verdict: no verdict block");
    expect(text).toContain("FAIL threads: 1 unresolved review thread");
    expect(text).toContain("ok   draft:");
  });

  it("refuses when the head moved after the verdict, on both head and patch-id", async () => {
    const result = await run(MERGE_ARGS, {
      facts: { headRefOid: MOVED_HEAD },
      port: { patchId: OTHER_PATCH },
    });
    expect(result.exitCode).toBe(10);
    expect(mergeCalls(result.port)).toEqual([]);
    const failed = parsed(result.stdout).report.gates.filter(
      (gate: { ok: boolean }) => !gate.ok
    );
    expect(failed.map((gate: { gate: string }) => gate.gate)).toEqual([
      "head",
      "patch-id",
    ]);
  });

  describe("a merge that only enqueues", () => {
    const pending = { kind: "pending", mergeCommit: null, observed: "state=OPEN" } as const;

    it("reports QUEUED with exit 11, never MERGED", async () => {
      const result = await run(MERGE_ARGS, { port: { receipt: pending } });
      expect(result.exitCode).toBe(11);
      expect(mergeCalls(result.port)).toHaveLength(1);
      expect(parsed(result.stdout)).toMatchObject({
        kind: "QUEUED",
        exitCode: 11,
        note: "PR is not merged yet (state=OPEN)",
        override: null,
        receipt: { pr: 1, mergeCommit: null, head: HEAD, patchId: PATCH },
      });
    });

    it("says so in pretty mode, on one line", async () => {
      const result = await run([...MERGE_ARGS, "--pretty"], { port: { receipt: pending } });
      const text = result.stdout.join("");
      expect(text.trimEnd().split("\n")).toHaveLength(1);
      expect(text).toContain("QUEUED: pr=#1 commit=unknown");
      expect(text).toContain("not merged yet");
      expect(text).not.toContain("MERGED:");
    });

    it("stays QUEUED under --override and keeps the reason", async () => {
      const result = await run([...MERGE_ARGS, "--override", "owner call"], {
        ...brokenWorld,
        port: { comments: [], receipt: pending },
      });
      expect(result.exitCode).toBe(11);
      expect(parsed(result.stdout)).toMatchObject({ kind: "QUEUED", override: "owner call" });
    });
  });

  describe("--check", () => {
    it("prints the report and exits 0 for a ready PR without merging", async () => {
      const result = await run([...MERGE_ARGS, "--check"]);
      expect(result.exitCode).toBe(0);
      expect(mergeCalls(result.port)).toEqual([]);
      expect(parsed(result.stdout)).toMatchObject({
        kind: "CHECK",
        report: { ready: true },
      });
    });

    it("exits 10 for an unready PR", async () => {
      const result = await run([...MERGE_ARGS, "--check"], brokenWorld);
      expect(result.exitCode).toBe(10);
      expect(mergeCalls(result.port)).toEqual([]);
      expect(commentCalls(result.port)).toEqual([]);
    });

    it("needs neither a subject nor a body file", async () => {
      const result = await run(["--pr", "1", "--check"]);
      expect(result.exitCode).toBe(0);
    });
  });

  describe("--override", () => {
    it("posts the reason and the failed gates, then merges on the same head match", async () => {
      const result = await run(
        [...MERGE_ARGS, "--override", "owner approved the stale verdict"],
        brokenWorld
      );
      expect(result.exitCode).toBe(0);
      const [body] = commentCalls(result.port);
      expect(body?.split("\n")[0]).toBe(
        "merge-gate override: owner approved the stale verdict"
      );
      expect(body).toContain("- verdict: no verdict block");
      expect(body).toContain("- threads: 1 unresolved review thread");
      expect(body).not.toContain("- draft:");
      expect(mergeCalls(result.port).map((request) => request.headSha)).toEqual([HEAD]);
      const kinds = result.port.calls.map((call) => call.kind);
      expect(kinds.indexOf("comment")).toBeLessThan(kinds.indexOf("merge"));
      expect(parsed(result.stdout)).toMatchObject({
        kind: "MERGED",
        override: "owner approved the stale verdict",
      });
    });

    it("does not comment when every gate already holds", async () => {
      const result = await run([...MERGE_ARGS, "--override", "belt and braces"]);
      expect(result.exitCode).toBe(0);
      expect(commentCalls(result.port)).toEqual([]);
      expect(mergeCalls(result.port)).toHaveLength(1);
    });

    it("refuses an empty or blank reason as a usage error", async () => {
      for (const reason of ["", "   "]) {
        const result = await run([...MERGE_ARGS, "--override", reason]);
        expect(result.exitCode).toBe(64);
        expect(result.port.calls).toEqual([]);
        expect(result.stderr.join("")).toContain("--override");
      }
    });

    it("will not override a PR that is already merged", async () => {
      const result = await run(
        [...MERGE_ARGS, "--override", "try anyway"],
        { facts: { state: "MERGED", mergedAt: "2026-10-02T16:14:32Z" } }
      );
      expect(result.exitCode).toBe(10);
      expect(commentCalls(result.port)).toEqual([]);
      expect(mergeCalls(result.port)).toEqual([]);
      expect(parsed(result.stdout)).toMatchObject({
        kind: "REFUSED",
        note: "override refused: PR is MERGED",
      });
    });

    it("cannot be combined with --check", async () => {
      const result = await run([...MERGE_ARGS, "--check", "--override", "why"]);
      expect(result.exitCode).toBe(64);
    });
  });

  describe("usage", () => {
    it("exits 64 for missing or malformed arguments", async () => {
      const subjectless = ["--pr", "1", "--body-file", "/tmp/body.md"];
      const bodyless = ["--pr", "1", "--subject", "s"];
      for (const argv of [
        [],
        ["--pr", "0", "--check"],
        ["--pr", "x", "--check"],
        ["--check"],
        subjectless,
        bodyless,
        [...MERGE_ARGS, "--bogus"],
        [...MERGE_ARGS.slice(0, -4), "--subject", "  ", "--body-file", "/tmp/b"],
      ]) {
        const result = await run(argv);
        expect(result.exitCode).toBe(64);
        expect(result.port.calls).toEqual([]);
        expect(result.stdout).toEqual([]);
      }
    });

    it("exits 64 when the body file is not readable, before any merge", async () => {
      const result = await run(MERGE_ARGS, {}, { bodyFileReadable: false });
      expect(result.exitCode).toBe(64);
      expect(result.stderr.join("")).toContain("/tmp/body.md");
      expect(mergeCalls(result.port)).toEqual([]);
    });

    it("parses the documented flags", () => {
      expect(
        parseArgs(
          [...MERGE_ARGS, "--override", "r", "--pretty"],
          { stdout: () => {}, stderr: () => {} }
        )
      ).toMatchObject({
        owner: "owner",
        repo: "repo",
        pr: 1,
        pretty: true,
        action: {
          kind: "merge",
          subject: "fix(x): land it (#1)",
          bodyFile: "/tmp/body.md",
          override: "r",
        },
      });
    });
  });

  describe("query errors", () => {
    it("exits 1 naming the GitHub failure and merges nothing", async () => {
      const built = world();
      const failing: GitHubReader = {
        ...built.reader,
        async pullRequest() {
          throw failureThrownByGitHub;
        },
      };
      const harness = testRuntime({ reader: failing, port: built.port });
      expect(await main(MERGE_ARGS, harness.runtime)).toBe(1);
      expect(parsed(harness.stdout)).toMatchObject({
        kind: "ERROR",
        source: "github",
        detail: "gh: HTTP 502",
      });
      expect(mergeCalls(built.port)).toEqual([]);
    });

    it("exits 1 naming the git failure and merges nothing", async () => {
      const result = await run(MERGE_ARGS, {
        port: {
          patchIdError: new MergeGateError("git", "git fetch origin main failed: no network"),
        },
      });
      expect(result.exitCode).toBe(1);
      expect(parsed(result.stdout)).toMatchObject({
        kind: "ERROR",
        source: "git",
        detail: "git fetch origin main failed: no network",
      });
      expect(mergeCalls(result.port)).toEqual([]);
    });

    it("exits 1 when gh refuses the merge, for example because the head moved", async () => {
      const result = await run(MERGE_ARGS, {
        port: {
          mergeError: new MergeGateError(
            "gh",
            "gh pr merge failed: Head branch was modified"
          ),
        },
      });
      expect(result.exitCode).toBe(1);
      expect(parsed(result.stdout)).toMatchObject({
        kind: "ERROR",
        source: "gh",
        detail: "gh pr merge failed: Head branch was modified",
      });
    });
  });

  it("uses the latest verdict when an older FAIL was superseded", async () => {
    const result = await run([...MERGE_ARGS, "--check"], {
      port: {
        comments: [
          issueComment({
            createdAt: "2026-10-02T10:00:00Z",
            body: verdictBody({ verdict: "FAIL" }),
          }),
          issueComment({
            createdAt: "2026-10-02T11:00:00Z",
            body: verdictBody({ verdict: "PASS" }),
          }),
        ],
      },
    });
    expect(result.exitCode).toBe(0);
  });
});
