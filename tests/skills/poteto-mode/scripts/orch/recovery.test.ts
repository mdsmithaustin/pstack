import { afterEach, describe, expect, it } from "bun:test";
import { mkdtemp, mkdir, readFile, readdir, rename, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const script =
  process.env.ORCH_TEST_SCRIPT ??
  join(
    import.meta.dir,
    "../../../../../skills/poteto-mode/scripts/orch/orch.ts",
  );
const directories: string[] = [];
async function fixture() {
  const dir = await mkdtemp(join(tmpdir(), "orch-recovery-"));
  directories.push(dir);
  const run = (...args: string[]) => {
    const result = Bun.spawnSync([
      process.execPath,
      script,
      "--store",
      dir,
      "--json",
      ...args,
    ]);
    return {
      code: result.exitCode,
      out: result.stdout.toString(),
      err: result.stderr.toString(),
    };
  };
  expect(run("init").code).toBe(0);
  expect(run("unit", "add", "u", "--track", "core").code).toBe(0);
  return { dir, run };
}
async function input(dir: string, name: string, value: unknown) {
  const path = join(dir, name);
  await writeFile(path, JSON.stringify(value));
  return path;
}
afterEach(async () => {
  for (const dir of directories.splice(0))
    await rm(dir, { recursive: true, force: true });
});
describe("CLI recovery", () => {
  it("retains legacy deliveries and partially acknowledges stable events", async () => {
    const { dir, run } = await fixture();
    expect(run("inbox", "push", "worker", "u", "done").code).toBe(0);
    expect(run("inbox", "push", "worker", "u", "failed").code).toBe(0);
    expect(JSON.parse(run("inbox", "drain").out)).toHaveLength(2);
    expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 2 });
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    expect(
      batch.events
        .map((event: { pointer: { status: string } }) => event.pointer.status)
        .sort(),
    ).toEqual(["done", "failed"]);
    const decision = [
      {
        event: batch.events[0].id,
        outcome: { kind: "unit", state: "accepted" },
      },
    ];
    const path = await input(dir, "decisions.json", decision);
    expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(0);
    const unit = JSON.parse(run("unit", "get", "u").out);
    expect(unit.state).toBe("accepted");
    expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(0);
    expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 1 });
    const next = JSON.parse(run("inbox", "drain", "--receipt").out);
    expect(next.id).toBe(batch.id);
    expect(next.events.map((event: { id: string }) => event.id)).toEqual([
      batch.events[1].id,
    ]);
    await input(dir, "decisions.json", [
      {
        event: batch.events[0].id,
        outcome: { kind: "unit", state: "conflict" },
      },
    ]);
    expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(1);
    expect(JSON.parse(run("unit", "get", "u").out).state).toBe("accepted");
    expect(await readFile(join(dir, "units.tsv"), "utf8")).toContain(
      "u\tcore\taccepted\t",
    );
  });
});

async function preload(
  dir: string,
  point: "claim" | "emission" | "unit" | "decision" | "attempt" | "ledger" | "complete" | "archive-before" | "archive" | "migration" | "migration-marker",
  pause = false,
) {
  const marker = join(dir, "fault-marker");
  const release = join(dir, "fault-release");
  const path = join(dir, "fault.ts");
  await writeFile(
    path,
    `
import { mock } from "bun:test";
import * as original from "node:fs/promises";
const fs = { ...original };
let claimed = false;
async function stop() {
  await fs.writeFile(${JSON.stringify(marker)}, "reached");
  ${pause ? `while (!(await fs.access(${JSON.stringify(release)}).then(() => true, () => false))) await Bun.sleep(5);` : 'process.kill(process.pid, "SIGKILL");'}
}
mock.module("node:fs/promises", () => ({ ...fs,
  rename: async (from, to) => {
    if (${JSON.stringify(point)} === "attempt" && String(to).endsWith("/attempts.json")) await stop();
    if (${JSON.stringify(point)} === "archive-before" && String(from).includes("/inbox-pending/") && String(to).includes("/inbox-batches/")) await stop();
    await fs.rename(from, to);
    if (${JSON.stringify(point)} === "archive" && String(from).includes("/inbox-pending/") && String(to).includes("/inbox-batches/")) await stop();
    if (${JSON.stringify(point)} === "migration" && String(from).includes("/inbox-batches/") && String(to).includes("/inbox-pending/")) await stop();
    if (${JSON.stringify(point)} === "migration-marker" && String(to).endsWith("/.inbox-pending-migrated")) await stop();
    if (${JSON.stringify(point)} === "complete" && String(to).includes("/decisions/") && String(to).endsWith(".json") && JSON.parse(await fs.readFile(to, "utf8")).completed) await stop();
    if (String(from).endsWith("/inbox")) claimed = true;
    if (${JSON.stringify(point)} === "claim" && String(from).endsWith("/inbox")) await stop();
    if (${JSON.stringify(point)} === "unit" && String(to).endsWith("/units.tsv")) await stop();
    if (${JSON.stringify(point)} === "ledger" && String(to).endsWith("/ledger.tsv")) await stop();
    if (${JSON.stringify(point)} === "decision" && String(to).includes("/decisions/") && String(to).endsWith(".json")) await stop();
  },
  mkdir: async (path, options) => {
    const result = await fs.mkdir(path, options);
    if (${JSON.stringify(point)} === "emission" && String(path).endsWith("/inbox") && claimed) await stop();
    return result;
  }
}));
`,
  );
  return { path, marker, release };
}
async function waitFor(path: string) {
  const deadline = Date.now() + 1500;
  while (Date.now() < deadline) {
    if (await Bun.file(path).exists()) return;
    await Bun.sleep(5);
  }
  throw new Error(`CLI did not reach fault point ${path}`);
}
async function killAt(
  dir: string,
  point: "claim" | "emission" | "unit" | "decision" | "attempt" | "ledger" | "complete" | "archive-before" | "archive" | "migration" | "migration-marker",
  args: string[],
) {
  const hook = await preload(dir, point);
  const child = Bun.spawn(
    [
      process.execPath,
      "--preload",
      hook.path,
      script,
      "--store",
      dir,
      "--json",
      ...args,
    ],
    { stdout: "pipe", stderr: "pipe" },
  );
  const code = await child.exited;
  expect(code).not.toBe(0);
  expect(await readFile(hook.marker, "utf8")).toBe("reached");
  expect(await new Response(child.stdout).text()).toBe("");
}
describe("CLI interruption", () => {
  it("recovers a claim killed between rename and mkdir", async () => {
    const { dir, run } = await fixture();
    expect(run("inbox", "push", "worker", "u", "done").code).toBe(0);
    await killAt(dir, "claim", ["inbox", "drain"]);
    expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 1 });
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    expect(
      batch.events.map(
        (e: { pointer: { status: string } }) => e.pointer.status,
      ),
    ).toEqual(["done"]);
  });
  it("retains a claim interrupted before emission", async () => {
    const { dir, run } = await fixture();
    expect(run("inbox", "push", "worker", "u", "done").code).toBe(0);
    await killAt(dir, "emission", ["inbox", "drain"]);
    expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 1 });
    expect(
      JSON.parse(run("inbox", "receipts").out)[0].events[0].pointer.status,
    ).toBe("done");
  });
  it("keeps arrivals during claim for a later batch", async () => {
    const { dir, run } = await fixture();
    expect(run("inbox", "push", "first", "u", "done").code).toBe(0);
    const hook = await preload(dir, "claim", true);
    const child = Bun.spawn(
      [
        process.execPath,
        "--preload",
        hook.path,
        script,
        "--store",
        dir,
        "--json",
        "inbox",
        "drain",
        "--receipt",
      ],
      { stdout: "pipe", stderr: "pipe" },
    );
    try {
      await waitFor(hook.marker);
      expect(run("inbox", "push", "arrival", "u", "later").code).toBe(0);
      await writeFile(hook.release, "go");
      expect(await child.exited).toBe(0);
      const batch = JSON.parse(await new Response(child.stdout).text());
      expect(
        batch.events.map(
          (e: { pointer: { agent: string } }) => e.pointer.agent,
        ),
      ).toEqual(["first"]);
      expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 2 });
      const path = await input(dir, "ack.json", [
        {
          event: batch.events[0].id,
          outcome: { kind: "discard", reason: "reviewed" },
        },
      ]);
      expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(0);
      expect(
        JSON.parse(run("inbox", "drain", "--receipt").out).events[0].pointer
          .agent,
      ).toBe("arrival");
    } finally {
      child.kill();
      await child.exited;
    }
  });
  for (const point of ["decision", "unit"] as const) {
    it(`replays a partial acknowledgment interrupted after ${point} persistence`, async () => {
      const { dir, run } = await fixture();
      expect(run("inbox", "push", "worker", "u", "done").code).toBe(0);
      expect(run("inbox", "push", "later", "u", "waiting").code).toBe(0);
      const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
      const path = await input(dir, "ack.json", [
        {
          event: batch.events[0].id,
          outcome: {
            kind: "unit",
            state: "reviewed",
            pr: 12,
            sha: "head",
            ledger: {
              kind: "verdict",
              pr: 12,
              sha: "head",
              verdict: "unit-test-verified",
              evidence: "proof",
            },
          },
        },
      ]);
      await killAt(dir, point, ["inbox", "ack", batch.id, "--file", path]);
      expect(JSON.parse(run("unit", "get", "u").out).state).toBe("reviewed");
      const ledger = run("ledger", "check", "12", "head");
      expect(ledger.code).toBe(0);
      expect(JSON.parse(ledger.out).verdict).toBe("unit-test-verified");
      expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(0);
      expect(run("ledger", "check", "12", "head").out).toBe(ledger.out);
      expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 1 });
      const pending = JSON.parse(run("inbox", "drain", "--receipt").out);
      expect(pending.id).toBe(batch.id);
      expect(pending.events.map((event: { id: string }) => event.id)).toEqual([
        batch.events[1].id,
      ]);
    });
  }
});

