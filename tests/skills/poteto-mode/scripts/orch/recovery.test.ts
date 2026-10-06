import { afterEach, describe, expect, it } from "bun:test";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
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
  point: "claim" | "emission" | "unit" | "decision",
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
    await fs.rename(from, to);
    if (String(from).endsWith("/inbox")) claimed = true;
    if (${JSON.stringify(point)} === "claim" && String(from).endsWith("/inbox")) await stop();
    if (${JSON.stringify(point)} === "unit" && String(to).endsWith("/units.tsv")) await stop();
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
  point: "claim" | "emission" | "unit" | "decision",
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
) {
  const path = await input(dir, `${requestId}.json`, {
    unit: "u",
    role: authority === "worker" ? "feature" : "trail reviewer",
    arm: "sol",
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
        run("inbox", "push", "agent", "u", verdict, "--attempt", id).code,
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
      run("inbox", "push", "verifier", "u", "passed", "--attempt", verifier.id)
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
      run("inbox", "push", "worker", "u", "done", "--attempt", worker.id).code,
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
    const first = await begin(dir, run, "first");
    const request = JSON.parse(await readFile(first.path, "utf8"));
    const other = await input(dir, "other.json", {
      ...request,
      requestId: "other",
      arm: "astra",
      resolution: { harness: "codex", model: "gpt-6-astra", effort: "high" },
    });
    const result = run("attempt", "begin", "--file", other);
    expect(result.code).toBe(0);
    const second = JSON.parse(result.out);
    expect(second).toMatchObject({
      unit: "u",
      role: "feature",
      arm: "astra",
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
