import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import type { Repository } from "./types.ts";

declare const runIdBrand: unique symbol;
declare const checkedHeadBrand: unique symbol;
export type RunId = string & { readonly [runIdBrand]: "RunId" };
export type CheckedHead = string & { readonly [checkedHeadBrand]: "CheckedHead" };
export interface EvidenceRequest {
  readonly repository: Repository;
  readonly runId: RunId;
  readonly checkedHead: CheckedHead;
  readonly attempt: number;
}
export interface EvidenceGap {
  readonly kind: "missing" | "expired" | "inaccessible" | "malformed" | "unsafe" | "limit" | "timeout" | "unavailable" | "identity-mismatch" | "attempt-unbound";
  readonly scope: string;
  readonly detail: string;
  readonly omitted: number;
}
export interface JUnitRecord {
  readonly artifactId: string;
  readonly artifactName: string;
  readonly member: string;
  readonly testName: string;
  readonly classname: string;
  readonly kind: "failure" | "error";
  readonly message: string;
  readonly type: string;
  readonly body: string;
  readonly attemptBinding: "verified-first-attempt" | "run-only";
}
export interface EvidenceLog {
  readonly member: string;
  readonly text: string;
}
export type FailedCheckEvidence =
  | { readonly kind: "unverified"; readonly requested: EvidenceRequest; readonly gaps: readonly EvidenceGap[] }
  | { readonly kind: "verified"; readonly requested: EvidenceRequest; readonly records: readonly JUnitRecord[]; readonly logs: readonly EvidenceLog[]; readonly gaps: readonly EvidenceGap[] };
export interface FailedCheckReader {
  recover(request: EvidenceRequest): Promise<FailedCheckEvidence>;
}

const LIMITS = {
  json: 1024 * 1024,
  archive: 8 * 1024 * 1024,
  downloads: 8,
  downloadBytes: 32 * 1024 * 1024,
  expandedBytes: 32 * 1024 * 1024,
  pages: 2,
  records: 32,
  evidenceCharacters: 24 * 1024,
  gaps: 64,
  output: 64 * 1024,
  commandMillis: 15000,
  parserMillis: 3000,
  collectionMillis: 90000,
} as const;

class EvidenceReadError extends Error {
  constructor(readonly kind: EvidenceGap["kind"], message: string, readonly bytesRead = 0) {
    super(message);
  }
}
export function parseRunId(value: unknown): RunId {
  if (typeof value !== "string" || !/^[1-9][0-9]*$/.test(value) || !Number.isSafeInteger(Number(value)))
    throw new Error("run id must be a positive safe integer");
  return value as RunId;
}
export function parseCheckedHead(value: unknown): CheckedHead {
  if (typeof value !== "string" || !/^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$/.test(value))
    throw new Error("must be a full hexadecimal commit SHA");
  return value.toLowerCase() as CheckedHead;
}
function object(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    throw new EvidenceReadError("malformed", "expected an object");
  return { ...value };
}
function array(value: unknown): readonly unknown[] {
  if (!Array.isArray(value)) throw new EvidenceReadError("malformed", "expected an array");
  return value;
}
function text(value: unknown, limit = 256): string {
  if (typeof value !== "string" || Array.from(value).length > limit)
    throw new EvidenceReadError("malformed", "invalid or over-limit text field");
  return value;
}
function integer(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    throw new EvidenceReadError("malformed", "invalid or imprecise numeric field");
  return value;
}
function id(value: unknown): string {
  const parsed = integer(value);
  if (parsed === 0) throw new EvidenceReadError("malformed", "invalid zero identifier");
  return String(parsed);
}
function json(bytes: Buffer): unknown {
  try {
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    throw new EvidenceReadError("malformed", "invalid UTF-8 JSON response");
  }
}