async function begin(
  dir: string,
  run: (...args: string[]) => { code: number; out: string; err: string },
  requestId: string,
  authority = "worker",
  replace?: string,
  role = authority === "worker" ? "feature" : "trail reviewer",
) {
  const path = await input(dir, `${requestId}.json`, {
    unit: "u",
    role,
    arm: 1,
    authority,
    requestId,
    brief: "brief.md",
    checkout: dir,
    resolution: { harness: "codex", model: "gpt-6.1-sol", effort: "xhigh" },
    ...(replace === undefined ? {} : { replace }),
  });
  const result = run("attempt", "begin", "--file", path);
  expect(result.code).toBe(0);
  return { path, attempt: JSON.parse(result.out), result };
}
function completionArgs(
  attempt: { id: string; binding: string },
  head?: { pr: string; sha: string },
): string[] {
  return [
    "--attempt", attempt.id,
    "--binding", attempt.binding,
    ...(head === undefined ? [] : ["--pr", head.pr, "--sha", head.sha]),
  ];
}
describe("CLI attempt authority", () => {
  it("makes requestId idempotent and replacement compare-and-set", async () => {
    const { dir, run } = await fixture();
    const first = await begin(dir, run, "first");
    expect(run("attempt", "begin", "--file", first.path).out).toBe(
      first.result.out,
    );
    const second = await begin(dir, run, "second", "worker", first.attempt.id);
    expect(second.attempt.replace).toBe(first.attempt.id);
    expect(run("attempt", "begin", "--file", first.path).out).toBe(
      first.result.out,
    );
    const wrong = await input(dir, "wrong.json", {
      ...JSON.parse(await readFile(first.path, "utf8")),
      requestId: "wrong",
      replace: first.attempt.id,
    });
    expect(run("attempt", "begin", "--file", wrong).code).toBe(1);
    await input(dir, "first.json", {
      ...JSON.parse(await readFile(first.path, "utf8")),
      brief: "changed",
    });
    expect(run("attempt", "begin", "--file", first.path).code).toBe(1);
    expect(
      run("unit", "set", "u", "--state", "late", "--attempt", first.attempt.id)
        .code,
    ).toBe(1);
    expect(run("unit", "set", "u", "--state", "unbound").code).toBe(1);
    expect(
      run(
        "unit",
        "set",
        "u",
        "--state",
        "accepted",
        "--attempt",
        second.attempt.id,
      ).code,
    ).toBe(0);
    expect(JSON.parse(run("unit", "get", "u").out).state).toBe("accepted");
  });
  it("rejects stale and unbound completion while keeping it inspectable", async () => {
    const { dir, run } = await fixture();
    const first = await begin(dir, run, "first");
    await begin(dir, run, "second", "worker", first.attempt.id);
    expect(
      run("inbox", "push", "worker", "u", "done", "--attempt", first.attempt.id)
        .code,
    ).toBe(0);
    expect(run("inbox", "push", "legacy", "u", "done").code).toBe(0);
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    for (const event of batch.events) {
      const path = await input(dir, "ack.json", [
        { event: event.id, outcome: { kind: "unit", state: "late" } },
      ]);
      expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(1);
    }
    expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 2 });
    expect(JSON.parse(run("unit", "get", "u").out).state).toBe("pending");
  });
  it("keeps parallel worker and verifier slots and verifier revisions", async () => {
    const { dir, run } = await fixture();
    expect(
      run("unit", "set", "u", "--state", "ready", "--pr", "12", "--sha", "head")
        .code,
    ).toBe(0);
    const worker = (await begin(dir, run, "worker")).attempt;
    const verifier = (await begin(dir, run, "verifier", "verifier")).attempt;
    const verdict = (id: string, value: string, sha = "head") =>
      run(
        "ledger",
        "record",
        "12",
        sha,
        value,
        "--evidence",
        "proof",
        "--attempt",
        id,
      );
    expect(verdict(worker.id, "unit-test-verified").code).toBe(0);
    expect(verdict(verifier.id, "unit-test-verified").code).toBe(0);
    expect(verdict(worker.id, "live-ui-verified").code).toBe(1);
    expect(verdict(verifier.id, "verifier-failed").code).toBe(0);
    expect(JSON.parse(run("ledger", "check", "12", "head").out).verdict).toBe(
      "verifier-failed",
    );
    expect(verdict(verifier.id, "unit-test-verified").code).toBe(0);
    expect(verdict(verifier.id, "unit-test-verified", "new-head").code).toBe(1);
    expect(
      run(
        "unit",
        "set",
        "u",
        "--state",
        "restacked",
        "--sha",
        "new-head",
        "--attempt",
        worker.id,
      ).code,
    ).toBe(0);
    expect(verdict(verifier.id, "verifier-failed").code).toBe(1);
    expect(
      run(
        "ledger",
        "record",
        "12",
        "head",
        "live-ui-verified",
        "--evidence",
        "forged",
        "--verifier",
        "claimed",
      ).code,
    ).toBe(1);
  });
  it("protects verifier attribution for untracked legacy ledger writes", async () => {
    const { run } = await fixture();
    expect(
      run(
        "ledger",
        "record",
        "12",
        "head",
        "unit-test-verified",
        "--evidence",
        "proof",
        "--verifier",
        "reviewer",
      ).code,
    ).toBe(0);
    expect(
      run(
        "ledger",
        "record",
        "12",
        "head",
        "live-ui-verified",
        "--evidence",
        "worker",
      ).code,
    ).toBe(1);
    expect(
      run(
        "ledger",
        "record",
        "12",
        "head",
        "verifier-failed",
        "--evidence",
        "failure",
        "--verifier",
        "reviewer",
      ).code,
    ).toBe(0);
    expect(JSON.parse(run("ledger", "check", "12", "head").out).verdict).toBe(
      "verifier-failed",
    );
  });
  it("records native, CLI and unknown observations without declaring a death", async () => {
    const { dir, run } = await fixture();
    const attempt = (await begin(dir, run, "worker")).attempt;
    expect(attempt.observation).toEqual({ kind: "unknown" });
    for (const observation of [
      { kind: "native", identity: "agent-1" },
      { kind: "cli", receipt: "log.txt" },
      { kind: "unknown" },
    ]) {
      const path = await input(dir, "observe.json", observation);
      const result = run("attempt", "observe", attempt.id, "--file", path);
      expect(result.code).toBe(0);
      expect(JSON.parse(result.out).observation).toEqual(observation);
      expect(JSON.parse(result.out).settled).toBeNull();
    }
  });
});

