import { describe, expect, it } from "bun:test";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { FailedCheckEvidence, JUnitRecord } from "../../../../../skills/poteto-mode/scripts/watch-pr/failed-check-evidence.ts";
import { main } from "../../../../../skills/poteto-mode/scripts/watch-pr/failed-check-cli.ts";
import { parseRunId } from "../../../../../skills/poteto-mode/scripts/watch-pr/failed-check-evidence.ts";

const SOURCE = join(import.meta.dir, "../../../../../skills/poteto-mode/scripts/watch-pr");
const HEAD = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const RUN = "repos/mdsmithaustin/pstack/actions/runs/9100226";
interface Fixture {
  run: { id: number; head_sha: string; run_attempt: number; status: string; conclusion: string };
  artifacts: { total_count: number; artifacts: Array<{ id: number; name: string; size_in_bytes: number; expired: boolean; archive_download_url?: string; workflow_run: { id: number; head_sha: string } }> };
  jobLog: string;
  archives: Record<string, Record<string, string>>;
}
function fixture(): Fixture {
  return JSON.parse(readFileSync(join(import.meta.dir, "fixtures/failed-check-226.json"), "utf8"));
}
function zip(entries: Record<string, string>, options: { permissions?: number; deflate?: boolean } = {}): Buffer {
  const program = "import io,json,sys,zipfile\nv=json.load(sys.stdin);b=io.BytesIO()\nwith zipfile.ZipFile(b,'w') as z:\n for n,t in v['entries'].items():\n  i=zipfile.ZipInfo(n);i.external_attr=v.get('permissions',0o100644)<<16;i.compress_type=zipfile.ZIP_DEFLATED if v.get('deflate') else zipfile.ZIP_STORED;z.writestr(i,t)\nsys.stdout.buffer.write(b.getvalue())";
  const result = Bun.spawnSync(["python3", "-c", program], { stdin: Buffer.from(JSON.stringify({ entries, ...options })) });
  if (result.exitCode !== 0) throw new Error(new TextDecoder().decode(result.stderr));
  return Buffer.from(result.stdout);
}
interface Response {
  readonly data?: string;
  readonly code?: number;
  readonly overflow?: number;
}
interface Scenario {
  readonly input?: Fixture;
  readonly archives?: Record<string, Buffer>;
  readonly finalRun?: Fixture["run"];
  readonly finalCode?: number;
  readonly logs?: Buffer;
  readonly noPython?: boolean;
  readonly hangPython?: boolean;
  readonly overflowArtifact?: string;
  readonly args?: readonly string[];
  readonly host?: string;
  readonly secondInventory?: Fixture["artifacts"];
}
function command(scenario: Scenario = {}): { code: number; report: FailedCheckEvidence; output: string; requests: string[][] } {
  const directory = mkdtempSync(join(tmpdir(), "failed-check-evidence-"));
  const input = scenario.input ?? fixture();
  try {
    const responses: Record<string, Response | readonly Response[]> = {
      [RUN]: [{ data: Buffer.from(JSON.stringify(input.run)).toString("base64") }, scenario.finalCode ? { code: scenario.finalCode } : { data: Buffer.from(JSON.stringify(scenario.finalRun ?? input.run)).toString("base64") }],
      [`${RUN}/artifacts?per_page=50&page=1`]: { data: Buffer.from(JSON.stringify(input.artifacts)).toString("base64") },
      [`${RUN}/attempts/${input.run.run_attempt}/logs`]: { data: (scenario.logs ?? zip({ "failed-job.txt": input.jobLog })).toString("base64") },
    };
    if (scenario.secondInventory) responses[`${RUN}/artifacts?per_page=50&page=2`] = { data: Buffer.from(JSON.stringify(scenario.secondInventory)).toString("base64") };
    for (const artifact of input.artifacts.artifacts) {
      const key = String(artifact.id);
      const bytes = scenario.archives?.[key] ?? (input.archives[key] ? zip(input.archives[key]) : null);
      responses[`repos/mdsmithaustin/pstack/actions/artifacts/${key}/zip`] = scenario.overflowArtifact === key ? { overflow: 8 * 1024 * 1024 + 1 } : bytes ? { data: bytes.toString("base64") } : { code: 1 };
    }
    writeFileSync(join(directory, "responses.json"), JSON.stringify(responses));
    const script = `#!${process.execPath}\nimport { readFileSync, appendFileSync, writeFileSync } from 'node:fs';\nconst root=process.env.EVIDENCE_CASE;const args=process.argv.slice(2);appendFileSync(root+'/requests',JSON.stringify(args)+'\\n');\nif(args[0]!=='api'||args[1]!=='--hostname'||args[3]!=='--method'||args[4]!=='GET')process.exit(91);\nconst path=args[5];const data=JSON.parse(readFileSync(root+'/responses.json','utf8'));let value=data[path];if(!value)process.exit(92);\nif(Array.isArray(value)){let n=0;try{n=Number(readFileSync(root+'/run-count','utf8'));}catch{}writeFileSync(root+'/run-count',String(n+1));value=value[Math.min(n,value.length-1)];}\nif(value.overflow)process.stdout.write(Buffer.alloc(value.overflow,65));else if(value.data)process.stdout.write(Buffer.from(value.data,'base64'));process.exitCode=value.code??0;\n`;
    writeFileSync(join(directory, "gh"), script);
    chmodSync(join(directory, "gh"), 0o755);
    if (scenario.hangPython) {
      writeFileSync(join(directory, "python3"), `#!${process.execPath}\nsetTimeout(()=>{},30000);\n`);
      chmodSync(join(directory, "python3"), 0o755);
    }
    const args = scenario.args ?? ["--owner", "mdsmithaustin", "--repo", "pstack", "--run", "9100226", "--head", HEAD, "--attempt", String(input.run.run_attempt)];
    const result = Bun.spawnSync([process.execPath, join(SOURCE, "failed-check-evidence"), ...args], {
      env: { ...process.env, GH_HOST: scenario.host ?? "github.com", EVIDENCE_CASE: directory, PATH: scenario.noPython ? directory : `${directory}:${process.env.PATH ?? ""}` },
    });
    const output = new TextDecoder().decode(result.stdout);
    if (!output.trim()) throw new Error(`diagnostic produced no receipt: ${result.exitCode} ${new TextDecoder().decode(result.stderr)}`);
    return { code: result.exitCode, output, report: JSON.parse(output), requests: readFileSync(join(directory, "requests"), "utf8").trim().split("\n").map((line) => JSON.parse(line)) };
  } finally { rmSync(directory, { recursive: true, force: true }); }
}
function verified(report: FailedCheckEvidence): readonly JUnitRecord[] {
  if (report.kind !== "verified") throw new Error("expected verified run receipt");
  return report.records;
}
function onlyAvailable(input: Fixture): Fixture {
  input.artifacts.artifacts = input.artifacts.artifacts.slice(0, 1);
  input.artifacts.total_count = 1;
  return input;
}