function boundedCommand(argv: readonly [string, ...string[]], limit: number, millis: number, input?: Buffer): Promise<Buffer> {
  if (millis <= 0) return Promise.reject(new EvidenceReadError("timeout", "collection deadline reached"));
  return new Promise((resolve, reject) => {
    const child = spawn(argv[0], argv.slice(1), { stdio: ["pipe", "pipe", "pipe"] });
    const chunks: Buffer[] = [];
    let bytes = 0;
    let stderrBytes = 0;
    let failure: EvidenceReadError | null = null;
    const stop = (kind: EvidenceGap["kind"], detail: string): void => {
      failure ??= new EvidenceReadError(kind, detail, bytes);
      child.kill("SIGKILL");
    };
    const timer = setTimeout(() => stop("timeout", `${argv[0]} deadline reached`), millis);
    child.stdin.on("error", () => {});
    child.stdin.end(input);
    child.stdout.on("data", (chunk: Buffer) => {
      bytes += chunk.length;
      if (bytes > limit) stop("limit", `${argv[0]} stdout byte limit exceeded`);
      else if (failure === null) chunks.push(chunk);
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderrBytes += chunk.length;
      if (stderrBytes > 8192) stop("limit", `${argv[0]} stderr byte limit exceeded`);
    });
    child.on("error", () => { failure ??= new EvidenceReadError("unavailable", `${argv[0]} unavailable`, bytes); });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (failure !== null) reject(new EvidenceReadError(failure.kind, failure.message, bytes));
      else if (code !== 0) reject(new EvidenceReadError("inaccessible", `${argv[0]} exited ${code ?? -1}`, bytes));
      else resolve(Buffer.concat(chunks));
    });
  });
}

interface ArchiveRecord extends Omit<JUnitRecord, "artifactId" | "artifactName" | "attemptBinding"> {}
interface ArchiveResult {
  readonly records: readonly ArchiveRecord[];
  readonly logs: readonly EvidenceLog[];
  readonly gaps: readonly EvidenceGap[];
  readonly expandedBytes: number;
}
function archiveResult(value: unknown, scope: string, allowance: number): ArchiveResult {
  const raw = object(value);
  if ("error" in raw) {
    const kind = raw.errorKind;
    if (kind !== "unsafe" && kind !== "unavailable") throw new EvidenceReadError("malformed", "invalid archive error kind");
    throw new EvidenceReadError(kind, text(raw.error));
  }
  const expandedBytes = integer(raw.expandedBytes);
  if (expandedBytes > Math.min(8 * 1024 * 1024, allowance)) throw new EvidenceReadError("malformed", "invalid archive byte accounting");
  const rows = array(raw.records);
  const logs = array(raw.logs);
  const gaps = array(raw.gaps);
  if (rows.length > LIMITS.records || logs.length > 4 || gaps.length > 4)
    throw new EvidenceReadError("malformed", "over-limit archive response");
  return {
    expandedBytes,
    records: rows.map((value) => {
      const row = object(value);
      const kind = row.kind;
      if (kind !== "failure" && kind !== "error") throw new EvidenceReadError("malformed", "invalid JUnit record kind");
      return { member: text(row.member), testName: text(row.testName), classname: text(row.classname), kind, message: text(row.message), type: text(row.type), body: text(row.body, 2048) };
    }),
    logs: logs.map((value) => { const row = object(value); return { member: text(row.member), text: text(row.text, 8192) }; }),
    gaps: gaps.map((value) => {
      const row = object(value);
      if (row.kind !== "limit") throw new EvidenceReadError("malformed", "invalid archive gap kind");
      return { kind: "limit", scope, detail: text(row.detail), omitted: integer(row.omitted) };
    }),
  };
}