describe("CLI explicit requirements", () => {
  it("checks state-only units without invented PRs and fails pending work or wrong criteria", async () => {
    const { dir, run } = await fixture();
    const criteria = await input(dir, "requirements.json", [
      { id: "core", unit: "u", states: ["published"] },
    ]);
    expect(run("requirements", "check", "--file", criteria).code).toBe(2);
    expect(run("unit", "set", "u", "--state", "published").code).toBe(0);
    expect(
      JSON.parse(run("requirements", "check", "--file", criteria).out),
    ).toEqual({
      ok: true,
      failures: [],
      pendingEvents: 0,
      pendingAttempts: [],
    });
    const attempt = (await begin(dir, run, "worker")).attempt;
    expect(run("requirements", "check", "--file", criteria).code).toBe(2);
    expect(
      run(
        "attempt",
        "finish",
        attempt.id,
        "--reason",
        "abandoned after inspection",
      ).code,
    ).toBe(0);
    expect(run("inbox", "push", "worker", "u", "done").code).toBe(0);
    expect(run("requirements", "check", "--file", criteria).code).toBe(2);
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    const ack = await input(dir, "ack.json", [
      {
        event: batch.events[0].id,
        outcome: { kind: "discard", reason: "duplicate" },
      },
    ]);
    expect(run("inbox", "ack", batch.id, "--file", ack).code).toBe(0);
    expect(run("requirements", "check", "--file", criteria).code).toBe(0);
    await input(dir, "requirements.json", [
      { id: "missing", unit: "missing", states: ["published"] },
    ]);
    expect(run("requirements", "check", "--file", criteria).code).toBe(2);
    await input(dir, "requirements.json", [{ id: "empty", unit: "u" }]);
    expect(run("requirements", "check", "--file", criteria).code).toBe(1);
  });
  it("requires the declared exact current PR/head and allowed verdict", async () => {
    const { dir, run } = await fixture();
    expect(
      run(
        "unit",
        "set",
        "u",
        "--state",
        "merged",
        "--pr",
        "12",
        "--sha",
        "head",
      ).code,
    ).toBe(0);
    const criteria = await input(dir, "requirements.json", [
      {
        id: "pr",
        unit: "u",
        ledger: { pr: 12, sha: "head", verdicts: ["unit-test-verified"] },
      },
    ]);
    expect(run("requirements", "check", "--file", criteria).code).toBe(2);
    expect(
      run(
        "ledger",
        "record",
        "12",
        "head",
        "unit-test-verified",
        "--evidence",
        "proof",
        "--verifier",
        "reviewer",
      ).code,
    ).toBe(0);
    expect(run("requirements", "check", "--file", criteria).code).toBe(0);
    expect(
      run(
        "ledger",
        "record",
        "12",
        "head",
        "verifier-failed",
        "--evidence",
        "failure",
        "--verifier",
        "reviewer",
      ).code,
    ).toBe(0);
    expect(run("requirements", "check", "--file", criteria).code).toBe(2);
    expect(
      run("unit", "set", "u", "--state", "restacked", "--sha", "new-head").code,
    ).toBe(0);
    expect(run("requirements", "check", "--file", criteria).code).toBe(2);
  });
});

describe("CLI acknowledgment authority", () => {
  it("uses verifier precedence for acknowledgments and preserves rejected events", async () => {
    const { dir, run } = await fixture();
    expect(
      run("unit", "set", "u", "--state", "ready", "--pr", "12", "--sha", "head")
        .code,
    ).toBe(0);
    const worker = (await begin(dir, run, "worker")).attempt;
    const verifier = (await begin(dir, run, "verifier", "verifier")).attempt;
    const apply = async (id: string, verdict: string) => {
      expect(
        run("inbox", "push", "agent", "u", verdict, ...completionArgs(id === verifier.id ? verifier : worker, { pr: "12", sha: "head" })).code,
      ).toBe(0);
      const result = run("inbox", "drain", "--receipt");
      expect(result.code).toBe(0);
      const batch = JSON.parse(result.out);
      const event = batch.events.find(
        (e: { pointer: { attempt: string } }) => e.pointer.attempt === id,
      );
      const path = await input(dir, "ack.json", [
        {
          event: event.id,
          outcome: {
            kind: "verdict",
            pr: 12,
            sha: "head",
            verdict,
            evidence: "proof",
          },
        },
      ]);
      return {
        batch,
        event,
        result: run("inbox", "ack", batch.id, "--file", path),
      };
    };
    expect((await apply(verifier.id, "unit-test-verified")).result.code).toBe(
      0,
    );
    const rejected = await apply(worker.id, "live-ui-verified");
    expect(rejected.result.code).toBe(1);
    expect(JSON.parse(run("ledger", "check", "12", "head").out).verdict).toBe(
      "unit-test-verified",
    );
    const path = await input(dir, "discard.json", [
      {
        event: rejected.event.id,
        outcome: {
          kind: "discard",
          reason: "worker cannot replace verification",
        },
      },
    ]);
    expect(run("inbox", "ack", rejected.batch.id, "--file", path).code).toBe(0);
    expect((await apply(verifier.id, "verifier-failed")).result.code).toBe(0);
    expect(JSON.parse(run("ledger", "check", "12", "head").out).verdict).toBe(
      "verifier-failed",
    );
    expect((await apply(verifier.id, "unit-test-verified")).result.code).toBe(
      0,
    );
    const receipts = JSON.parse(run("inbox", "receipts").out);
    expect(
      receipts
        .flatMap((r: { decisions: { completed: boolean }[] }) => r.decisions)
        .every((d: { completed: boolean }) => d.completed),
    ).toBe(true);
    expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 0 });
  });
  it("rejects a verifier event for a changed head without consuming it", async () => {
    const { dir, run } = await fixture();
    expect(
      run("unit", "set", "u", "--state", "ready", "--pr", "12", "--sha", "head")
        .code,
    ).toBe(0);
    const verifier = (await begin(dir, run, "verifier", "verifier")).attempt;
    const worker = (await begin(dir, run, "worker")).attempt;
    expect(
      run("inbox", "push", "verifier", "u", "passed", ...completionArgs(verifier, { pr: "12", sha: "head" }))
        .code,
    ).toBe(0);
    expect(
      run(
        "unit",
        "set",
        "u",
        "--state",
        "restacked",
        "--sha",
        "new-head",
        "--attempt",
        worker.id,
      ).code,
    ).toBe(0);
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    const path = await input(dir, "ack.json", [
      {
        event: batch.events[0].id,
        outcome: {
          kind: "verdict",
          pr: 12,
          sha: "head",
          verdict: "unit-test-verified",
          evidence: "old",
        },
      },
    ]);
    expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(1);
    expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 1 });
    expect(JSON.parse(run("unit", "get", "u").out).sha).toBe("new-head");
    expect(run("ledger", "check", "12", "head").code).toBe(2);
  });
  it("replays tracked unit, verdict and attempt settlement together", async () => {
    const { dir, run } = await fixture();
    const worker = (await begin(dir, run, "worker")).attempt;
    expect(
      run("inbox", "push", "worker", "u", "done", ...completionArgs(worker, { pr: "12", sha: "head" })).code,
    ).toBe(0);
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    const path = await input(dir, "ack.json", [
      {
        event: batch.events[0].id,
        outcome: {
          kind: "unit",
          state: "published",
          pr: 12,
          sha: "head",
          ledger: {
            kind: "verdict",
            pr: 12,
            sha: "head",
            verdict: "unit-test-verified",
            evidence: "proof",
          },
        },
      },
    ]);
    await killAt(dir, "unit", ["inbox", "ack", batch.id, "--file", path]);
    const attempts = run("attempt", "list");
    expect(attempts.code).toBe(0);
    expect(JSON.parse(attempts.out)[0]).toMatchObject({
      id: worker.id,
      target: { pr: "12", sha: "head" },
    });
    expect(JSON.parse(run("ledger", "check", "12", "head").out).verdict).toBe(
      "unit-test-verified",
    );
    expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(0);
    const criteria = await input(dir, "requirements.json", [
      { id: "published", unit: "u", states: ["published"] },
    ]);
    expect(run("requirements", "check", "--file", criteria).code).toBe(0);
  });
});