describe("failed-check evidence production command", () => {
  it("recovers literal JUnit assertions after the recorded log stops", () => {
    const result = command();
    expect(result.code).toBe(2);
    expect(verified(result.report).map((row) => [row.artifactId, row.testName, row.kind, row.message, row.body])).toEqual([
      ["22601", "recovers truncated assertion", "failure", "expected checked head", "Traceback: fixture_test.py:42\nAssertionError: expected aaaaaaaa, got bbbbbbbb"],
      ["22601", "recovers truncated assertion", "error", "transport disconnected", "ConnectionError: artifact stream disconnected"],
      ["22602", "retains second artifact", "failure", "missing failure text", "AssertionError: second artifact evidence"],
    ]);
    expect<unknown>(result.report.requested).toEqual({ repository: { host: "github.com", owner: "mdsmithaustin", repo: "pstack" }, runId: "9100226", checkedHead: HEAD, attempt: 1 });
    if (result.report.kind !== "verified") throw new Error("wrong receipt kind");
    expect(result.report.logs).toEqual([{ member: "failed-job.txt", text: "2026-10-01T12:00:00Z Run bun test\n2026-10-01T12:00:01Z Starting failed-check diagnostic tests\n[log truncated before assertion]\n" }]);
    expect(result.report.gaps.map((gap) => [gap.kind, gap.scope])).toEqual([["expired", "artifact 22603 test-results-expired"], ["inaccessible", "artifact 22604 test-results-inaccessible"]]);
    expect(result.requests.map((args) => args.slice(0, 5))).toEqual(Array(7).fill(["api", "--hostname", "github.com", "--method", "GET"]));
    expect(result.requests.map((args) => args[5])).toEqual([RUN, `${RUN}/attempts/1/logs`, `${RUN}/artifacts?per_page=50&page=1`, "repos/mdsmithaustin/pstack/actions/artifacts/22601/zip", "repos/mdsmithaustin/pstack/actions/artifacts/22602/zip", "repos/mdsmithaustin/pstack/actions/artifacts/22604/zip", RUN]);
  });
  it("reports missing artifacts for the exact verified run", () => {
    const input = fixture(); input.artifacts = { total_count: 0, artifacts: [] };
    const result = command({ input });
    expect(result.report.kind).toBe("verified");
    expect(result.report.gaps).toEqual([{ kind: "missing", scope: "inventory", detail: "no artifacts available for this Actions run", omitted: 0 }]);
  });
  it("refuses a different checked head before any archive request", () => {
    const input = fixture(); input.run.head_sha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    const result = command({ input });
    expect<unknown>(result.report).toEqual({ kind: "unverified", requested: { repository: { host: "github.com", owner: "mdsmithaustin", repo: "pstack" }, runId: "9100226", checkedHead: HEAD, attempt: 1 }, gaps: [{ kind: "identity-mismatch", scope: "run", detail: "Actions run id, checked head or attempt did not match", omitted: 0 }] });
    expect(result.requests).toEqual([["api", "--hostname", "github.com", "--method", "GET", RUN]]);
  });
  for (const failure of ["head drift", "attempt drift", "final read unavailable"]) {
    it(`discards all attributed records after ${failure}`, () => {
      const changed = { ...fixture().run, ...(failure === "head drift" ? { head_sha: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" } : { run_attempt: 2 }) };
      const result = command(failure === "final read unavailable" ? { finalCode: 1 } : { finalRun: changed });
      expect(result.report.kind).toBe("unverified");
      expect(result.report.gaps.at(-1)?.scope).toBe("run");
      expect("records" in result.report).toBe(false);
      expect(result.requests.at(-1)?.[5]).toBe(RUN);
    });
  }
  it("retains run/head evidence with unknown rerun attempt attribution", () => {
    const input = onlyAvailable(fixture()); input.run.run_attempt = 2;
    const result = command({ input });
    expect(verified(result.report).map((row) => [row.testName, row.attemptBinding])).toEqual([["recovers truncated assertion", "run-only"], ["recovers truncated assertion", "run-only"]]);
    expect(result.report.gaps).toEqual([{ kind: "attempt-unbound", scope: "artifact 22601 test-results-linux", detail: "artifact metadata does not establish its rerun attempt", omitted: 0 }]);
  });
  it("keeps available evidence without a completed failed workflow restriction", () => {
    const input = onlyAvailable(fixture()); input.run.status = "in_progress"; input.run.conclusion = "";
    const result = command({ input });
    expect(result.code).toBe(0);
    expect(verified(result.report).map((row) => row.kind)).toEqual(["failure", "error"]);
  });
  it("ignores artifact labels and download URLs when binding evidence", () => {
    const input = onlyAvailable(fixture());
    input.artifacts.artifacts[0].name = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    input.artifacts.artifacts[0].archive_download_url = "https://unrelated.example/another-run.zip";
    const result = command({ input });
    expect(verified(result.report).map((row) => row.testName)).toEqual(["recovers truncated assertion", "recovers truncated assertion"]);
    expect(result.requests.map((args) => args[5])).toEqual([RUN, `${RUN}/attempts/1/logs`, `${RUN}/artifacts?per_page=50&page=1`, "repos/mdsmithaustin/pstack/actions/artifacts/22601/zip", RUN]);
  });
  it("rejects an artifact belonging to another run and preserves other artifacts", () => {
    const input = fixture(); input.artifacts.artifacts[0].workflow_run.id = 99;
    const result = command({ input });
    expect(verified(result.report).map((row) => row.testName)).toEqual(["retains second artifact"]);
    expect(result.report.gaps[0]).toEqual({ kind: "identity-mismatch", scope: "artifact 22601 test-results-linux", detail: "artifact run or head did not match", omitted: 0 });
    expect(result.requests.map((args) => args[5])).not.toContain("repos/mdsmithaustin/pstack/actions/artifacts/22601/zip");
  });
  it("keeps binary downloads bounded and preserves a later safe artifact", () => {
    const result = command({ overflowArtifact: "22601" });
    expect(verified(result.report).map((row) => row.testName)).toEqual(["retains second artifact"]);
    expect(result.report.gaps[0]).toEqual({ kind: "limit", scope: "artifact 22601 test-results-linux", detail: "gh stdout byte limit exceeded", omitted: 0 });
  });
  it("reports Python unavailability as an explicit retrieval gap", () => {
    const result = command({ input: onlyAvailable(fixture()), noPython: true });
    expect(result.report.kind).toBe("verified");
    expect(result.report.gaps.map((gap) => [gap.kind, gap.detail])).toEqual([["unavailable", "python3 unavailable"], ["unavailable", "python3 unavailable"]]);
  });
  it("kills and reaps a stalled parser under its deadline", () => {
    const input = onlyAvailable(fixture());
    const result = command({ input, logs: Buffer.from("not a zip"), hangPython: true });
    expect(result.report.kind).toBe("verified");
    expect(result.report.gaps.map((gap) => [gap.kind, gap.detail])).toEqual([["timeout", "python3 deadline reached"], ["timeout", "python3 deadline reached"]]);
  }, 10000);
  it("routes Enterprise-host reads without inspecting the current PR", () => {
    const result = command({ input: onlyAvailable(fixture()), host: "github.example.com" });
    expect(result.report.requested.repository).toEqual({ host: "github.example.com", owner: "mdsmithaustin", repo: "pstack" });
    expect(result.requests.map((args) => args[2])).toEqual(Array(5).fill("github.example.com"));
  });
  it("truncates long fields and globally bounds records across artifacts", () => {
    const input = fixture(); input.artifacts.artifacts = input.artifacts.artifacts.slice(0, 2); input.artifacts.total_count = 2;
    const xml = `<testsuite>${Array.from({ length: 50 }, (_, i) => `<testcase name="case${i}"><failure>${"failure evidence ".repeat(300)}</failure></testcase>`).join("")}</testsuite>`;
    const result = command({ input, archives: { "22601": zip({ "results.xml": xml }), "22602": zip({ "results.xml": xml }) } });
    const rows = verified(result.report);
    expect(rows[0].testName).toBe("case0");
    expect(rows[0].body).toBe("failure evidence ".repeat(120) + "failure ");
    expect(rows.length).toBeLessThanOrEqual(32);
    expect(result.report.gaps.map((gap) => gap.kind)).toContain("limit");
    expect(Buffer.byteLength(result.output)).toBeLessThanOrEqual(65536);
  });
  it("bounds inventory pages and preserves final identity gaps after many expired artifacts", () => {
    const input = fixture();
    const items = Array.from({ length: 100 }, (_, i) => ({ id: 1000 + i, name: `expired-${i}`, size_in_bytes: 100, expired: true, workflow_run: { id: 9100226, head_sha: HEAD } }));
    input.artifacts = { total_count: 101, artifacts: items.slice(0, 50) };
    const result = command({ input, secondInventory: { total_count: 101, artifacts: items.slice(50) }, finalRun: { ...input.run, run_attempt: 2 } });
    expect(result.report.kind).toBe("unverified");
    expect(result.report.gaps).toContainEqual({ kind: "limit", scope: "inventory", detail: "artifact inventory incomplete", omitted: 1 });
    expect(result.report.gaps).toContainEqual({ kind: "identity-mismatch", scope: "run", detail: "Actions run id, checked head or attempt did not match", omitted: 0 });
    expect(result.report.gaps.length).toBeLessThanOrEqual(64);
    expect(result.requests.map((args) => args[5])).toEqual([RUN, `${RUN}/attempts/1/logs`, `${RUN}/artifacts?per_page=50&page=1`, `${RUN}/artifacts?per_page=50&page=2`, RUN]);
  });
  it("bounds serialized pretty JSON and reports its omissions in the exit code", async () => {
    const row: JUnitRecord = { artifactId: "22601", artifactName: "results", member: "results.xml", testName: "literal test", classname: "literal class", kind: "failure", message: "\t".repeat(256), type: "AssertionError", body: "\t".repeat(2048), attemptBinding: "verified-first-attempt" };
    let output = "";
    const code = await main(["--owner", "mdsmithaustin", "--repo", "pstack", "--run", "9100226", "--head", HEAD, "--attempt", "1", "--pretty"], {
      reader: { recover: async (requested) => ({ kind: "verified", requested, records: Array(32).fill(row), logs: [], gaps: [] }) },
      stdout: (value) => { output += value; }, stderr: () => {},
    });
    const report: FailedCheckEvidence = JSON.parse(output);
    expect(code).toBe(2);
    expect(Buffer.byteLength(output)).toBeLessThanOrEqual(65536);
    expect(verified(report)[0].testName).toBe("literal test");
    expect(report.gaps.map((gap) => [gap.kind, gap.detail])).toEqual([["limit", "serialized evidence omitted"]]);
  });
  it("rejects an abbreviated checked head before calling the reader", async () => {
    let error = "";
    const code = await main(["--owner", "mdsmithaustin", "--repo", "pstack", "--run", "9100226", "--head", "aaaaaaaa", "--attempt", "1"], {
      reader: { recover: async () => { throw new Error("unexpected network read"); } },
      stdout: () => {}, stderr: (value) => { error += value; },
    });
    expect(code).toBe(64);
    expect(error).toContain("must be a full hexadecimal commit SHA");
    expect(() => parseRunId("9007199254740993")).toThrow("run id must be a positive safe integer");
  });
});

describe("untrusted archive bytes through the production reader", () => {
  const xml = "<testsuite><testcase name=\"literal safe test\"><failure>literal failure evidence</failure></testcase></testsuite>";
  const cases: Array<[string, () => Buffer, string]> = [
    ["traversal", () => zip({ "../escape.xml": xml }), "unsafe ZIP member path"],
    ["absolute path", () => zip({ "/escape.xml": xml }), "unsafe ZIP member path"],
    ["drive path", () => zip({ "C:/escape.xml": xml }), "unsafe ZIP member path"],
    ["backslash", () => zip({ "dir\\escape.xml": xml }), "unsafe ZIP member path"],
    ["symlink", () => zip({ "results.xml": xml }, { permissions: 0o120777 }), "symlink, special or executable ZIP member"],
    ["executable", () => zip({ "results.xml": xml }, { permissions: 0o100755 }), "symlink, special or executable ZIP member"],
    ["compression bomb", () => zip({ "results.xml": "x".repeat(500000) }, { deflate: true }), "ZIP member size or compression ratio limit exceeded"],
    ["deep XML", () => zip({ "results.xml": "<testsuite>" + "<a>".repeat(64) + "</a>".repeat(64) + "</testsuite>" }), "XML element, depth or attribute limit exceeded"],
    ["large XML attributes", () => zip({ "results.xml": `<testsuite name="${"x".repeat(16385)}"/>` }), "XML element, depth or attribute limit exceeded"],
    ["XML element count", () => zip({ "results.xml": `<testsuite>${"<a/>".repeat(50000)}</testsuite>` }), "XML element, depth or attribute limit exceeded"],
    ["entity expansion", () => zip({ "results.xml": '<!DOCTYPE testsuite [<!ENTITY x "EXPANDED">]><testsuite><testcase name="bad"><failure>&x;</failure></testcase></testsuite>' }), "XML DTD or entity declaration is forbidden"],
    ["malformed XML suffix", () => zip({ "results.xml": xml + "<trailing>" }), "junk after document element"],
    ["unsafe later member", () => zip({ "results.xml": xml, "../later.txt": "unsafe" }), "unsafe ZIP member path"],
  ];
  for (const [name, bytes, detail] of cases) {
    it(`rejects ${name} without accepting earlier partial records`, () => {
      const result = command({ input: onlyAvailable(fixture()), archives: { "22601": bytes() } });
      expect(result.report.kind).toBe("verified");
      expect(verified(result.report)).toEqual([]);
      expect(result.report.gaps).toEqual([{ kind: "unsafe", scope: "artifact 22601 test-results-linux", detail: expect.stringContaining(detail), omitted: 0 }]);
    });
  }
  it("rejects a forged low entry count before allocating the ZIP member list", () => {
    const bytes = zip(Object.fromEntries(Array.from({ length: 129 }, (_, i) => [`${i}.txt`, "x"])));
    const end = bytes.lastIndexOf(Buffer.from("PK\x05\x06")); bytes.writeUInt16LE(1, end + 8); bytes.writeUInt16LE(1, end + 10);
    const result = command({ input: onlyAvailable(fixture()), archives: { "22601": bytes } });
    expect(result.report.gaps).toEqual([{ kind: "unsafe", scope: "artifact 22601 test-results-linux", detail: "ZIP entry limit exceeded", omitted: 0 }]);
  });
  it("rejects UTF-16 entity declarations through the actual parser callbacks", () => {
    const program = "import io,sys,zipfile\nb=io.BytesIO()\nwith zipfile.ZipFile(b,'w') as z:z.writestr('results.xml','<?xml version=\"1.0\" encoding=\"UTF-16\"?><!DOCTYPE testsuite [<!ENTITY x \"BAD\">]><testsuite/>'.encode('utf-16'))\nsys.stdout.buffer.write(b.getvalue())";
    const encoded = Bun.spawnSync(["python3", "-c", program]);
    expect(encoded.exitCode).toBe(0);
    const result = command({ input: onlyAvailable(fixture()), archives: { "22601": Buffer.from(encoded.stdout) } });
    expect(result.report.gaps).toEqual([{ kind: "unsafe", scope: "artifact 22601 test-results-linux", detail: "XML DTD or entity declaration is forbidden", omitted: 0 }]);
  });
  it("rejects corrupt member checksums", () => {
    const bytes = zip({ "results.xml": xml }); bytes[42] ^= 1;
    const result = command({ input: onlyAvailable(fixture()), archives: { "22601": bytes } });
    expect(result.report.gaps).toEqual([{ kind: "unsafe", scope: "artifact 22601 test-results-linux", detail: expect.stringContaining("CRC"), omitted: 0 }]);
  });
  for (const [name, value, localOffset, centralOffset] of [["encryption", 1, 6, 8], ["unsupported compression", 99, 8, 10]] as const) {
    it(`rejects ${name} before decompressing the member`, () => {
      const bytes = zip({ "results.xml": xml });
      bytes.writeUInt16LE(value, localOffset);
      bytes.writeUInt16LE(value, bytes.indexOf(Buffer.from("PK\x01\x02")) + centralOffset);
      const result = command({ input: onlyAvailable(fixture()), archives: { "22601": bytes } });
      expect(result.report.gaps).toEqual([{ kind: "unsafe", scope: "artifact 22601 test-results-linux", detail: "encrypted or unsupported ZIP member", omitted: 0 }]);
    });
  }
  it("rejects inconsistent local and central sizes", () => {
    const bytes = zip({ "results.xml": xml }); bytes.writeUInt32LE(1, 18);
    const result = command({ input: onlyAvailable(fixture()), archives: { "22601": bytes } });
    expect(result.report.gaps).toEqual([{ kind: "unsafe", scope: "artifact 22601 test-results-linux", detail: "inconsistent ZIP sizes or checksum", omitted: 0 }]);
  });
  it("rejects ZIP64 before standard-library entry allocation", () => {
    const bytes = zip({ "results.xml": xml }); bytes.writeUInt16LE(65535, bytes.lastIndexOf(Buffer.from("PK\x05\x06")) + 10);
    const result = command({ input: onlyAvailable(fixture()), archives: { "22601": bytes } });
    expect(result.report.gaps).toEqual([{ kind: "unsafe", scope: "artifact 22601 test-results-linux", detail: "unsupported multidisk or ZIP64 archive", omitted: 0 }]);
  });
  it("preserves XML namespaces, CDATA, escaped text and Unicode literally", () => {
    const content = '<testsuite xmlns="urn:junit"><testcase name="literal &amp; case"><failure message="&#x26; expected"><![CDATA[<trace>& untouched 😀]]></failure><error>escaped &lt;payload&gt;</error></testcase></testsuite>';
    const result = command({ input: onlyAvailable(fixture()), archives: { "22601": zip({ "results.xml": content }) } });
    expect(result.code).toBe(0);
    expect(verified(result.report).map((row) => [row.testName, row.kind, row.message, row.body])).toEqual([["literal & case", "failure", "& expected", "<trace>& untouched 😀"], ["literal & case", "error", "", "escaped <payload>"]]);
  });
});