export class GhFailedCheckReader implements FailedCheckReader {
  async recover(request: EvidenceRequest): Promise<FailedCheckEvidence> {
    const gaps: EvidenceGap[] = [];
    const records: JUnitRecord[] = [];
    const logs: EvidenceLog[] = [];
    let omittedGaps = 0;
    let downloadBytes = LIMITS.downloadBytes;
    let expandedBytes = LIMITS.expandedBytes;
    let downloads = 0;
    let evidenceCharacters = 0;
    let omittedRecords = 0;
    const deadline = performance.now() + LIMITS.collectionMillis;
    const repository = request.repository;
    const prefix = `repos/${repository.owner}/${repository.repo}/actions`;
    const runPath = `${prefix}/runs/${request.runId}`;
    const addGap = (kind: EvidenceGap["kind"], scope: string, detail: string, omitted = 0): void => {
      if (gaps.length < LIMITS.gaps - 4 || scope === "run" || scope === "inventory" || scope === "output") gaps.push({ kind, scope: scope.slice(0, 256), detail: detail.slice(0, 512), omitted });
      else omittedGaps++;
    };
    const failureGap = (error: unknown, scope: string): void => {
      if (error instanceof EvidenceReadError) addGap(error.kind, scope, error.message);
      else addGap("malformed", scope, "invalid diagnostic response");
    };
    const command = (path: string, limit: number): Promise<Buffer> => boundedCommand(
      ["gh", "api", "--hostname", repository.host, "--method", "GET", path],
      limit, Math.min(LIMITS.commandMillis, deadline - performance.now())
    );
    const verify = async (): Promise<void> => {
      const run = object(json(await command(runPath, LIMITS.json)));
      if (id(run.id) !== request.runId || text(run.head_sha, 64).toLowerCase() !== request.checkedHead || integer(run.run_attempt) !== request.attempt)
        throw new EvidenceReadError("identity-mismatch", "Actions run id, checked head or attempt did not match");
    };
    const finishGaps = (): readonly EvidenceGap[] => omittedGaps === 0 ? gaps : [...gaps, { kind: "limit", scope: "output", detail: "additional evidence gaps omitted", omitted: omittedGaps }];
    try { await verify(); }
    catch (error) { failureGap(error, "run"); return { kind: "unverified", requested: request, gaps: finishGaps() }; }
    const archive = async (path: string, mode: "logs" | "junit", scope: string): Promise<ArchiveResult | null> => {
      if (downloadBytes <= 0 || expandedBytes <= 0) { addGap("limit", scope, "global archive byte budget exhausted", 1); return null; }
      const allowance = expandedBytes;
      try {
        let bytes: Buffer;
        try {
          bytes = await command(path, Math.min(LIMITS.archive, downloadBytes));
          downloadBytes -= bytes.length;
        } catch (error) {
          if (error instanceof EvidenceReadError) downloadBytes -= Math.min(error.bytesRead, downloadBytes);
          throw error;
        }
        try {
          const output = await boundedCommand(
            ["python3", "-I", fileURLToPath(new URL("./junit-archive.py", import.meta.url)), mode, String(allowance)],
            LIMITS.output, Math.min(LIMITS.parserMillis, deadline - performance.now()), bytes
          );
          const result = archiveResult(json(output), scope, allowance);
          expandedBytes -= result.expandedBytes;
          return result;
        } catch (error) {
          expandedBytes -= Math.min(8 * 1024 * 1024, expandedBytes);
          throw error;
        }
      } catch (error) { failureGap(error, scope); return null; }
    };
    const logArchive = await archive(`${runPath}/attempts/${request.attempt}/logs`, "logs", "logs");
    if (logArchive !== null) { logs.push(...logArchive.logs); for (const gap of logArchive.gaps) addGap(gap.kind, gap.scope, gap.detail, gap.omitted); }
    const seen = new Set<string>();
    let listed = 0;
    try {
      for (let page = 1; page <= LIMITS.pages; page++) {
        const inventory = object(json(await command(`${runPath}/artifacts?per_page=50&page=${page}`, LIMITS.json)));
        const total = integer(inventory.total_count);
        const artifacts = array(inventory.artifacts);
        if (artifacts.length > 50) throw new EvidenceReadError("malformed", "over-limit artifact page");
        listed += artifacts.length;
        for (const value of artifacts) {
          let scope = "artifact";
          try {
            const artifact = object(value);
            const artifactId = id(artifact.id);
            const name = text(artifact.name);
            scope = `artifact ${artifactId} ${name}`;
            if (seen.has(artifactId)) { addGap("malformed", scope, "duplicate artifact id in inventory"); continue; }
            seen.add(artifactId);
            if (typeof artifact.expired !== "boolean") throw new EvidenceReadError("malformed", "missing artifact expiry state");
            if (artifact.expired) { addGap("expired", scope, "artifact expired"); continue; }
            const origin = object(artifact.workflow_run);
            if (id(origin.id) !== request.runId || text(origin.head_sha, 64).toLowerCase() !== request.checkedHead) {
              addGap("identity-mismatch", scope, "artifact run or head did not match"); continue;
            }
            const size = integer(artifact.size_in_bytes);
            if (size > LIMITS.archive || downloads >= LIMITS.downloads) { addGap("limit", scope, "artifact download size or count limit reached", 1); continue; }
            downloads++;
            const result = await archive(`${prefix}/artifacts/${artifactId}/zip`, "junit", scope);
            if (result === null) continue;
            for (const gap of result.gaps) addGap(gap.kind, gap.scope, gap.detail, gap.omitted);
            if (result.records.length === 0) addGap("missing", scope, "no JUnit failure or error records found");
            if (request.attempt > 1) addGap("attempt-unbound", scope, "artifact metadata does not establish its rerun attempt");
            for (const row of result.records) {
              const cost = JSON.stringify(row).length + name.length;
              if (records.length >= LIMITS.records || evidenceCharacters + cost > LIMITS.evidenceCharacters) { omittedRecords++; continue; }
              evidenceCharacters += cost;
              records.push({ ...row, artifactId, artifactName: name, attemptBinding: request.attempt === 1 ? "verified-first-attempt" : "run-only" });
            }
          } catch (error) { failureGap(error, scope); }
        }
        if (listed >= total) break;
        if (artifacts.length === 0 || page === LIMITS.pages) { addGap("limit", "inventory", "artifact inventory incomplete", Math.max(0, total - listed)); break; }
      }
      if (listed === 0) addGap("missing", "inventory", "no artifacts available for this Actions run");
    } catch (error) { failureGap(error, "inventory"); }
    if (omittedRecords) addGap("limit", "output", "JUnit records omitted by global evidence budget", omittedRecords);
    try { await verify(); }
    catch (error) { failureGap(error, "run"); return { kind: "unverified", requested: request, gaps: finishGaps() }; }
    return { kind: "verified", requested: request, records, logs, gaps: finishGaps() };
  }
}

export function renderEvidence(report: FailedCheckEvidence, pretty = false): { readonly output: string; readonly exitCode: number } {
  let output = report;
  let omitted = 0;
  const render = (): string => `${JSON.stringify(output, null, pretty ? 2 : undefined)}\n`;
  while (Buffer.byteLength(render()) > LIMITS.output) {
    omitted++;
    const gap: EvidenceGap = { kind: "limit", scope: "output", detail: "serialized evidence omitted", omitted };
    const gaps = [...output.gaps.filter((row) => row.detail !== gap.detail), gap];
    if (output.kind === "verified" && output.logs.length) output = { ...output, logs: output.logs.slice(1), gaps };
    else if (output.kind === "verified" && output.records.length) output = { ...output, records: output.records.slice(0, -1), gaps };
    else if (gaps.length > 1) output = { ...output, gaps: [...gaps.slice(0, -2), gap] };
    else throw new Error("diagnostic identity exceeds output budget");
  }
  return { output: render(), exitCode: output.kind === "verified" && output.gaps.length === 0 ? 0 : 2 };
}