describe("CLI slot and pending invariants", () => {
  it("preserves pending attempts across arbitrary direct unit updates", async () => {
    const { dir, run } = await fixture();
    const worker = (await begin(dir, run, "worker")).attempt;
    expect(
      run(
        "unit",
        "set",
        "u",
        "--state",
        "custom running state",
        "--attempt",
        worker.id,
      ).code,
    ).toBe(0);
    expect(JSON.parse(run("attempt", "list").out)[0].settled).toBeNull();
    const path = await input(dir, "requirements.json", [
      { id: "state", unit: "u", states: ["custom running state"] },
    ]);
    expect(run("requirements", "check", "--file", path).code).toBe(2);
    expect(
      run("attempt", "finish", worker.id, "--reason", "output inspected").code,
    ).toBe(0);
    expect(run("requirements", "check", "--file", path).code).toBe(0);
  });
  it("keeps exact resolution and independent panel arms and rejects a foreign unit", async () => {
    const { dir, run } = await fixture();
    const first = await begin(dir, run, "first", "worker", undefined, "arena runners");
    const request = JSON.parse(await readFile(first.path, "utf8"));
    const other = await input(dir, "other.json", {
      ...request,
      requestId: "other",
      arm: 2,
      resolution: { harness: "codex", model: "gpt-6-astra", effort: "high" },
    });
    const result = run("attempt", "begin", "--file", other);
    expect(result.code).toBe(0);
    const second = JSON.parse(result.out);
    expect(second).toMatchObject({
      unit: "u",
      role: "arena runners",
      arm: 2,
      authority: "worker",
      resolution: { harness: "codex", model: "gpt-6-astra", effort: "high" },
    });
    expect(
      run(
        "unit",
        "set",
        "u",
        "--state",
        "first arm",
        "--attempt",
        first.attempt.id,
      ).code,
    ).toBe(0);
    expect(
      run("unit", "set", "u", "--state", "second arm", "--attempt", second.id)
        .code,
    ).toBe(0);
    expect(run("unit", "add", "foreign", "--track", "core").code).toBe(0);
    expect(
      run(
        "unit",
        "set",
        "foreign",
        "--state",
        "wrong",
        "--attempt",
        first.attempt.id,
      ).code,
    ).toBe(1);
    expect(JSON.parse(run("unit", "get", "foreign").out).state).toBe("pending");
    expect(JSON.parse(run("unit", "get", "u").out).state).toBe("second arm");
  });
});


describe("CLI core review regressions", () => {
  for (const point of ["unit", "attempt"] as const) {
    it(`replays a direct head update interrupted at ${point}`, async () => {
      const { dir, run } = await fixture();
      expect(run("unit", "set", "u", "--state", "ready", "--pr", "12", "--sha", "old").code).toBe(0);
      const worker = (await begin(dir, run, "worker")).attempt;
      await killAt(dir, point, ["unit", "set", "u", "--state", "restacked", "--sha", "new", "--attempt", worker.id]);
      const saved = JSON.parse(run("attempt", "list").out)[0];
      expect(saved.target).toEqual({ pr: "12", sha: "new" });
      expect(run("unit", "set", "u", "--state", "continued", "--attempt", worker.id).code).toBe(0);
      expect(JSON.parse(run("unit", "get", "u").out)).toMatchObject({ state: "continued", sha: "new" });
    });
  }
  it("replays direct ledger settlement after its rename", async () => {
    const { dir, run } = await fixture();
    expect(run("unit", "set", "u", "--state", "ready", "--pr", "12", "--sha", "head").code).toBe(0);
    const verifier = (await begin(dir, run, "verifier", "verifier")).attempt;
    await killAt(dir, "ledger", ["ledger", "record", "12", "head", "unit-test-verified", "--evidence", "proof", "--attempt", verifier.id]);
    expect(JSON.parse(run("ledger", "check", "12", "head").out).verdict).toBe("unit-test-verified");
    expect(JSON.parse(run("attempt", "list").out)[0].settled).not.toBeNull();
    const criteria = await input(dir, "requirements.json", [{ id: "verified", unit: "u", ledger: { pr: 12, sha: "head", verdicts: ["unit-test-verified"] } }]);
    expect(run("requirements", "check", "--file", criteria).code).toBe(0);
  });
  for (const kind of ["unit", "verdict"] as const) {
    it(`quarantines a legacy queued ${kind} result after rebinding its attempt`, async () => {
      const { dir, run } = await fixture();
      expect(run("unit", "set", "u", "--state", "ready", "--pr", "12", "--sha", "old").code).toBe(0);
      const worker = (await begin(dir, run, "worker")).attempt;
      expect(run("inbox", "push", "worker", "u", "done", "--attempt", worker.id).code).toBe(0);
      expect(run("unit", "set", "u", "--state", "restacked", "--sha", "new", "--attempt", worker.id).code).toBe(0);
      const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
      const outcome = kind === "unit" ? { kind, state: "late" } : { kind, pr: 12, sha: "new", verdict: "unit-test-verified", evidence: "old report" };
      const ack = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome }]);
      expect(run("inbox", "ack", batch.id, "--file", ack).code).toBe(1);
      expect(JSON.parse(run("unit", "get", "u").out).state).toBe("restacked");
      expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 1 });
    });
  }
  for (const operation of ["unit", "ledger", "ack-unit", "ack-verdict"] as const) {
    it(`revokes ${operation} effects after explicit abandonment`, async () => {
      const { dir, run } = await fixture();
      expect(run("unit", "set", "u", "--state", "ready", "--pr", "12", "--sha", "head").code).toBe(0);
      const worker = (await begin(dir, run, "worker")).attempt;
      expect(run("inbox", "push", "worker", "u", "done", ...completionArgs(worker, { pr: "12", sha: "head" })).code).toBe(0);
      expect(run("attempt", "finish", worker.id, "--reason", "abandoned").code).toBe(0);
      let result;
      if (operation === "unit") result = run("unit", "set", "u", "--state", "late", "--attempt", worker.id);
      else if (operation === "ledger") result = run("ledger", "record", "12", "head", "unit-test-verified", "--evidence", "late", "--attempt", worker.id);
      else {
        const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
        const outcome = operation === "ack-unit" ? { kind: "unit", state: "late" } : { kind: "verdict", pr: 12, sha: "head", verdict: "unit-test-verified", evidence: "late" };
        const ack = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome }]);
        result = run("inbox", "ack", batch.id, "--file", ack);
      }
      expect(result.code).toBe(1);
      expect(result.err).toContain("explicitly finished");
      expect(JSON.parse(run("unit", "get", "u").out).state).toBe("ready");
      expect(run("ledger", "check", "12", "head").code).toBe(2);
    });
  }
  for (const verdict of ["verifier-blocked", "verifier-failed"]) {
    for (const mixed of [false, true]) {
      it(`rejects ${verdict} ${mixed ? "mixed" : "single"} closeout criteria`, async () => {
        const { dir, run } = await fixture();
        expect(run("unit", "set", "u", "--state", "custom done", "--pr", "12", "--sha", "head").code).toBe(0);
        expect(run("ledger", "record", "12", "head", verdict, "--evidence", "failure", "--verifier", "reviewer").code).toBe(0);
        const criteria = await input(dir, "requirements.json", [{ id: "verified", unit: "u", ledger: { pr: 12, sha: "head", verdicts: mixed ? ["unit-test-verified", verdict] : [verdict] } }]);
        expect(run("requirements", "check", "--file", criteria).code).toBe(1);
      });
    }
  }
  for (const mode of ["legacy", "receipt", "compact"] as const) {
    it(`keeps repeated empty ${mode} drains bounded`, async () => {
      const { dir, run } = await fixture();
      for (let i = 0; i < 3; i++) {
        const result = mode === "compact" ? Bun.spawnSync([process.execPath, script, "--store", dir, "inbox", "drain"]) : run("inbox", "drain", ...(mode === "receipt" ? ["--receipt"] : []));
        expect("exitCode" in result ? result.exitCode : result.code).toBe(0);
        expect(await readdir(join(dir, "inbox-batches"))).toEqual([]);
        if ("out" in result) expect(JSON.parse(result.out)).toEqual(mode === "receipt" ? null : []);
      }
      expect(run("inbox", "push", "worker", "u", "done").code).toBe(0);
      expect(JSON.parse(run("inbox", "drain", "--receipt").out).events[0].pointer.status).toBe("done");
    });
  }
  it("keeps an unknown predecessor in final reconciliation after its successor finishes", async () => {
    const { dir, run } = await fixture();
    const first = (await begin(dir, run, "first")).attempt;
    const second = (await begin(dir, run, "second", "worker", first.id)).attempt;
    expect(run("attempt", "finish", second.id, "--reason", "inspected").code).toBe(0);
    const criteria = await input(dir, "requirements.json", [{ id: "state", unit: "u", states: ["pending"] }]);
    const check = run("requirements", "check", "--file", criteria);
    expect(check.code).toBe(2);
    expect(JSON.parse(check.out).pendingAttempts).toEqual([first.id]);
  });
  it("allows a known terminal disposition for a superseded attempt", async () => {
    const { dir, run } = await fixture();
    expect(run("unit", "set", "u", "--state", "pending", "--pr", "12", "--sha", "head").code).toBe(0);
    const first = (await begin(dir, run, "first")).attempt;
    const second = (await begin(dir, run, "second", "worker", first.id)).attempt;
    expect(run("attempt", "finish", first.id, "--reason", "confirmed abandoned").code).toBe(0);
    expect(run("unit", "set", "u", "--state", "old", "--attempt", first.id).code).toBe(1);
    expect(run("ledger", "record", "12", "head", "unit-test-verified", "--evidence", "old", "--attempt", first.id).code).toBe(1);
    expect(run("attempt", "finish", second.id, "--reason", "inspected").code).toBe(0);
    const criteria = await input(dir, "requirements.json", [{ id: "state", unit: "u", states: ["pending"] }]);
    expect(run("requirements", "check", "--file", criteria).code).toBe(0);
  });
});


describe("CLI immutable completion bindings", () => {
  for (const kind of ["unit", "verdict"] as const) {
    for (const timing of ["queued", "late"] as const) {
      it(`rejects a ${timing} old-head ${kind} report on a rebound attempt`, async () => {
        const { dir, run } = await fixture();
        expect(run("unit", "set", "u", "--state", "ready", "--pr", "12", "--sha", "old").code).toBe(0);
        const worker = (await begin(dir, run, "worker")).attempt;
        const publish = () => run("inbox", "push", "worker", "u", "done", ...completionArgs(worker, { pr: "12", sha: "old" }));
        if (timing === "queued") expect(publish().code).toBe(0);
        expect(run("unit", "set", "u", "--state", "restacked", "--sha", "new", "--attempt", worker.id).code).toBe(0);
        if (timing === "late") expect(publish().code).toBe(0);
        const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
        expect(batch.events[0].pointer.completion).toEqual({ binding: worker.binding, pr: "12", sha: "old" });
        const outcome = kind === "unit" ? { kind, state: "late" } : { kind, pr: 12, sha: "new", verdict: "unit-test-verified", evidence: "old report" };
        const path = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome }]);
        const ack = run("inbox", "ack", batch.id, "--file", path);
        expect(ack.code).toBe(1);
        expect(ack.err).toContain("completion binding changed");
        expect(JSON.parse(run("unit", "get", "u").out)).toMatchObject({ state: "restacked", sha: "new" });
        expect(run("ledger", "check", "12", "new").code).toBe(2);
        expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 1 });
      });
    }
  }
  it("checks the actual report head even when publication claims a current binding", async () => {
    const { dir, run } = await fixture();
    expect(run("unit", "set", "u", "--state", "ready", "--pr", "12", "--sha", "old").code).toBe(0);
    const worker = (await begin(dir, run, "worker")).attempt;
    expect(run("unit", "set", "u", "--state", "restacked", "--sha", "new", "--attempt", worker.id).code).toBe(0);
    const current = JSON.parse(run("attempt", "list").out)[0];
    expect(run("inbox", "push", "worker", "u", "done", ...completionArgs(current, { pr: "12", sha: "old" })).code).toBe(0);
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    const path = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome: { kind: "unit", state: "late" } }]);
    const ack = run("inbox", "ack", batch.id, "--file", path);
    expect(ack.code).toBe(1);
    expect(ack.err).toContain("completion report head changed");
    expect(JSON.parse(run("unit", "get", "u").out).state).toBe("restacked");
  });
  it("preserves currency when a unit returns to a previous head", async () => {
    const { dir, run } = await fixture();
    expect(run("unit", "set", "u", "--state", "ready", "--pr", "12", "--sha", "old").code).toBe(0);
    const worker = (await begin(dir, run, "worker")).attempt;
    for (const sha of ["new", "old"]) expect(run("unit", "set", "u", "--state", "restacked", "--sha", sha, "--attempt", worker.id).code).toBe(0);
    expect(run("inbox", "push", "worker", "u", "done", ...completionArgs(worker, { pr: "12", sha: "old" })).code).toBe(0);
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    const path = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome: { kind: "unit", state: "late" } }]);
    expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(1);
    expect(JSON.parse(run("unit", "get", "u").out)).toMatchObject({ state: "restacked", sha: "old" });
  });
  it("accepts an initial worker report that introduces its PR and SHA", async () => {
    const { dir, run } = await fixture();
    const worker = (await begin(dir, run, "worker")).attempt;
    expect(run("inbox", "push", "worker", "u", "done", ...completionArgs(worker, { pr: "12", sha: "head" })).code).toBe(0);
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    const path = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome: { kind: "unit", state: "published", pr: 12, sha: "head", ledger: { kind: "verdict", pr: 12, sha: "head", verdict: "unit-test-verified", evidence: "proof" } } }]);
    expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(0);
    expect(JSON.parse(run("unit", "get", "u").out)).toMatchObject({ state: "published", pr: "12", sha: "head" });
    expect(JSON.parse(run("ledger", "check", "12", "head").out).verdict).toBe("unit-test-verified");
    expect(JSON.parse(run("attempt", "list").out)[0].settled.kind).toBe("accepted");
    expect(run("unit", "set", "u", "--state", "merged", "--attempt", worker.id).code).toBe(0);
    expect(JSON.parse(run("attempt", "list").out)).toHaveLength(1);
    expect(JSON.parse(run("unit", "get", "u").out).state).toBe("merged");
  });
  it("accepts a bound state-only worker completion without inventing a PR", async () => {
    const { dir, run } = await fixture();
    const worker = (await begin(dir, run, "worker")).attempt;
    expect(run("inbox", "push", "worker", "u", "done", ...completionArgs(worker)).code).toBe(0);
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    const path = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome: { kind: "unit", state: "arbitrary published state" } }]);
    expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(0);
    const criteria = await input(dir, "requirements.json", [{ id: "state", unit: "u", states: ["arbitrary published state"] }]);
    expect(run("requirements", "check", "--file", criteria).code).toBe(0);
    expect(JSON.parse(run("unit", "get", "u").out)).toMatchObject({ pr: "", sha: "" });
  });
  it("rejects an initial outcome for a different report head", async () => {
    const { dir, run } = await fixture();
    const worker = (await begin(dir, run, "worker")).attempt;
    expect(run("inbox", "push", "worker", "u", "done", ...completionArgs(worker, { pr: "12", sha: "actual" })).code).toBe(0);
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    const path = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome: { kind: "unit", state: "wrong", pr: 12, sha: "other" } }]);
    const ack = run("inbox", "ack", batch.id, "--file", path);
    expect(ack.code).toBe(1);
    expect(ack.err).toContain("does not match completion report head");
    expect(JSON.parse(run("unit", "get", "u").out)).toMatchObject({ state: "pending", pr: "", sha: "" });
  });
  it("does not let a verifier completion introduce a different head", async () => {
    const { dir, run } = await fixture();
    const verifier = (await begin(dir, run, "verifier", "verifier")).attempt;
    expect(run("inbox", "push", "verifier", "u", "done", ...completionArgs(verifier, { pr: "12", sha: "head" })).code).toBe(0);
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    const path = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome: { kind: "unit", state: "wrong", pr: 12, sha: "head" } }]);
    expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(1);
    expect(JSON.parse(run("unit", "get", "u").out).state).toBe("pending");
  });
  it("keeps a true duplicate acknowledgment valid after rebind and terminal finish", async () => {
    const { dir, run } = await fixture();
    const worker = (await begin(dir, run, "worker")).attempt;
    expect(run("inbox", "push", "worker", "u", "done", ...completionArgs(worker, { pr: "12", sha: "head" })).code).toBe(0);
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    const path = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome: { kind: "unit", state: "published", pr: 12, sha: "head" } }]);
    expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(0);
    expect(run("unit", "set", "u", "--state", "merged", "--sha", "new", "--attempt", worker.id).code).toBe(0);
    expect(run("attempt", "finish", worker.id, "--reason", "confirmed complete").code).toBe(0);
    const attempts = run("attempt", "list").out;
    expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(0);
    expect(run("attempt", "list").out).toBe(attempts);
    expect(JSON.parse(run("unit", "get", "u").out)).toMatchObject({ state: "merged", sha: "new" });
    expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 0 });
    expect(await readdir(join(dir, "inbox-batches"))).toEqual([batch.id]);
    expect(JSON.parse(run("inbox", "drain", "--receipt").out)).toBeNull();
    expect(await readdir(join(dir, "inbox-batches"))).toEqual([batch.id]);
    expect(JSON.parse(run("inbox", "receipts").out)[0].events[0].id).toBe(batch.events[0].id);
  });
  it("quarantines new results when an accepted verifier is explicitly finished", async () => {
    const { dir, run } = await fixture();
    expect(run("unit", "set", "u", "--state", "ready", "--pr", "12", "--sha", "head").code).toBe(0);
    const verifier = (await begin(dir, run, "verifier", "verifier")).attempt;
    expect(run("ledger", "record", "12", "head", "unit-test-verified", "--evidence", "proof", "--attempt", verifier.id).code).toBe(0);
    expect(run("unit", "set", "u", "--state", "merged", "--attempt", verifier.id).code).toBe(0);
    expect(run("attempt", "finish", verifier.id, "--reason", "abandoned").code).toBe(0);
    expect(JSON.parse(run("attempt", "list").out)[0].settled).toEqual({ kind: "finished", reason: "abandoned" });
    expect(run("ledger", "record", "12", "head", "verifier-failed", "--evidence", "late", "--attempt", verifier.id).code).toBe(1);
    expect(run("inbox", "push", "verifier", "u", "failed", ...completionArgs(verifier, { pr: "12", sha: "head" })).code).toBe(0);
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    const path = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome: { kind: "verdict", pr: 12, sha: "head", verdict: "verifier-failed", evidence: "late" } }]);
    expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(1);
    expect(JSON.parse(run("ledger", "check", "12", "head").out).verdict).toBe("unit-test-verified");
  });
  it("keeps legacy five-cell untracked publication usable", async () => {
    const { dir, run } = await fixture();
    expect(run("inbox", "push", "legacy", "u", "done").code).toBe(0);
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    expect((await readFile(join(dir, "inbox-pending", batch.id, batch.events[0].id), "utf8")).replace(/\r?\n$/, "").split("\t")).toHaveLength(5);
    const path = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome: { kind: "unit", state: "published" } }]);
    expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(0);
    expect(JSON.parse(run("unit", "get", "u").out).state).toBe("published");
  });
  for (const reason of ["abandoned", "2026-10-05T12:00:00.000Z"]) {
    it(`does not infer accepted authority from legacy settlement ${reason}`, async () => {
      const { dir, run } = await fixture();
      const worker = (await begin(dir, run, "worker")).attempt;
      const rows = JSON.parse(await readFile(join(dir, "attempts.json"), "utf8"));
      rows[0].settled = reason;
      delete rows[0].binding;
      await writeFile(join(dir, "attempts.json"), JSON.stringify(rows));
      expect(run("unit", "set", "u", "--state", "late", "--attempt", worker.id).code).toBe(1);
      expect(JSON.parse(run("attempt", "list").out)[0].settled).toEqual({ kind: "finished", reason });
      expect(JSON.parse(run("unit", "get", "u").out).state).toBe("pending");
    });
  }
  for (const point of ["ledger", "attempt"] as const) {
    it(`preserves verifier revisions after replay at ${point}`, async () => {
      const { dir, run } = await fixture();
      expect(run("unit", "set", "u", "--state", "ready", "--pr", "12", "--sha", "head").code).toBe(0);
      const verifier = (await begin(dir, run, "verifier", "verifier")).attempt;
      await killAt(dir, point, ["ledger", "record", "12", "head", "unit-test-verified", "--evidence", "proof", "--attempt", verifier.id]);
      expect(run("ledger", "record", "12", "head", "verifier-failed", "--evidence", "new failure", "--attempt", verifier.id).code).toBe(0);
      expect(JSON.parse(run("ledger", "check", "12", "head").out)).toMatchObject({ verdict: "verifier-failed", evidence: "new failure" });
      expect(run("ledger", "record", "12", "head", "unit-test-verified", "--evidence", "fixed", "--attempt", verifier.id).code).toBe(0);
      expect(JSON.parse(run("ledger", "check", "12", "head").out).evidence).toBe("fixed");
    });
  }
});


describe("CLI partial non-PR metadata", () => {
  for (const field of ["sha", "pr"] as const) {
    it(`accepts an initial worker's ${field} without requiring other head metadata`, async () => {
      const { dir, run } = await fixture();
      const worker = (await begin(dir, run, "worker")).attempt;
      const value = field === "sha" ? "source" : "12";
      expect(run("inbox", "push", "worker", "u", "done", ...completionArgs(worker), `--${field}`, value).code).toBe(0);
      const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
      const path = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome: { kind: "unit", state: "published", [field]: field === "pr" ? 12 : value } }]);
      expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(0);
      const criteria = await input(dir, "requirements.json", [{ id: "state", unit: "u", states: ["published"] }]);
      expect(run("requirements", "check", "--file", criteria).code).toBe(0);
      expect(JSON.parse(run("unit", "get", "u").out)).toMatchObject(field === "sha" ? { pr: "", sha: "source" } : { pr: "12", sha: "" });
    });
  }
});


describe("CLI publication during head writes", () => {
  it("preserves an old report published between the unit rename and binding write", async () => {
    const { dir, run } = await fixture();
    expect(run("unit", "set", "u", "--state", "ready", "--pr", "12", "--sha", "old").code).toBe(0);
    const worker = (await begin(dir, run, "worker")).attempt;
    const hook = await preload(dir, "unit", true);
    const child = Bun.spawn([process.execPath, "--preload", hook.path, script, "--store", dir, "--json", "unit", "set", "u", "--state", "restacked", "--sha", "new", "--attempt", worker.id], { stdout: "pipe", stderr: "pipe" });
    try {
      await waitFor(hook.marker);
      expect(run("inbox", "push", "worker", "u", "done", ...completionArgs(worker, { pr: "12", sha: "old" })).code).toBe(0);
      await writeFile(hook.release, "go");
      expect(await child.exited).toBe(0);
      const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
      const path = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome: { kind: "unit", state: "late" } }]);
      const ack = run("inbox", "ack", batch.id, "--file", path);
      expect(ack.code).toBe(1);
      expect(ack.err).toContain("completion binding changed");
      expect(JSON.parse(run("unit", "get", "u").out)).toMatchObject({ state: "restacked", sha: "new" });
      expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 1 });
    } finally {
      child.kill();
      await child.exited;
    }
  });
});


describe("CLI terminal disposition text", () => {
  it("keeps a tab in an explicit disposition readable without restoring effects", async () => {
    const { dir, run } = await fixture();
    const worker = (await begin(dir, run, "worker")).attempt;
    expect(run("attempt", "finish", worker.id, "--reason", "abandoned\tinspected").code).toBe(0);
    const result = run("attempt", "list");
    expect(result.code).toBe(0);
    expect(JSON.parse(result.out)[0].settled).toEqual({ kind: "finished", reason: "abandoned\tinspected" });
    expect(run("unit", "set", "u", "--state", "late", "--attempt", worker.id).code).toBe(1);
    expect(JSON.parse(run("unit", "get", "u").out).state).toBe("pending");
  });
});


describe("CLI bot core regressions", () => {
  it("round trips numeric saved role arms through the existing destination resolver", async () => {
    const { dir, run } = await fixture();
    const config = join(dir, ".agents");
    await mkdir(config);
    await writeFile(join(config, "pstack-models.md"), "## codex\nfeature: gpt-6.1-sol@xhigh\narena runners: gpt-6.1-sol@xhigh,gpt-6-astra@high\n");
    const contexts = await input(dir, "contexts.json", {});
    for (const [role, arm, authority, model, effort] of [
      ["feature", 1, "worker", "gpt-6.1-sol", "xhigh"],
      ["arena runners", 1, "worker", "gpt-6.1-sol", "xhigh"],
      ["arena runners", 2, "worker", "gpt-6-astra", "high"],
      ["arena runners", 2, "verifier", "gpt-6-astra", "high"],
    ] as const) {
      const path = await input(dir, `numeric-${role}-${arm}-${authority}.json`, {
        unit: "u", role, arm, authority, requestId: `${role}-${arm}-${authority}`,
        brief: "brief.md", checkout: dir, resolution: { harness: "codex", model, effort },
      });
      const result = run("attempt", "begin", "--file", path);
      expect(result.code).toBe(0);
      expect(run("attempt", "begin", "--file", path).out).toBe(result.out);
      const saved = JSON.parse(await readFile(join(dir, "attempts.json"), "utf8")).find((row: { requestId: string }) => row.requestId === `${role}-${arm}-${authority}`);
      expect(saved).toMatchObject({ role, arm, authority });
      const resolver = Bun.spawnSync(["python3", join(import.meta.dir, "../../../../../skills/setup-pstack/scripts/resolve-resume.py"),
        "--source", "claude-code", "--role", saved.role, "--arm", String(saved.arm),
        "--project", dir, "--user-file", join(dir, "absent-user"), "--contexts", contexts],
        { env: { ...process.env, CODEX_HOME: join(dir, "absent-catalog"), PYTHONDONTWRITEBYTECODE: "1" } });
      expect(resolver.exitCode).toBe(1);
      const candidate = JSON.parse(resolver.stdout.toString()).candidates[0];
      expect(candidate.resolution).toEqual({ role, arm, model, effort, source: "workspace ## codex" });
      expect(candidate.eligible).toBe(false);
      expect(candidate.reason).toBe("destination availability, route or version is unobserved");
    }
    expect(JSON.parse(run("attempt", "list").out)).toHaveLength(4);
  });
  for (const arm of [0, -1, 1.5, "sol", "1", "nonnumeric"]) {
    it(`rejects invalid saved numeric arm ${JSON.stringify(arm)}`, async () => {
      const { dir, run } = await fixture();
      const path = await input(dir, "invalid.json", {
        unit: "u", role: "arena runners", arm, authority: "worker", requestId: "invalid",
        brief: "brief.md", checkout: dir, resolution: { harness: "codex", model: "gpt-6.1-sol", effort: "xhigh" },
      });
      expect(run("attempt", "begin", "--file", path).code).toBe(1);
      expect(JSON.parse(run("attempt", "list").out)).toEqual([]);
      const valid = await input(dir, "valid.json", { ...JSON.parse(await readFile(path, "utf8")), arm: 1 });
      expect(run("attempt", "begin", "--file", valid).code).toBe(0);
      expect(JSON.parse(run("attempt", "list").out)[0].arm).toBe(1);
    });
  }
  it("rejects arm 2 for a canonical non-panel role", async () => {
    const { dir, run } = await fixture();
    const path = await input(dir, "single.json", {
      unit: "u", role: "feature", arm: 2, authority: "worker", requestId: "single",
      brief: "brief.md", checkout: dir, resolution: { harness: "codex", model: "gpt-6.1-sol", effort: "xhigh" },
    });
    expect(run("attempt", "begin", "--file", path).code).toBe(1);
    await input(dir, "single.json", { ...JSON.parse(await readFile(path, "utf8")), arm: 1 });
    expect(run("attempt", "begin", "--file", path).code).toBe(0);
    expect(JSON.parse(run("attempt", "list").out)[0].arm).toBe(1);
  });
  it("does not read completed history during routine real CLI operations", async () => {
    const { dir, run } = await fixture();
    const history: string[] = [join(dir, "inbox-batches")];
    for (let i = 0; i < 5; i++) {
      expect(run("inbox", "push", "worker", "u", `done-${i}`).code).toBe(0);
      const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
      const path = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome: { kind: "unit", state: `accepted-${i}` } }]);
      expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(0);
      history.push(join(dir, "inbox-batches", batch.id));
    }
    const hook = join(dir, "history-reads.ts");
    await writeFile(hook, `
import { mock } from "bun:test";
import * as original from "node:fs/promises";
const fs = { ...original };
const history = ${JSON.stringify(history)};
function check(path) {
  if (history.some(root => String(path) === root || String(path).startsWith(root + "/"))) throw new Error("completed history read: " + path);
}
mock.module("node:fs/promises", () => ({ ...fs,
  readFile: async (path, ...args) => { check(path); return fs.readFile(path, ...args); },
  readdir: async (path, ...args) => { check(path); return fs.readdir(path, ...args); }
}));
`);
    const guarded = (...args: string[]) => {
      const result = Bun.spawnSync([process.execPath, "--preload", hook, script, "--store", dir, "--json", ...args]);
      expect(result.stderr.toString()).not.toContain("completed history read");
      expect(result.exitCode).toBe(0);
      return JSON.parse(result.stdout.toString());
    };
    expect(guarded("inbox", "count")).toEqual({ count: 0 });
    expect(guarded("inbox", "drain", "--peek")).toEqual([]);
    expect(guarded("inbox", "drain", "--receipt")).toBeNull();
    expect(guarded("unit", "get", "u").state).toBe("accepted-4");
    expect(guarded("unit", "set", "u", "--state", "ready").state).toBe("ready");
    const request = await input(dir, "worker.json", {
      unit: "u", role: "feature", arm: 1, authority: "worker", requestId: "worker",
      brief: "brief.md", checkout: dir, resolution: { harness: "codex", model: "gpt-6.1-sol", effort: "xhigh" },
    });
    const worker = guarded("attempt", "begin", "--file", request);
    expect(worker).toMatchObject({ role: "feature", arm: 1 });
    const observation = await input(dir, "observation.json", { kind: "unknown" });
    expect(guarded("attempt", "observe", worker.id, "--file", observation).observation).toEqual({ kind: "unknown" });
    expect(guarded("unit", "set", "u", "--state", "ready", "--pr", "12", "--sha", "head", "--attempt", worker.id)).toMatchObject({ pr: "12", sha: "head" });
    expect(guarded("ledger", "record", "12", "head", "unit-test-verified", "--evidence", "proof", "--attempt", worker.id).verdict).toBe("unit-test-verified");
    expect(guarded("attempt", "finish", worker.id, "--reason", "confirmed complete").settled).toEqual({ kind: "finished", reason: "confirmed complete" });
    expect(guarded("attempt", "list")[0].id).toBe(worker.id);
    const criteria = await input(dir, "requirements.json", [{ id: "state", unit: "u", states: ["ready"], ledger: { pr: 12, sha: "head", verdicts: ["unit-test-verified"] } }]);
    expect(guarded("requirements", "check", "--file", criteria)).toEqual({ ok: true, failures: [], pendingEvents: 0, pendingAttempts: [] });
    expect(run("inbox", "push", "new", "u", "waiting").code).toBe(0);
    expect(run("inbox", "push", "later", "u", "waiting").code).toBe(0);
    expect(guarded("inbox", "count")).toEqual({ count: 2 });
    expect(guarded("inbox", "drain", "--peek")[0].agent).toBe("new");
    const active = guarded("inbox", "drain", "--receipt");
    expect(active.events[0].pointer.agent).toBe("new");
    const ack = await input(dir, "active.json", [{ event: active.events[0].id, outcome: { kind: "discard", reason: "reviewed" } }]);
    expect(guarded("inbox", "ack", active.id, "--file", ack)).toEqual({ id: active.id, events: [active.events[1]] });
    expect(guarded("inbox", "count")).toEqual({ count: 1 });
    expect(guarded("inbox", "drain", "--receipt")).toEqual({ id: active.id, events: [active.events[1]] });
    const last = await input(dir, "last-active.json", [{ event: active.events[1].id, outcome: { kind: "discard", reason: "reviewed" } }]);
    expect(guarded("inbox", "ack", active.id, "--file", last)).toEqual({ id: active.id, events: [] });
    expect(guarded("inbox", "count")).toEqual({ count: 0 });
    expect(guarded("inbox", "drain", "--receipt")).toBeNull();
    const blocked = Bun.spawnSync([process.execPath, "--preload", hook, script, "--store", dir, "--json", "inbox", "receipts"]);
    expect(blocked.exitCode).toBe(1);
    expect(blocked.stderr.toString()).toContain("completed history read");
    const receipts = JSON.parse(run("inbox", "receipts").out);
    expect(receipts.filter((row: { decisions: unknown[] }) => row.decisions.length === 1)).toHaveLength(5);
    expect(receipts.find((row: { id: string }) => row.id === active.id).decisions).toHaveLength(2);
    expect(receipts).toHaveLength(6);
  });
});


describe("CLI pending collection crash invariants", () => {
  it("keeps a partial receipt pending when killed after decision completion", async () => {
    const { dir, run } = await fixture();
    expect(run("inbox", "push", "first", "u", "done").code).toBe(0);
    expect(run("inbox", "push", "second", "u", "waiting").code).toBe(0);
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    const path = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome: { kind: "unit", state: "accepted" } }]);
    await killAt(dir, "complete", ["inbox", "ack", batch.id, "--file", path]);
    expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 1 });
    expect(JSON.parse(run("unit", "get", "u").out).state).toBe("accepted");
    expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(0);
    const pending = JSON.parse(run("inbox", "drain", "--receipt").out);
    expect(pending.id).toBe(batch.id);
    expect(pending.events.map((row: { id: string }) => row.id)).toEqual([batch.events[1].id]);
    expect(await readdir(join(dir, "inbox-pending"))).toEqual([batch.id]);
    expect(await readdir(join(dir, "inbox-batches"))).toEqual([]);
    const receipt = JSON.parse(run("inbox", "receipts").out)[0];
    expect(receipt.events).toHaveLength(2);
    expect(receipt.decisions).toMatchObject([{ event: batch.events[0].id, completed: true }]);
  });
  for (const point of ["complete", "archive-before", "archive"] as const) {
    it(`retains a consumed receipt killed at ${point} and accepts a historical retry after finish`, async () => {
      const { dir, run } = await fixture();
      const worker = (await begin(dir, run, "worker")).attempt;
      expect(run("inbox", "push", "worker", "u", "done", ...completionArgs(worker, { pr: "12", sha: "head" })).code).toBe(0);
      const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
      const path = await input(dir, "ack.json", [{ event: batch.events[0].id, outcome: {
        kind: "unit", state: "published", pr: 12, sha: "head",
        ledger: { kind: "verdict", pr: 12, sha: "head", verdict: "unit-test-verified", evidence: "proof" },
      } }]);
      await killAt(dir, point, ["inbox", "ack", batch.id, "--file", path]);
      expect(run("inbox", "push", "arrival", "u", "waiting").code).toBe(0);
      expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 1 });
      expect(await readdir(join(dir, "inbox-pending"))).toEqual([]);
      expect(await readdir(join(dir, "inbox-batches"))).toEqual([batch.id]);
      expect(JSON.parse(run("unit", "get", "u").out)).toMatchObject({ state: "published", pr: "12", sha: "head" });
      const ledger = run("ledger", "check", "12", "head").out;
      expect(JSON.parse(ledger).verdict).toBe("unit-test-verified");
      expect(run("unit", "set", "u", "--state", "merged", "--sha", "new", "--attempt", worker.id).code).toBe(0);
      expect(run("attempt", "finish", worker.id, "--reason", "confirmed complete").code).toBe(0);
      const attempts = run("attempt", "list").out;
      expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(0);
      expect(run("attempt", "list").out).toBe(attempts);
      expect(run("ledger", "check", "12", "head").out).toBe(ledger);
      expect(JSON.parse(run("unit", "get", "u").out)).toMatchObject({ state: "merged", sha: "new" });
      expect(run("unit", "set", "u", "--state", "late", "--attempt", worker.id).code).toBe(1);
      const receipt = JSON.parse(run("inbox", "receipts").out).find((row: { id: string }) => row.id === batch.id);
      expect(receipt.events[0].pointer.completion.sha).toBe("head");
      expect(receipt.decisions[0]).toMatchObject({ completed: true, unit: { state: "published" }, attempt: { settled: { kind: "accepted" } } });
      expect(JSON.parse(run("inbox", "drain", "--receipt").out).events[0].pointer.agent).toBe("arrival");
    });
  }
  it("recovers registered pending events and concurrent arrivals after SIGKILL during claim", async () => {
    const { dir, run } = await fixture();
    expect(run("inbox", "push", "first", "u", "done").code).toBe(0);
    const hook = await preload(dir, "claim", true);
    const child = Bun.spawn([process.execPath, "--preload", hook.path, script, "--store", dir, "--json", "inbox", "drain", "--receipt"], { stdout: "pipe", stderr: "pipe" });
    try {
      await waitFor(hook.marker);
      expect(run("inbox", "push", "arrival", "u", "later").code).toBe(0);
      child.kill("SIGKILL");
      expect(await child.exited).not.toBe(0);
      expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 2 });
      const first = JSON.parse(run("inbox", "drain", "--receipt").out);
      expect(first.events.map((row: { pointer: { agent: string } }) => row.pointer.agent)).toEqual(["first"]);
      const path = await input(dir, "ack.json", [{ event: first.events[0].id, outcome: { kind: "discard", reason: "reviewed" } }]);
      expect(run("inbox", "ack", first.id, "--file", path).code).toBe(0);
      const second = JSON.parse(run("inbox", "drain", "--receipt").out);
      expect(second.events.map((row: { pointer: { agent: string } }) => row.pointer.agent)).toEqual(["arrival"]);
      expect(second.id).not.toBe(first.id);
    } finally {
      child.kill();
      await child.exited;
    }
  });
  for (const point of ["migration", "migration-marker"] as const) {
    it(`replays unfinished legacy batch decisions after SIGKILL at ${point}`, async () => {
      const { dir, run } = await fixture();
      expect(run("inbox", "push", "history", "u", "old").code).toBe(0);
      const historical = JSON.parse(run("inbox", "drain", "--receipt").out);
      const historyAck = await input(dir, "history.json", [{ event: historical.events[0].id, outcome: { kind: "discard", reason: "retained" } }]);
      expect(run("inbox", "ack", historical.id, "--file", historyAck).code).toBe(0);
      expect(run("inbox", "push", "first", "u", "done").code).toBe(0);
      expect(run("inbox", "push", "second", "u", "waiting").code).toBe(0);
      const legacy = JSON.parse(run("inbox", "drain", "--receipt").out);
      const path = await input(dir, "legacy.json", [{ event: legacy.events[0].id, outcome: { kind: "unit", state: "replayed" } }]);
      await killAt(dir, "decision", ["inbox", "ack", legacy.id, "--file", path]);
      await rename(join(dir, "inbox-pending", legacy.id), join(dir, "inbox-batches", legacy.id));
      await rm(join(dir, ".inbox-pending-migrated"));
      await rm(join(dir, "fault-marker"));
      await killAt(dir, point, ["inbox", "count"]);
      expect(run("inbox", "push", "arrival", "u", "later").code).toBe(0);
      expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 2 });
      expect(JSON.parse(run("unit", "get", "u").out).state).toBe("replayed");
      expect(await readFile(join(dir, ".inbox-pending-migrated"), "utf8")).toBe("1\n");
      const pending = JSON.parse(run("inbox", "drain", "--receipt").out);
      expect(pending.id).toBe(legacy.id);
      expect(pending.events.map((row: { id: string }) => row.id)).toEqual([legacy.events[1].id]);
      expect(run("inbox", "ack", historical.id, "--file", historyAck).code).toBe(0);
      expect(run("inbox", "ack", legacy.id, "--file", path).code).toBe(0);
      const last = await input(dir, "last.json", [{ event: legacy.events[1].id, outcome: { kind: "discard", reason: "reviewed" } }]);
      expect(run("inbox", "ack", legacy.id, "--file", last).code).toBe(0);
      expect((await readdir(join(dir, "inbox-batches"))).sort()).toEqual([historical.id, legacy.id].sort());
      const receipts = JSON.parse(run("inbox", "receipts").out);
      expect(receipts.find((row: { id: string }) => row.id === legacy.id).decisions).toHaveLength(2);
      expect(JSON.parse(run("inbox", "drain", "--receipt").out).events[0].pointer.agent).toBe("arrival");
    });
  }
  it("adopts legacy renamed five-cell drains into the pending collection", async () => {
    const { dir, run } = await fixture();
    expect(run("inbox", "push", "legacy", "u", "done").code).toBe(0);
    await rename(join(dir, "inbox"), join(dir, ".inbox-drain-legacy"));
    expect(JSON.parse(run("inbox", "count").out)).toEqual({ count: 1 });
    const batch = JSON.parse(run("inbox", "drain", "--receipt").out);
    expect(batch.id).toBe("inbox-drain-legacy");
    expect(batch.events[0].pointer.agent).toBe("legacy");
    const path = await input(dir, "legacy.json", [{ event: batch.events[0].id, outcome: { kind: "unit", state: "adopted" } }]);
    expect(run("inbox", "ack", batch.id, "--file", path).code).toBe(0);
    expect(JSON.parse(run("unit", "get", "u").out).state).toBe("adopted");
    expect(await readdir(join(dir, "inbox-batches"))).toEqual([batch.id]);
  });
});
