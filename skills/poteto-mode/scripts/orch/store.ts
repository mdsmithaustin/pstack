import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import {
  access,
  mkdir,
  open,
  readFile,
  readdir,
  rename,
  rm,
  unlink,
  writeFile,
} from "node:fs/promises";
import { basename, dirname, join, resolve } from "node:path";
import { parseRemote } from "../watch-pr/remote.ts";
import {
  currentAttempts,
  parseAckDecisions,
  parseAttempt,
  parseBeginAttempt,
  parseCompletionBinding,
  parseObservation,
  parseSavedDecision,
  parseWriteIntent,
  safeId,
  sameSlot,
  type AckDecision,
  type Attempt,
  type Batch,
  type BeginAttempt,
  type CompletionBinding,
  type Event,
  type Observation,
  type Receipt,
  type SavedDecision,
  type WriteIntent,
} from "./recovery.ts";
import { UserError, parseVerdict, verdictOrNull, type Verdict } from "./validation.ts";

export { UserError, parseVerdict } from "./validation.ts";
export type { Verdict } from "./validation.ts";

const UNIT_HEADER = "id\ttrack\tstate\tbranch\tpr\tsha\tbrief";
const LEDGER_HEADER = "pr\tsha\tverdict\tevidence\tverifier\tts";
const LOCK_FILE = ".orch.lock";

export interface Unit {
  readonly id: string;
  readonly track: string;
  readonly state: string;
  readonly branch: string;
  readonly pr: string;
  readonly sha: string;
  readonly brief: string;
}

export interface LedgerEntry {
  readonly pr: string;
  readonly sha: string;
  readonly verdict: Verdict;
  readonly evidence: string;
  readonly verifier: string;
  readonly ts: string;
}

export interface InboxPointer {
  readonly ts: string;
  readonly agent: string;
  readonly unit: string;
  readonly status: string;
  readonly report: string;
  readonly attempt?: string;
  readonly completion?: CompletionBinding;
}

export interface InboxPushResult {
  readonly pointer: InboxPointer;
  readonly filename: string;
}

export interface OpenGate {
  readonly kind: "open";
  readonly id: string;
  readonly question: string;
  readonly options: string;
  readonly defaultAnswer: string;
}

export interface ResolvedGate {
  readonly kind: "resolved";
  readonly id: string;
  readonly question: string;
  readonly options: string;
  readonly defaultAnswer: string;
  readonly answer: string;
}

export type Gate = OpenGate | ResolvedGate;

export type FrontierPrState = "OPEN" | "MERGED" | "CLOSED";

export interface FrontierPr {
  readonly pr: number;
  readonly branches: string;
  readonly sha: string;
  readonly state: FrontierPrState;
}

export interface Frontier {
  readonly generation: number;
  readonly prs: readonly FrontierPr[];
  readonly lowestUnmerged: number | null;
}

export interface StandingLine {
  readonly number: number;
  readonly line: string;
}

export type Counts = Readonly<Record<string, number>>;

export interface StatusSummary {
  readonly unitStates: Counts;
  readonly ledgerVerdicts: Counts;
  readonly frontierGeneration: number;
  readonly openGateIds: readonly string[];
}

export interface StatusReport {
  readonly units: readonly Unit[];
  readonly ledger: readonly LedgerEntry[];
  readonly frontier: Frontier;
  readonly gates: readonly Gate[];
  readonly summary: StatusSummary;
  readonly changed: string;
}

export interface AddUnitParams {
  readonly id: string;
  readonly track: string;
  readonly brief?: string;
}

export interface SetUnitParams {
  readonly attempt?: string;
  readonly id: string;
  readonly state: string;
  readonly branch?: string;
  readonly pr?: number;
  readonly sha?: string;
}

export interface ListUnitsParams {
  readonly state?: string;
  readonly track?: string;
}

export interface RecordLedgerParams {
  readonly attempt?: string;
  readonly pr: number;
  readonly sha: string;
  readonly verdict: Verdict;
  readonly evidence: string;
  readonly verifier?: string;
}

export interface CheckLedgerParams {
  readonly pr: number;
  readonly sha: string;
}

export interface PushInboxParams {
  readonly attempt?: string;
  readonly binding?: string;
  readonly pr?: number;
  readonly sha?: string;
  readonly agent: string;
  readonly unit: string;
  readonly status: string;
  readonly report?: string;
}

export interface ParkGateParams {
  readonly id: string;
  readonly question: string;
  readonly options: string;
  readonly defaultAnswer: string;
}

export interface ResolveGateParams {
  readonly id: string;
  readonly answer: string;
}

export type FrontierDiscovery = "github" | "graphite";

export interface SetFrontierParams {
  readonly repo: string;
  readonly discovery?: FrontierDiscovery;
  readonly prs?: readonly number[];
}

export interface AddStandingParams {
  readonly line: string;
}

export interface OpenStoreOptions {
  readonly force?: boolean;
  readonly onLockStolen?: (holder: string) => void;
  readonly onStaleLock?: (holder: string) => void;
}

export interface Store {
  readonly units: {
    readonly add: (params: AddUnitParams) => Promise<Unit>;
    readonly set: (params: SetUnitParams) => Promise<Unit>;
    readonly get: (id: string) => Promise<Unit>;
    readonly list: (params?: ListUnitsParams) => Promise<readonly Unit[]>;
    readonly counts: () => Promise<Counts>;
  };
  readonly ledger: {
    readonly record: (params: RecordLedgerParams) => Promise<LedgerEntry>;
    readonly check: (params: CheckLedgerParams) => Promise<LedgerEntry>;
    readonly summary: () => Promise<Counts>;
  };
  readonly inbox: {
    readonly push: (params: PushInboxParams) => Promise<InboxPushResult>;
    readonly drain: () => Promise<readonly InboxPointer[]>;
    readonly claim: () => Promise<Batch | null>;
    readonly receipts: () => Promise<readonly Receipt[]>;
    readonly ack: (
      batch: string,
      decisions: readonly AckDecision[],
    ) => Promise<Batch>;
    readonly peek: () => Promise<readonly InboxPointer[]>;
    readonly count: () => Promise<number>;
  };
  readonly attempts: {
    readonly begin: (params: BeginAttempt) => Promise<Attempt>;
    readonly observe: (
      id: string,
      observation: Observation,
    ) => Promise<Attempt>;
    readonly list: () => Promise<readonly Attempt[]>;
    readonly finish: (id: string, reason: string) => Promise<Attempt>;
  };
  readonly gates: {
    readonly park: (params: ParkGateParams) => Promise<OpenGate>;
    readonly list: () => Promise<readonly OpenGate[]>;
    readonly resolve: (params: ResolveGateParams) => Promise<ResolvedGate>;
  };
  readonly frontier: {
    readonly set: (params: SetFrontierParams) => Promise<Frontier>;
    readonly show: () => Promise<Frontier>;
  };
  readonly standing: {
    readonly show: () => Promise<readonly StandingLine[]>;
    readonly add: (params: AddStandingParams) => Promise<StandingLine>;
  };
  readonly status: {
    readonly render: () => Promise<StatusReport>;
  };
  readonly init: () => Promise<{ readonly store: string }>;
  readonly close: () => Promise<void>;
}

export interface NotFoundOutput {
  readonly compact: string;
  readonly json: unknown;
}

export class UsageError extends UserError {}
export class NotFoundError extends UserError {
  public constructor(
    message: string,
    public readonly output?: NotFoundOutput
  ) {
    super(message);
  }
}

function errorCode(error: unknown): string | null {
  if (
    error !== null &&
    typeof error === "object" &&
    "code" in error &&
    typeof error.code === "string"
  ) {
    return error.code;
  }
  return null;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isUnknownArray(value: unknown): value is readonly unknown[] {
  return Array.isArray(value);
}

function frontierPrStateOrNull(value: unknown): FrontierPrState | null {
  switch (value) {
    case "OPEN":
    case "MERGED":
    case "CLOSED":
      return value;
    default:
      return null;
  }
}

function cleanCell(value: string): string {
  const cleaned = value.replace(/[\t\n\r]/g, " ");
  return /^[=+\-@]/.test(cleaned) ? `'${cleaned}` : cleaned;
}

function requiredCell(value: string, label: string): string {
  const cleaned = cleanCell(value);
  if (cleaned.trim().length === 0) {
    throw new UserError(`${label} must not be empty`);
  }
  return cleaned;
}

function requiredLine(value: string, label: string): string {
  const cleaned = value.replace(/[\n\r]/g, " ").trim();
  if (cleaned.length === 0) {
    throw new UserError(`${label} must not be empty`);
  }
  return cleaned;
}

function positiveInteger(value: number, label: string): number {
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new UserError(`${label} must be a positive integer`);
  }
  return value;
}

async function exists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch (error) {
    if (errorCode(error) === "ENOENT") {
      return false;
    }
    throw error;
  }
}

async function atomicWrite(path: string, contents: string): Promise<void> {
  const temporary = join(
    dirname(path),
    `.${basename(path)}.${process.pid}.${randomUUID()}.tmp`
  );
  try {
    await writeFile(temporary, contents, { flag: "wx" });
    await rename(temporary, path);
  } finally {
    await rm(temporary, { force: true });
  }
}

async function writeIfMissing(path: string, contents: string): Promise<void> {
  if (!(await exists(path))) {
    await atomicWrite(path, contents);
  }
}

async function requiredFile(path: string): Promise<string> {
  try {
    return await readFile(path, "utf8");
  } catch (error) {
    if (errorCode(error) === "ENOENT") {
      throw new UserError(
        `store is not initialized at ${dirname(path)}; run orch init`
      );
    }
    throw error;
  }
}

function holderIsDead(holder: string): boolean {
  const pid = Number.parseInt(holder, 10);
  if (!Number.isSafeInteger(pid) || pid <= 0 || String(pid) !== holder) {
    return false;
  }
  try {
    process.kill(pid, 0);
    return false;
  } catch (error) {
    return errorCode(error) === "ESRCH";
  }
}

async function acquireLock(
  store: string,
  options: OpenStoreOptions
): Promise<() => Promise<void>> {
  const path = join(store, LOCK_FILE);
  const pid = String(process.pid);
  const create = async (): Promise<void> => {
    const handle = await open(path, "wx");
    await handle.writeFile(`${pid}\n`);
    await handle.close();
  };

  const takeOver = async (): Promise<void> => {
    await unlink(path);
    try {
      await create();
    } catch (retryError) {
      if (errorCode(retryError) === "EEXIST") {
        const retryHolder =
          (await readFile(path, "utf8")).trim() || "unknown";
        throw new UserError(`store lock held by pid ${retryHolder}`);
      }
      throw retryError;
    }
  };

  try {
    await create();
  } catch (error) {
    if (errorCode(error) !== "EEXIST") {
      throw error;
    }
    let holder = "unknown";
    try {
      holder = (await readFile(path, "utf8")).trim() || "unknown";
    } catch {
      holder = "unknown";
    }
    if (holderIsDead(holder)) {
      options.onStaleLock?.(holder);
      await takeOver();
    } else if (options.force) {
      options.onLockStolen?.(holder);
      await takeOver();
    } else {
      throw new UserError(`store lock held by pid ${holder}`);
    }
  }

  return async (): Promise<void> => {
    try {
      if ((await readFile(path, "utf8")).trim() === pid) {
        await unlink(path);
      }
    } catch (error) {
      if (errorCode(error) !== "ENOENT") {
        throw error;
      }
    }
  };
}

async function readTsv(
  path: string,
  header: string,
  width: number
): Promise<readonly (readonly string[])[]> {
  const lines = (await requiredFile(path)).replace(/\r/g, "").split("\n");
  if (lines.shift() !== header) {
    throw new UserError(`${basename(path)} has an invalid header`);
  }
  return lines
    .filter((value) => value.length > 0)
    .map((value) => {
      const cells = value.split("\t");
      if (cells.length !== width) {
        throw new UserError(`${basename(path)} has a malformed row`);
      }
      return cells;
    });
}

async function writeTsv(
  path: string,
  header: string,
  rows: readonly (readonly string[])[]
): Promise<void> {
  const body = rows.map((row) => row.map(cleanCell).join("\t")).join("\n");
  await atomicWrite(path, `${header}\n${body}${body.length > 0 ? "\n" : ""}`);
}

async function readUnits(store: string): Promise<readonly Unit[]> {
  return (await readTsv(join(store, "units.tsv"), UNIT_HEADER, 7)).map(
    (row) => ({
      id: row[0] ?? "",
      track: row[1] ?? "",
      state: row[2] ?? "",
      branch: row[3] ?? "",
      pr: row[4] ?? "",
      sha: row[5] ?? "",
      brief: row[6] ?? "",
    })
  );
}

function unitCells(unit: Unit): readonly string[] {
  return [
    unit.id,
    unit.track,
    unit.state,
    unit.branch,
    unit.pr,
    unit.sha,
    unit.brief,
  ];
}

async function saveUnits(store: string, rows: readonly Unit[]): Promise<void> {
  await writeTsv(
    join(store, "units.tsv"),
    UNIT_HEADER,
    rows.map(unitCells)
  );
}

async function readLedger(store: string): Promise<readonly LedgerEntry[]> {
  return (await readTsv(join(store, "ledger.tsv"), LEDGER_HEADER, 6)).map(
    (row) => {
      const rawVerdict = row[2] ?? "";
      const verdict = verdictOrNull(rawVerdict);
      if (verdict === null) {
        throw new UserError(`ledger.tsv has invalid verdict ${rawVerdict}`);
      }
      return {
        pr: row[0] ?? "",
        sha: row[1] ?? "",
        verdict,
        evidence: row[3] ?? "",
        verifier: row[4] ?? "",
        ts: row[5] ?? "",
      };
    }
  );
}

function ledgerCells(row: LedgerEntry): readonly string[] {
  return [
    row.pr,
    row.sha,
    row.verdict,
    row.evidence,
    row.verifier,
    row.ts,
  ];
}

async function saveLedger(
  store: string,
  rows: readonly LedgerEntry[]
): Promise<void> {
  await writeTsv(
    join(store, "ledger.tsv"),
    LEDGER_HEADER,
    rows.map(ledgerCells)
  );
}

function pointerCells(pointer: InboxPointer): readonly string[] {
  return [
    pointer.ts,
    pointer.agent,
    pointer.unit,
    pointer.status,
    pointer.report,
    ...(pointer.attempt === undefined ? [] : [pointer.attempt]),
    ...(pointer.completion === undefined
      ? []
      : [
          pointer.completion.binding,
          pointer.completion.pr,
          pointer.completion.sha,
        ]),
  ];
}

async function readEvents(directory: string): Promise<readonly Event[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  const result: Event[] = [];
  const files = entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".tsv"))
    .sort((left, right) => left.name.localeCompare(right.name));
  for (const entry of files) {
    const raw = (await readFile(join(directory, entry.name), "utf8")).replace(
      /\r?\n$/,
      "",
    );
    const row = raw.split("\t");
    if (/[\r\n]/.test(raw) || ![5, 6, 9].includes(row.length)) {
      throw new UserError(`inbox pointer ${entry.name} is malformed`);
    }
    result.push({
      id: entry.name,
      pointer: {
        ts: row[0] ?? "",
        agent: row[1] ?? "",
        unit: row[2] ?? "",
        status: row[3] ?? "",
        report: row[4] ?? "",
        ...(row.length >= 6 ? { attempt: safeId(row[5]) } : {}),
        ...(row.length === 9
          ? { completion: parseCompletionBinding({
              binding: row[6], pr: row[7], sha: row[8],
            }) }
          : {}),
      },
    });
  }
  return result;
}

async function batchIds(directory: string): Promise<readonly string[]> {
  if (!(await exists(directory))) return [];
  return (await readdir(directory, { withFileTypes: true }))
    .filter((entry) => entry.isDirectory())
    .map((entry) => safeId(entry.name))
    .sort();
}

async function batchDirectory(store: string, id: string): Promise<string> {
  const pending = join(store, "inbox-pending", safeId(id));
  if (await exists(pending)) return pending;
  const retained = join(store, "inbox-batches", safeId(id));
  if (await exists(retained)) return retained;
  throw new NotFoundError(`batch ${id} not found`);
}

async function savedDecisions(
  store: string,
  batch: string,
): Promise<readonly SavedDecision[]> {
  const directory = join(await batchDirectory(store, batch), "decisions");
  if (!(await exists(directory))) return [];
  const files = (await readdir(directory))
    .filter((name) => name.endsWith(".json"))
    .sort();
  return Promise.all(
    files.map(async (name) =>
      parseSavedDecision(
        JSON.parse(await readFile(join(directory, name), "utf8")),
      ),
    ),
  );
}

async function readBatch(
  store: string,
  id: string,
  pending = false,
): Promise<Batch> {
  const directory = await batchDirectory(store, id);
  const completed = new Set(
    (await savedDecisions(store, id))
      .filter((decision) => decision.completed)
      .map((decision) => decision.event),
  );
  const events = await readEvents(directory);
  return {
    id,
    events: pending
      ? events.filter((event) => !completed.has(event.id))
      : events,
  };
}

async function readAttempts(store: string): Promise<readonly Attempt[]> {
  const path = join(store, "attempts.json");
  if (!(await exists(path))) return [];
  const rows: unknown = JSON.parse(await readFile(path, "utf8"));
  if (!Array.isArray(rows))
    throw new UserError("attempts.json must contain an array");
  return rows.map(parseAttempt);
}

async function saveAttempt(store: string, attempt: Attempt): Promise<void> {
  const rows = [...(await readAttempts(store))];
  const index = rows.findIndex((row) => row.id === attempt.id);
  if (index < 0) rows.push(attempt);
  else rows[index] = attempt;
  await atomicWrite(
    join(store, "attempts.json"),
    `${JSON.stringify(rows, null, 2)}\n`,
  );
}

async function repairStore(
  store: string,
  pending: PendingBatchCollection,
): Promise<void> {
  if (!(await exists(join(store, "units.tsv")))) return;
  const journal = join(store, "write-intents");
  if (await exists(journal)) {
    const names = (await readdir(journal))
      .filter((name) => name.endsWith(".json"))
      .sort();
    for (const name of names) {
      const path = join(journal, name);
      const intent = parseWriteIntent(JSON.parse(await readFile(path, "utf8")));
      if (!intent.completed) await applyWriteIntent(store, path, intent);
      await unlink(path);
    }
  }
  await pending.repair();
}

class PendingBatchCollection {
  constructor(private readonly store: string) {}

  async ids(): Promise<readonly string[]> {
    return batchIds(join(this.store, "inbox-pending"));
  }

  async repair(): Promise<void> {
    const store = this.store;
    await mkdir(join(store, "inbox-pending"), { recursive: true });
    await mkdir(join(store, "inbox-batches"), { recursive: true });
    for (const entry of await readdir(store, { withFileTypes: true })) {
      if (entry.isDirectory() && entry.name.startsWith(".inbox-drain-"))
        await rename(
          join(store, entry.name),
          join(store, "inbox-pending", entry.name.slice(1)),
        );
    }
    const migrated = join(store, ".inbox-pending-migrated");
    if (!(await exists(migrated))) {
      for (const id of await batchIds(join(store, "inbox-batches"))) {
        if ((await readBatch(store, id, true)).events.length > 0)
          await rename(
            join(store, "inbox-batches", id),
            join(store, "inbox-pending", id),
          );
      }
      await atomicWrite(migrated, "1\n");
    }
    await mkdir(join(store, "inbox"), { recursive: true });
    for (const id of await this.ids()) {
      for (const decision of await savedDecisions(store, id)) {
        if (!decision.completed)
          await applyWriteIntent(
            store,
            decisionPath(store, id, decision.event),
            decision,
          );
      }
      await this.retain(id);
    }
  }

  async retain(id: string): Promise<void> {
    if ((await readBatch(this.store, id, true)).events.length === 0)
      await rename(
        join(this.store, "inbox-pending", id),
        join(this.store, "inbox-batches", id),
      );
  }

  async claim(): Promise<Batch | null> {
    for (const id of await this.ids()) {
      const batch = await readBatch(this.store, id, true);
      if (batch.events.length > 0) return batch;
    }
    if ((await readEvents(join(this.store, "inbox"))).length === 0) return null;
    const id = `batch-${randomUUID()}`;
    await rename(join(this.store, "inbox"), join(this.store, "inbox-pending", id));
    await mkdir(join(this.store, "inbox"), { recursive: true });
    return readBatch(this.store, id, true);
  }

  async events(): Promise<readonly Event[]> {
    const batches = await Promise.all(
      (await this.ids()).map((id) => readBatch(this.store, id, true)),
    );
    return [
      ...batches.flatMap((batch) => batch.events),
      ...(await readEvents(join(this.store, "inbox"))),
    ];
  }
}

function decisionPath(store: string, batch: string, event: string): string {
  return join(store, "inbox-pending", batch, "decisions", `${event}.json`);
}

async function writeIntent(
  store: string,
  effects: Omit<WriteIntent, "completed">,
): Promise<void> {
  const directory = join(store, "write-intents");
  await mkdir(directory, { recursive: true });
  const path = join(directory, `${randomUUID()}.json`);
  const intent = { ...effects, completed: false };
  await atomicWrite(path, `${JSON.stringify(intent, null, 2)}\n`);
  await applyWriteIntent(store, path, intent);
  await unlink(path);
}

async function applyWriteIntent(
  store: string,
  path: string,
  intent: WriteIntent,
): Promise<void> {
  const { unit, ledger, attempt } = intent;
  if (unit !== undefined) {
    const rows = [...(await readUnits(store))];
    const index = rows.findIndex((row) => row.id === unit.id);
    if (index < 0) throw new UserError("write intent unit disappeared");
    rows[index] = unit;
    await saveUnits(store, rows);
  }
  if (ledger !== undefined) {
    const rows = [...(await readLedger(store))];
    const index = rows.findIndex(
      (row) =>
        row.pr === ledger.pr && row.sha === ledger.sha,
    );
    if (index < 0) rows.push(ledger);
    else rows[index] = ledger;
    await saveLedger(store, rows);
  }
  if (attempt !== undefined) await saveAttempt(store, attempt);
  await atomicWrite(
    path,
    `${JSON.stringify({ ...intent, completed: true }, null, 2)}\n`,
  );
}

async function mutationAuthority(
  store: string,
  unit: Unit | undefined,
  attemptId?: string,
): Promise<Attempt | undefined> {
  const rows = await readAttempts(store);
  if (attemptId === undefined) {
    if (unit !== undefined && rows.some((row) => row.unit === unit.id && row.settled?.kind !== "finished"))
      throw new UserError(`tracked unit ${unit.id} requires an attempt`);
    return undefined;
  }
  const id = safeId(attemptId);
  const attempt = currentAttempts(rows).find((row) => row.id === id);
  if (attempt === undefined) throw new UserError("stale or unknown attempt");
  if (attempt.settled?.kind === "finished")
    throw new UserError("explicitly finished attempt cannot authorize effects");
  if (unit === undefined || attempt.unit !== unit.id)
    throw new UserError("attempt is not bound to this unit");
  if (attempt.target.pr !== unit.pr || attempt.target.sha !== unit.sha)
    throw new UserError("attempt head changed");
  return attempt;
}

function reboundAttempt(attempt: Attempt, unit: Unit): Attempt {
  if (attempt.target.pr === unit.pr && attempt.target.sha === unit.sha)
    return attempt;
  return {
    ...attempt,
    binding: randomUUID(),
    target: { pr: unit.pr, sha: unit.sha },
  };
}

function completionBinding(pointer: InboxPointer, attempt: Attempt): CompletionBinding {
  const completion = pointer.completion;
  if (completion === undefined)
    throw new UserError("unbound completion requires inspection or discard");
  if (completion.binding !== attempt.binding)
    throw new UserError("completion binding changed");
  const introducingHead =
    attempt.authority === "worker" &&
    attempt.target.pr === "" && attempt.target.sha === "";
  if (!introducingHead && (
    completion.pr !== attempt.target.pr || completion.sha !== attempt.target.sha
  ))
    throw new UserError("completion report head changed");
  return completion;
}

function updatedUnit(old: Unit, params: SetUnitParams): Unit {
  return {
    ...old,
    state: requiredCell(params.state, "state"),
    branch:
      params.branch === undefined
        ? old.branch
        : requiredCell(params.branch, "branch"),
    pr:
      params.pr === undefined
        ? old.pr
        : String(positiveInteger(params.pr, "PR")),
    sha: params.sha === undefined ? old.sha : requiredCell(params.sha, "SHA"),
  };
}

async function ledgerEffect(
  store: string,
  params: RecordLedgerParams,
  unit?: Unit,
  attempt?: Attempt,
): Promise<LedgerEntry> {
  const pr = String(positiveInteger(params.pr, "PR"));
  const sha = requiredCell(params.sha, "SHA");
  const boundUnits = (await readUnits(store)).filter((row) => row.pr === pr);
  if (attempt === undefined) {
    const tracked = await readAttempts(store);
    if (boundUnits.some((row) => tracked.some((a) => a.unit === row.id && a.settled?.kind !== "finished")))
      throw new UserError("tracked ledger mutation requires an attempt");
  } else if (unit?.pr !== pr || unit.sha !== sha)
    throw new UserError("verdict does not match the current unit PR/head");
  const verifier =
    attempt === undefined
      ? params.verifier === undefined
        ? ""
        : requiredCell(params.verifier, "verifier")
      : attempt.authority === "verifier"
        ? attempt.id
        : "";
  const old = (await readLedger(store)).find(
    (row) => row.pr === pr && row.sha === sha,
  );
  if (old !== undefined && old.verifier !== "" && verifier === "")
    throw new UserError("worker cannot replace a verifier verdict");
  return {
    pr,
    sha,
    verdict: parseVerdict(params.verdict),
    evidence: requiredCell(params.evidence, "evidence"),
    verifier,
    ts: new Date().toISOString(),
  };
}

function renderGates(rows: readonly Gate[]): string {
  if (rows.length === 0) {
    return "";
  }
  const blocks = rows.map((gate) => {
    const answer =
      gate.kind === "resolved" ? `\n- Answer: ${gate.answer}` : "";
    return `## ${gate.id}

- Status: ${gate.kind}
- Question: ${gate.question}
- Options: ${gate.options}
- Default: ${gate.defaultAnswer}${answer}`;
  });
  return `# Gates\n\n${blocks.join("\n\n")}\n`;
}

async function readGates(store: string): Promise<readonly Gate[]> {
  const raw = (await requiredFile(join(store, "gates.md")))
    .replace(/\r/g, "")
    .trim();
  if (raw.length === 0) {
    return [];
  }
  const prefix = "# Gates\n\n## ";
  if (!raw.startsWith(prefix)) {
    throw new UserError("gates.md has an invalid heading");
  }
  const result: Gate[] = [];
  for (const block of raw.slice(prefix.length).split("\n\n## ")) {
    const lines = block.split("\n").filter((value) => value.length > 0);
    const id = lines.shift() ?? "";
    const fields = new Map<string, string>();
    for (const value of lines) {
      const match = /^- ([^:]+): (.*)$/.exec(value);
      if (match === null) {
        throw new UserError(`gates.md has a malformed gate ${id}`);
      }
      fields.set(match[1] ?? "", match[2] ?? "");
    }
    const status = fields.get("Status");
    const question = fields.get("Question");
    const options = fields.get("Options");
    const defaultAnswer = fields.get("Default");
    if (
      id.length === 0 ||
      question === undefined ||
      options === undefined ||
      defaultAnswer === undefined
    ) {
      throw new UserError(`gates.md has a malformed gate ${id}`);
    }
    if (status === "open") {
      result.push({ kind: "open", id, question, options, defaultAnswer });
    } else if (status === "resolved" && fields.has("Answer")) {
      result.push({
        kind: "resolved",
        id,
        question,
        options,
        defaultAnswer,
        answer: fields.get("Answer") ?? "",
      });
    } else {
      throw new UserError(`gates.md has invalid status ${status ?? ""}`);
    }
  }
  if (new Set(result.map((gate) => gate.id)).size !== result.length) {
    throw new UserError("gates.md has duplicate gate ids");
  }
  return result;
}

function parseFrontier(raw: string): Frontier {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new UserError("frontier.json is not valid JSON");
  }
  if (!isRecord(value)) {
    throw new UserError("frontier.json must contain an object");
  }
  if (Object.keys(value).length === 0) {
    return { generation: 0, prs: [], lowestUnmerged: null };
  }
  if (
    typeof value.generation !== "number" ||
    !Number.isSafeInteger(value.generation) ||
    value.generation < 0 ||
    !isUnknownArray(value.prs) ||
    !(
      value.lowestUnmerged === null ||
      (typeof value.lowestUnmerged === "number" &&
        Number.isSafeInteger(value.lowestUnmerged))
    )
  ) {
    throw new UserError("frontier.json has an invalid shape");
  }
  const prs: FrontierPr[] = [];
  for (const row of value.prs) {
    const state = isRecord(row)
      ? frontierPrStateOrNull(row.state)
      : null;
    if (
      !isRecord(row) ||
      typeof row.pr !== "number" ||
      !Number.isSafeInteger(row.pr) ||
      row.pr < 1 ||
      typeof row.branches !== "string" ||
      row.branches.length === 0 ||
      typeof row.sha !== "string" ||
      state === null
    ) {
      throw new UserError("frontier.json has an invalid PR row");
    }
    prs.push({
      pr: row.pr,
      branches: row.branches,
      sha: row.sha,
      state,
    });
  }
  return {
    generation: value.generation,
    prs,
    lowestUnmerged: value.lowestUnmerged,
  };
}

async function readFrontier(store: string): Promise<Frontier> {
  return parseFrontier(await requiredFile(join(store, "frontier.json")));
}

async function readStanding(
  store: string
): Promise<readonly StandingLine[]> {
  const raw = (await requiredFile(join(store, "preferences.md"))).replace(
    /\r/g,
    ""
  );
  if (raw.trim().length === 0) {
    return [];
  }
  const result: StandingLine[] = [];
  for (const value of raw.split("\n").filter((item) => item.length > 0)) {
    const match = /^([1-9]\d*)\. (.+)$/.exec(value);
    const number = Number(match?.[1] ?? 0);
    if (match === null || number !== result.length + 1) {
      throw new UserError("preferences.md has malformed numbering");
    }
    result.push({ number, line: match[2] ?? "" });
  }
  return result;
}

function countValues(values: readonly string[]): Counts {
  const result: Record<string, number> = {};
  for (const value of values) {
    result[value] = (result[value] ?? 0) + 1;
  }
  return Object.fromEntries(
    Object.entries(result).sort(([left], [right]) =>
      left.localeCompare(right)
    )
  );
}

function summarize(
  unitRows: readonly Unit[],
  ledgerRows: readonly LedgerEntry[],
  currentFrontier: Frontier,
  gateRows: readonly Gate[]
): StatusSummary {
  return {
    unitStates: countValues(unitRows.map((unit) => unit.state)),
    ledgerVerdicts: countValues(ledgerRows.map((row) => row.verdict)),
    frontierGeneration: currentFrontier.generation,
    openGateIds: gateRows
      .filter((gate): gate is OpenGate => gate.kind === "open")
      .map((gate) => gate.id)
      .sort(),
  };
}

function countRecord(value: unknown): Record<string, number> | null {
  if (!isRecord(value)) {
    return null;
  }
  const result: Record<string, number> = {};
  for (const [name, count] of Object.entries(value)) {
    if (
      typeof count !== "number" ||
      !Number.isSafeInteger(count) ||
      count < 0
    ) {
      return null;
    }
    result[name] = count;
  }
  return result;
}

function previousSummary(raw: string): StatusSummary | null {
  const match = /<!-- orch-summary (.+) -->/.exec(raw);
  if (match === null) {
    return null;
  }
  let value: unknown;
  try {
    value = JSON.parse(match[1] ?? "");
  } catch {
    return null;
  }
  if (
    !isRecord(value) ||
    typeof value.frontierGeneration !== "number" ||
    !isUnknownArray(value.openGateIds)
  ) {
    return null;
  }
  const unitStates = countRecord(value.unitStates);
  const ledgerVerdicts = countRecord(value.ledgerVerdicts);
  const openGateIds = value.openGateIds.filter(
    (item): item is string => typeof item === "string"
  );
  if (
    unitStates === null ||
    ledgerVerdicts === null ||
    openGateIds.length !== value.openGateIds.length
  ) {
    return null;
  }
  return {
    unitStates,
    ledgerVerdicts,
    frontierGeneration: value.frontierGeneration,
    openGateIds,
  };
}

function changed(before: StatusSummary | null, after: StatusSummary): string {
  if (before === null) {
    return "first render";
  }
  const result: string[] = [];
  const groups: readonly {
    readonly label: string;
    readonly oldCounts: Counts;
    readonly newCounts: Counts;
  }[] = [
    {
      label: "units",
      oldCounts: before.unitStates,
      newCounts: after.unitStates,
    },
    {
      label: "ledger",
      oldCounts: before.ledgerVerdicts,
      newCounts: after.ledgerVerdicts,
    },
  ];
  for (const { label, oldCounts, newCounts } of groups) {
    const names = [
      ...new Set([...Object.keys(oldCounts), ...Object.keys(newCounts)]),
    ].sort();
    for (const name of names) {
      const oldCount = oldCounts[name] ?? 0;
      const newCount = newCounts[name] ?? 0;
      if (oldCount !== newCount) {
        result.push(`${label} ${name} ${oldCount}->${newCount}`);
      }
    }
  }
  if (before.frontierGeneration !== after.frontierGeneration) {
    result.push(
      `frontier generation ${before.frontierGeneration}->${after.frontierGeneration}`
    );
  }
  if (before.openGateIds.join("\0") !== after.openGateIds.join("\0")) {
    result.push(
      `open gates ${before.openGateIds.length}->${after.openGateIds.length}`
    );
  }
  return result.length === 0 ? "no derived changes" : result.join("; ");
}

function markdown(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/\|/g, "\\|");
}

function table(
  headers: readonly string[],
  rows: readonly (readonly string[])[]
): string {
  if (rows.length === 0) {
    return "(none)";
  }
  return [
    `| ${headers.join(" | ")} |`,
    `| ${headers.map(() => "---").join(" | ")} |`,
    ...rows.map((row) => `| ${row.map(markdown).join(" | ")} |`),
  ].join("\n");
}

function statusMarkdown(
  unitRows: readonly Unit[],
  ledgerRows: readonly LedgerEntry[],
  currentFrontier: Frontier,
  gateRows: readonly Gate[],
  currentSummary: StatusSummary
): string {
  return `# Orchestrate status

Generated: ${new Date().toISOString()}

## Units

States: ${countLine(currentSummary.unitStates)}

${table(
  ["ID", "Track", "State", "Branch", "PR", "SHA", "Brief"],
  unitRows.map(unitCells)
)}

## Verification ledger

Verdicts: ${countLine(currentSummary.ledgerVerdicts)}

${table(
  ["PR", "SHA", "Verdict", "Evidence", "Verifier", "Timestamp"],
  ledgerRows.map(ledgerCells)
)}

## Frontier

Generation: ${currentFrontier.generation}
Lowest unmerged: ${currentFrontier.lowestUnmerged ?? "none"}

${table(
  ["Branch", "PR", "SHA", "State"],
  currentFrontier.prs.map((row) => [
    row.branches,
    String(row.pr),
    row.sha,
    row.state,
  ])
)}

## Gates

${table(
  ["ID", "Status", "Question", "Options", "Default", "Answer"],
  gateRows.map((gate) => [
    gate.id,
    gate.kind,
    gate.question,
    gate.options,
    gate.defaultAnswer,
    gate.kind === "resolved" ? gate.answer : "",
  ])
)}

<!-- orch-summary ${JSON.stringify(currentSummary)} -->
`;
}

function countLine(value: Counts): string {
  const entries = Object.entries(value);
  return entries.length === 0
    ? "none"
    : entries.map(([name, count]) => `${name}=${count}`).join(", ");
}

const OPEN_GT_PR_STATUSES = new Set([
  "Trunk branch locked",
  "Changes requested",
  "Waiting on PRs in this stack to merge",
  "Waiting on downstack merge state",
  "Draft",
  "Required checks failed",
  "Undergoing failure detection",
  "Merge queue failed on current head commit",
  "Handed off to merge queue...",
  "Waiting on downstack",
  "Merge conflicts",
  "Needs reviewers",
  "Needs approvals",
  "Needs restack",
  "Queued to merge...",
  "Ready to merge",
  "Ready to merge as stack",
  "Rebasing...",
  "Waiting on CI...",
  "Stale, needs rebase onto trunk",
  "Unresolved comments",
  "Waiting on required CI",
  "Waiting to merge...",
]);

interface GtPullRequest {
  readonly pr: number;
  readonly state: FrontierPrState;
}

interface GtFrontierEntry extends GtPullRequest {
  readonly branches: string;
}

interface GithubPullRequest {
  readonly pr: number;
  readonly branches: string;
  readonly sha: string;
  readonly state: FrontierPrState;
  readonly base: string;
  readonly isCrossRepository: boolean;
}

interface FrontierResolution {
  readonly source: "gt" | "GitHub";
  readonly prs: readonly FrontierPr[];
}

function parseGtPullRequest({
  branch,
  detail,
}: {
  branch: string;
  detail: string;
}): GtPullRequest {
  const match =
    /^(?:\[origin\] )?PR #([1-9]\d*)(?: \(([^)\r\n]+)\))?(?: .+)?$/.exec(
      detail
    );
  const pr = Number(match?.[1] ?? 0);
  if (match === null || !Number.isSafeInteger(pr)) {
    throw new UserError(
      `gt info output has an invalid PR row for branch ${branch}: ${detail}`
    );
  }
  const status = match[2];
  if (status === "Merged") {
    return { pr, state: "MERGED" };
  }
  if (status === "Closed") {
    return { pr, state: "CLOSED" };
  }
  if (status === undefined || OPEN_GT_PR_STATUSES.has(status)) {
    return { pr, state: "OPEN" };
  }
  throw new UserError(
    `gt info output has an unknown PR state for branch ${branch}: ${status}`
  );
}

function parseGtBranches(raw: string): readonly string[] {
  const branches: string[] = [];
  const lines = raw.replace(/\r/g, "").split("\n");
  for (const [index, line] of lines.entries()) {
    if (line.length === 0) {
      continue;
    }
    const branchMatch =
      /^(?:│ )*[◯◉] +([^\s]+)((?: \([^()\r\n]*\))*)$/.exec(line);
    if (branchMatch === null) {
      throw new UserError(
        `gt log short output has an unparseable line ${index + 1}: ${JSON.stringify(line)}`
      );
    }
    const branch = branchMatch[1] ?? "";
    if (branches.includes(branch)) {
      throw new UserError(
        `gt log short output contains duplicate branch ${branch}`
      );
    }
    branches.push(branch);
  }
  const trunk = branches[0];
  if (trunk === undefined) {
    throw new UserError("gt log short output did not contain a stack");
  }
  return branches.slice(1);
}

function graphitePullRequest({
  branch,
  repo,
}: {
  branch: string;
  repo: string;
}): GtPullRequest {
  let raw: string;
  try {
    raw = execFileSync("gt", ["--no-interactive", "info", branch], {
      cwd: repo,
      encoding: "utf8",
      env: { ...process.env, NO_COLOR: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    throw new UserError(
      `gt info ${branch} failed: ${errorMessage(error)}`
    );
  }
  const rows = raw
    .replace(/\r/g, "")
    .split("\n")
    .filter(
      (line) =>
        line.startsWith("PR #") || line.startsWith("[origin] PR #")
    );
  if (rows.length === 0) {
    throw new UserError(
      `gt info output branch ${branch} has no pull request; this clone's gt metadata may predate the submit, so resolve the frontier from the stacker's clone or after gt sync`
    );
  }
  if (rows.length > 1) {
    throw new UserError(
      `gt info output contains multiple PRs for branch ${branch}`
    );
  }
  return parseGtPullRequest({ branch, detail: rows[0] ?? "" });
}

function graphiteFrontier(repo: string): readonly GtFrontierEntry[] {
  let raw: string;
  try {
    raw = execFileSync(
      "gt",
      ["--no-interactive", "log", "short", "--stack", "--reverse"],
      {
        cwd: repo,
        encoding: "utf8",
        env: { ...process.env, NO_COLOR: "1" },
        stdio: ["ignore", "pipe", "pipe"],
      }
    );
  } catch (error) {
    throw new UserError(
      `gt log short --stack --reverse failed: ${errorMessage(error)}`
    );
  }
  const result = parseGtBranches(raw).map((branch) => ({
    branches: branch,
    ...graphitePullRequest({ branch, repo }),
  }));
  if (new Set(result.map((row) => row.pr)).size !== result.length) {
    throw new UserError("gt info output contains duplicate pull requests");
  }
  return result;
}

function branchSha({
  branch,
  repo,
}: {
  branch: string;
  repo: string;
}): string {
  let raw: string;
  try {
    raw = execFileSync("git", ["rev-parse", branch], {
      cwd: repo,
      encoding: "utf8",
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    throw new UserError(
      `git rev-parse ${branch} failed: ${errorMessage(error)}`
    );
  }
  const sha = raw.trim();
  if (!/^[0-9a-f]{40,64}$/i.test(sha)) {
    throw new UserError(`git rev-parse ${branch} returned an invalid SHA`);
  }
  return sha;
}

function graphiteIsAvailable(repo: string): boolean {
  try {
    execFileSync("gt", ["--version"], {
      cwd: repo,
      encoding: "utf8",
      env: { ...process.env, NO_COLOR: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    return true;
  } catch (error) {
    if (errorCode(error) === "ENOENT") {
      return false;
    }
    throw new UserError(`gt --version failed: ${errorMessage(error)}`);
  }
}

function requireGitRepository(repo: string): void {
  let raw: string;
  try {
    raw = execFileSync("git", ["rev-parse", "--is-inside-work-tree"], {
      cwd: repo,
      encoding: "utf8",
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    throw new UserError(
      `repo directory is not an accessible Git worktree: ${errorMessage(error)}`
    );
  }
  if (raw.trim() !== "true") {
    throw new UserError(`repo directory is not a Git worktree: ${repo}`);
  }
}

function currentBranch(repo: string): string {
  let raw: string;
  try {
    raw = execFileSync("git", ["branch", "--show-current"], {
      cwd: repo,
      encoding: "utf8",
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    throw new UserError(
      `git branch --show-current failed: ${errorMessage(error)}`
    );
  }
  const branch = raw.trim();
  if (branch.length === 0) {
    throw new UserError(
      "GitHub frontier discovery requires a checked out branch"
    );
  }
  return branch;
}

function githubPullRequest(value: unknown): GithubPullRequest {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new UserError("gh pr list returned a malformed pull request row");
  }
  const row = value as Record<string, unknown>;
  const pr = row.number;
  const branches = row.headRefName;
  const sha = row.headRefOid;
  const base = row.baseRefName;
  const state = row.state;
  const isCrossRepository = row.isCrossRepository;
  if (
    typeof pr !== "number" ||
    !Number.isSafeInteger(pr) ||
    pr < 1 ||
    typeof branches !== "string" ||
    branches.length === 0 ||
    typeof sha !== "string" ||
    !/^[0-9a-f]{40,64}$/i.test(sha) ||
    typeof base !== "string" ||
    base.length === 0 ||
    typeof isCrossRepository !== "boolean" ||
    (state !== "OPEN" && state !== "MERGED" && state !== "CLOSED")
  ) {
    throw new UserError("gh pr list returned a malformed pull request row");
  }
  return { pr, branches, sha, base, state, isCrossRepository };
}

function githubFrontier(repo: string): readonly FrontierPr[] {
  let repository: string;
  try {
    repository = execFileSync("git", ["remote", "get-url", "origin"], {
      cwd: repo,
      encoding: "utf8",
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
  } catch (error) {
    throw new UserError(
      `git remote get-url origin failed: ${errorMessage(error)}; GitHub frontier discovery requires an origin remote`
    );
  }
  if (repository.length === 0) {
    throw new UserError(
      "GitHub frontier discovery requires a nonempty origin URL"
    );
  }
  const identity = parseRemote(repository);
  if (identity === null) {
    throw new UserError(
      "GitHub frontier discovery requires a supported credential-free origin URL"
    );
  }

  let raw: string;
  try {
    const { GH_REPO: _ignoredRepo, ...env } = process.env;
    raw = execFileSync(
      "gh",
      [
        "pr",
        "list",
        "--repo",
        `${identity.host}/${identity.owner}/${identity.repo}`,
        "--state",
        "all",
        "--limit",
        "1000",
        "--json",
        "number,state,headRefName,headRefOid,baseRefName,isCrossRepository",
      ],
      {
        cwd: repo,
        encoding: "utf8",
        env,
        stdio: ["ignore", "pipe", "pipe"],
      }
    );
  } catch (error) {
    if (errorCode(error) === "ENOENT") {
      throw new UserError(
        "GitHub frontier discovery requires gh; install GitHub CLI, or pass --graphite for a stack Graphite tracks"
      );
    }
    throw new UserError(`gh pr list failed: ${errorMessage(error)}`);
  }

  let decoded: unknown;
  try {
    decoded = JSON.parse(raw);
  } catch (error) {
    throw new UserError(`gh pr list returned invalid JSON: ${errorMessage(error)}`);
  }
  if (!Array.isArray(decoded)) {
    throw new UserError("gh pr list returned an invalid response");
  }
  if (decoded.length === 1000) {
    throw new UserError(
      "gh pr list reached its 1000 PR limit; cannot prove complete repository history; pass --graphite for a stack Graphite tracks before resolving the frontier"
    );
  }

  const byBranch = new Map<string, GithubPullRequest[]>();
  const byPr = new Set<number>();
  for (const value of decoded) {
    const row = githubPullRequest(value);
    if (byPr.has(row.pr)) {
      throw new UserError(`gh pr list returned duplicate PR #${row.pr}`);
    }
    byPr.add(row.pr);
    const rows = byBranch.get(row.branches) ?? [];
    rows.push(row);
    byBranch.set(row.branches, rows);
  }

  const children = new Map<string, GithubPullRequest[]>();
  for (const rows of byBranch.values()) {
    for (const row of rows) {
      const childrenForBase = children.get(row.base) ?? [];
      childrenForBase.push(row);
      children.set(row.base, childrenForBase);
    }
  }

  const singleBranchRow = ({
    branch,
    candidates,
    description,
  }: {
    branch: string;
    candidates: readonly GithubPullRequest[];
    description: string;
  }): GithubPullRequest | undefined => {
    if (candidates.length === 0) {
      return undefined;
    }
    if (candidates.length > 1) {
      throw new UserError(
        `GitHub frontier discovery found multiple PRs for ${description} ${branch}`
      );
    }
    return candidates[0];
  };

  const branch = currentBranch(repo);
  const selected = singleBranchRow({
    branch,
    candidates: byBranch.get(branch) ?? [],
    description: "checked out branch",
  });
  if (selected === undefined) {
    throw new UserError(
      `GitHub frontier discovery found no PR for checked out branch ${branch}; checkout a branch in the stack, or pass --graphite for a stack Graphite tracks`
    );
  }
  if (selected.isCrossRepository) {
    throw new UserError(
      "GitHub frontier discovery does not support cross-repository stacks; pass --graphite for a stack Graphite tracks"
    );
  }

  const ancestors: GithubPullRequest[] = [];
  const seen = new Set<string>([selected.branches]);
  let cursor = selected;
  while (true) {
    const baseCandidates = byBranch.get(cursor.base) ?? [];
    if (baseCandidates.some((row) => row.isCrossRepository)) {
      throw new UserError(
        "GitHub frontier discovery does not support cross-repository stacks; pass --graphite for a stack Graphite tracks"
      );
    }
    const parent = singleBranchRow({
      branch: cursor.base,
      candidates: baseCandidates,
      description: "base branch",
    });
    if (parent === undefined) {
      break;
    }
    if (seen.has(parent.branches)) {
      throw new UserError("gh pr list contains a cyclic stack");
    }
    seen.add(parent.branches);
    ancestors.unshift(parent);
    cursor = parent;
  }

  for (const row of [...ancestors, selected]) {
    if ((children.get(row.branches) ?? []).length > 1) {
      throw new UserError(
        `GitHub frontier discovery found a branched stack above ${row.branches}`
      );
    }
  }
  const descendants: GithubPullRequest[] = [];
  cursor = selected;
  while (true) {
    const candidates = children.get(cursor.branches) ?? [];
    if (candidates.length === 0) {
      break;
    }
    if (candidates.length > 1) {
      throw new UserError(
        `GitHub frontier discovery found a branched stack above ${cursor.branches}`
      );
    }
    const child = candidates[0];
    if (child === undefined) {
      break;
    }
    if (child.isCrossRepository) {
      throw new UserError(
        "GitHub frontier discovery does not support cross-repository stacks; pass --graphite for a stack Graphite tracks"
      );
    }
    if (seen.has(child.branches)) {
      throw new UserError("gh pr list contains a cyclic stack");
    }
    seen.add(child.branches);
    descendants.push(child);
    cursor = child;
  }

  return [...ancestors, selected, ...descendants].map(
    ({ base: _base, isCrossRepository: _isCrossRepository, ...row }) => row
  );
}

function resolveFrontier(
  repo: string,
  discovery: FrontierDiscovery
): FrontierResolution {
  requireGitRepository(repo);
  if (discovery === "github") {
    return { source: "GitHub", prs: githubFrontier(repo) };
  }
  if (!graphiteIsAvailable(repo)) {
    throw new UsageError(
      "--graphite requires gt; install Graphite or omit --graphite to discover the frontier through GitHub"
    );
  }
  return {
    source: "gt",
    prs: graphiteFrontier(repo).map((row) => ({
    ...row,
    sha: branchSha({ branch: row.branches, repo }),
    })),
  };
}

function validateFrontierPin({
  actual,
  expected,
  source,
}: {
  actual: readonly number[];
  expected: readonly number[];
  source: "gt" | "GitHub";
}): void {
  if (
    actual.length === expected.length &&
    actual.every((pr, index) => pr === expected[index])
  ) {
    return;
  }
  const actualSet = new Set(actual);
  const expectedSet = new Set(expected);
  const missing = expected.filter((pr) => !actualSet.has(pr));
  const extra = actual.filter((pr) => !expectedSet.has(pr));
  const drift: string[] = [];
  if (missing.length > 0) {
    drift.push(`missing from ${source}: ${missing.join(",")}`);
  }
  if (extra.length > 0) {
    drift.push(`extra in ${source}: ${extra.join(",")}`);
  }
  if (missing.length === 0 && extra.length === 0) {
    drift.push(
      `order differs: expected ${expected.join(",")}; ${source} ${actual.join(",")}`
    );
  }
  throw new UserError(`frontier pin mismatch: ${drift.join("; ")}`);
}

export function openStore(
  directory: string,
  options: OpenStoreOptions = {}
): Store {
  const store = resolve(directory);
  const pending = new PendingBatchCollection(store);
  let closed = false;
  let releaseLock: (() => Promise<void>) | null = null;
  let lockRequest: Promise<void> | null = null;

  const ensureOpen = (): void => {
    if (closed) {
      throw new UserError("store is closed");
    }
  };

  const ensureLock = async (): Promise<void> => {
    ensureOpen();
    if (releaseLock !== null) {
      return;
    }
    if (lockRequest === null) {
      lockRequest = acquireLock(store, options).then((release) => {
        releaseLock = release;
      });
    }
    try {
      await lockRequest;
    } catch (error) {
      lockRequest = null;
      throw error;
    }
  };

  const beginWrite = async (): Promise<void> => {
    ensureOpen();
    if (!(await exists(store))) {
      throw new UserError(
        `store is not initialized at ${store}; run orch init`
      );
    }
    await ensureLock();
    await repairStore(store, pending);
  };

  const claim = async (): Promise<Batch | null> => {
    await beginWrite();
    return pending.claim();
  };

  return {
    units: {
      add: async (params) => {
        await beginWrite();
        const row: Unit = {
          id: requiredCell(params.id, "unit id"),
          track: requiredCell(params.track, "track"),
          state: "pending",
          branch: "",
          pr: "",
          sha: "",
          brief:
            params.brief === undefined
              ? ""
              : requiredCell(params.brief, "brief"),
        };
        const rows = [...(await readUnits(store))];
        if (rows.some((unit) => unit.id === row.id)) {
          throw new UserError(`unit ${row.id} already exists`);
        }
        rows.push(row);
        await saveUnits(store, rows);
        return row;
      },
      set: async (params) => {
        await beginWrite();
        const id = requiredCell(params.id, "unit id");
        const old = (await readUnits(store)).find((unit) => unit.id === id);
        if (old === undefined) throw new NotFoundError(`unit ${id} not found`);
        const attempt = await mutationAuthority(store, old, params.attempt);
        const row = updatedUnit(old, params);
        await writeIntent(store, {
          unit: row,
          ...(attempt === undefined
            ? {}
            : { attempt: reboundAttempt(attempt, row) }),
        });
        return row;
      },
      get: async (id) => {
        await beginWrite();
        const cleanId = requiredCell(id, "unit id");
        const row = (await readUnits(store)).find(
          (unit) => unit.id === cleanId
        );
        if (row === undefined) {
          throw new NotFoundError(`unit ${cleanId} not found`);
        }
        return row;
      },
      list: async (params = {}) => {
        await beginWrite();
        const state =
          params.state === undefined
            ? undefined
            : requiredCell(params.state, "state");
        const track =
          params.track === undefined
            ? undefined
            : requiredCell(params.track, "track");
        return (await readUnits(store)).filter(
          (unit) =>
            (state === undefined || unit.state === state) &&
            (track === undefined || unit.track === track)
        );
      },
      counts: async () => {
        await beginWrite();
        return countValues(
          (await readUnits(store)).map((unit) => unit.state)
        );
      },
    },
    ledger: {
      record: async (params) => {
        await beginWrite();
        const attempts = await readAttempts(store);
        const bound =
          params.attempt === undefined
            ? undefined
            : attempts.find((row) => row.id === params.attempt);
        const unit =
          bound === undefined
            ? undefined
            : (await readUnits(store)).find((row) => row.id === bound.unit);
        const attempt = await mutationAuthority(store, unit, params.attempt);
        const row = await ledgerEffect(store, params, unit, attempt);
        await writeIntent(store, {
          ledger: row,
          ...(attempt === undefined
            ? {}
            : { attempt: { ...attempt, settled: { kind: "accepted", at: row.ts } } }),
        });
        return row;
      },
      check: async (params) => {
        await beginWrite();
        const pr = String(positiveInteger(params.pr, "PR"));
        const sha = requiredCell(params.sha, "SHA");
        const row = (await readLedger(store)).find(
          (value) => value.pr === pr && value.sha === sha
        );
        if (row === undefined) {
          throw new NotFoundError("NOT-VERIFIED", {
            compact: "NOT-VERIFIED",
            json: { pr, sha, verdict: "NOT-VERIFIED" },
          });
        }
        return row;
      },
      summary: async () => {
        await beginWrite();
        return countValues(
          (await readLedger(store)).map((row) => row.verdict)
        );
      },
    },
    inbox: {
      push: async (params) => {
        ensureOpen();
        await requiredFile(join(store, "units.tsv"));
        if (params.binding === undefined && (
          params.pr !== undefined || params.sha !== undefined
        ))
          throw new UserError("claimed completion head requires a binding");
        if (params.binding !== undefined && params.attempt === undefined)
          throw new UserError("completion binding requires an attempt");
        const pointer: InboxPointer = {
          ts: new Date().toISOString(),
          agent: requiredCell(params.agent, "agent"),
          unit: requiredCell(params.unit, "unit"),
          status: requiredCell(params.status, "status"),
          report:
            params.report === undefined
              ? ""
              : requiredCell(params.report, "report"),
          ...(params.attempt === undefined
            ? {}
            : { attempt: safeId(params.attempt) }),
          ...(params.binding === undefined
            ? {}
            : { completion: parseCompletionBinding({
                binding: params.binding,
                pr: params.pr === undefined
                  ? "" : String(positiveInteger(params.pr, "PR")),
                sha: params.sha === undefined
                  ? "" : requiredCell(params.sha, "SHA"),
              }) }),
        };
        const filename = `${pointer.ts.replace(/[:.]/g, "-")}-${process.pid}-${randomUUID()}.tsv`;
        const temporary = join(store, `.inbox-push-${randomUUID()}.tmp`);
        await writeFile(
          temporary,
          `${pointerCells(pointer).map(cleanCell).join("\t")}\n`,
          { flag: "wx" },
        );
        try {
          while (true) {
            try {
              await rename(temporary, join(store, "inbox", filename));
              break;
            } catch (error) {
              if (errorCode(error) !== "ENOENT") throw error;
              await mkdir(join(store, "inbox"), { recursive: true });
            }
          }
        } finally {
          await rm(temporary, { force: true });
        }
        return { pointer, filename };
      },
      drain: async () => (await claim())?.events.map((event) => event.pointer) ?? [],
      claim,
      receipts: async () => {
        await beginWrite();
        const ids = [
          ...(await pending.ids()),
          ...(await batchIds(join(store, "inbox-batches"))),
        ].sort();
        return Promise.all(
          ids.map(async (id) => ({
            ...(await readBatch(store, id)),
            decisions: await savedDecisions(store, id),
          })),
        );
      },
      ack: async (batchId, input) => {
        await beginWrite();
        const batch = await readBatch(store, safeId(batchId));
        const decisions = parseAckDecisions(input);
        const saved = await savedDecisions(store, batch.id);
        for (const decision of decisions) {
          const prior = saved.find((row) => row.event === decision.event);
          if (prior !== undefined) {
            if (
              JSON.stringify(prior.outcome) !== JSON.stringify(decision.outcome)
            )
              throw new UserError("conflicting acknowledgment");
            continue;
          }
          const event = batch.events.find((row) => row.id === decision.event);
          if (event === undefined)
            throw new UserError(
              `event ${decision.event} is not in batch ${batch.id}`,
            );
          let unit: Unit | undefined;
          let ledger: LedgerEntry | undefined;
          let attempt: Attempt | undefined;
          if (decision.outcome.kind !== "discard") {
            const old = (await readUnits(store)).find(
              (row) => row.id === event.pointer.unit,
            );
            attempt = await mutationAuthority(
              store,
              old,
              event.pointer.attempt,
            );
            const completion = attempt === undefined
              ? undefined : completionBinding(event.pointer, attempt);
            if (decision.outcome.kind === "unit") {
              if (old === undefined)
                throw new NotFoundError(`unit ${event.pointer.unit} not found`);
              unit = updatedUnit(old, { id: old.id, ...decision.outcome });
              if (completion !== undefined && (
                unit.pr !== completion.pr || unit.sha !== completion.sha
              ))
                throw new UserError("unit outcome does not match completion report head");
              if (decision.outcome.ledger !== undefined)
                ledger = await ledgerEffect(
                  store,
                  decision.outcome.ledger,
                  unit,
                  attempt,
                );
            } else
              ledger = await ledgerEffect(
                store,
                decision.outcome,
                old,
                attempt,
              );
          }
          const normalized: SavedDecision = {
            ...decision,
            ...(unit === undefined ? {} : { unit }),
            ...(ledger === undefined ? {} : { ledger }),
            ...(attempt === undefined
              ? {}
              : {
                  attempt: {
                    ...(unit === undefined ? attempt : reboundAttempt(attempt, unit)),
                    settled: {
                      kind: "accepted",
                      at: ledger?.ts ?? new Date().toISOString(),
                    },
                  },
                }),
            completed: false,
          };
          const directory = join(store, "inbox-pending", batch.id, "decisions");
          await mkdir(directory, { recursive: true });
          await atomicWrite(
            decisionPath(store, batch.id, decision.event),
            `${JSON.stringify(normalized, null, 2)}\n`,
          );
          await applyWriteIntent(
            store,
            decisionPath(store, batch.id, decision.event),
            normalized,
          );
        }
        const remaining = await readBatch(store, batch.id, true);
        if ((await pending.ids()).includes(batch.id)) await pending.retain(batch.id);
        return remaining;
      },
      peek: async () => {
        await beginWrite();
        return (await pending.events()).map((event) => event.pointer);
      },
      count: async () => {
        await beginWrite();
        return (await pending.events()).length;
      },
    },
    attempts: {
      begin: async (input) => {
        await beginWrite();
        const params = parseBeginAttempt(input);
        const rows = await readAttempts(store);
        const prior = rows.find((row) => row.requestId === params.requestId);
        if (prior !== undefined) {
          const {
            id: _id,
            binding: _binding,
            target: _target,
            observation: _observation,
            settled: _settled,
            ...request
          } = prior;
          if (JSON.stringify(request) !== JSON.stringify(params))
            throw new UserError("conflicting attempt requestId");
          return prior;
        }
        const unit = (await readUnits(store)).find(
          (row) => row.id === params.unit,
        );
        if (unit === undefined)
          throw new NotFoundError(`unit ${params.unit} not found`);
        const current = currentAttempts(rows).find((row) =>
          sameSlot(row, params),
        );
        if (params.replace !== current?.id)
          throw new UserError("attempt predecessor changed");
        const attempt: Attempt = {
          ...params,
          id: `attempt-${randomUUID()}`,
          binding: randomUUID(),
          target: { pr: unit.pr, sha: unit.sha },
          observation: { kind: "unknown" },
          settled: null,
        };
        await saveAttempt(store, attempt);
        return attempt;
      },
      observe: async (id, input) => {
        await beginWrite();
        const attempt = (await readAttempts(store)).find(
          (row) => row.id === safeId(id),
        );
        if (attempt === undefined)
          throw new NotFoundError(`attempt ${id} not found`);
        const observation = parseObservation(input);
        const row = { ...attempt, observation };
        await saveAttempt(store, row);
        return row;
      },
      list: async () => {
        await beginWrite();
        return readAttempts(store);
      },
      finish: async (id, reason) => {
        await beginWrite();
        const attempt = (await readAttempts(store)).find(
          (row) => row.id === safeId(id),
        );
        if (attempt === undefined)
          throw new UserError("stale or unknown attempt");
        const row: Attempt = {
          ...attempt,
          settled: { kind: "finished", reason: requiredLine(reason, "reason") },
        };
        await saveAttempt(store, row);
        return row;
      },
    },
    gates: {
      park: async (params) => {
        await beginWrite();
        const gate: OpenGate = {
          kind: "open",
          id: requiredLine(params.id, "gate id"),
          question: requiredLine(params.question, "question"),
          options: requiredLine(params.options, "options"),
          defaultAnswer: requiredLine(
            params.defaultAnswer,
            "default"
          ),
        };
        const rows = [...(await readGates(store))];
        const index = rows.findIndex((old) => old.id === gate.id);
        if (index < 0) {
          rows.push(gate);
        } else {
          rows[index] = gate;
        }
        await atomicWrite(join(store, "gates.md"), renderGates(rows));
        return gate;
      },
      list: async () => {
        ensureOpen();
        return (await readGates(store)).filter(
          (gate): gate is OpenGate => gate.kind === "open"
        );
      },
      resolve: async (params) => {
        await beginWrite();
        const id = requiredLine(params.id, "gate id");
        const rows = [...(await readGates(store))];
        const index = rows.findIndex((gate) => gate.id === id);
        const old = rows[index];
        if (index < 0 || old === undefined) {
          throw new NotFoundError(`gate ${id} not found`);
        }
        const gate: ResolvedGate = {
          kind: "resolved",
          id: old.id,
          question: old.question,
          options: old.options,
          defaultAnswer: old.defaultAnswer,
          answer: requiredLine(params.answer, "answer"),
        };
        rows[index] = gate;
        await atomicWrite(join(store, "gates.md"), renderGates(rows));
        return gate;
      },
    },
    frontier: {
      set: async (params) => {
        await beginWrite();
        const repo = resolve(requiredLine(params.repo, "repo directory"));
        const pin =
          params.prs === undefined
            ? undefined
            : params.prs.map((pr) => positiveInteger(pr, "PR"));
        if (pin !== undefined && new Set(pin).size !== pin.length) {
          throw new UserError("--prs must not contain duplicates");
        }
        const old = await readFrontier(store);
        const frontier = resolveFrontier(repo, params.discovery ?? "github");
        if (pin !== undefined) {
          validateFrontierPin({
            actual: frontier.prs.map((row) => row.pr),
            expected: pin,
            source: frontier.source,
          });
        }
        const value: Frontier = {
          generation: old.generation + 1,
          prs: frontier.prs,
          lowestUnmerged:
            frontier.prs.find((row) => row.state === "OPEN")?.pr ?? null,
        };
        await atomicWrite(
          join(store, "frontier.json"),
          `${JSON.stringify(value, null, 2)}\n`
        );
        return value;
      },
      show: async () => {
        ensureOpen();
        return readFrontier(store);
      },
    },
    standing: {
      show: async () => {
        ensureOpen();
        return readStanding(store);
      },
      add: async (params) => {
        await beginWrite();
        const rows = [...(await readStanding(store))];
        const item: StandingLine = {
          number: rows.length + 1,
          line: requiredLine(params.line, "standing order"),
        };
        rows.push(item);
        await atomicWrite(
          join(store, "preferences.md"),
          `${rows.map((row) => `${row.number}. ${row.line}`).join("\n")}\n`
        );
        return item;
      },
    },
    status: {
      render: async () => {
        await beginWrite();
        const unitRows = await readUnits(store);
        const ledgerRows = await readLedger(store);
        const currentFrontier = await readFrontier(store);
        const gateRows = await readGates(store);
        const currentSummary = summarize(
          unitRows,
          ledgerRows,
          currentFrontier,
          gateRows
        );
        const path = join(store, "status.md");
        const before = (await exists(path))
          ? previousSummary(await readFile(path, "utf8"))
          : null;
        const change = changed(before, currentSummary);
        await atomicWrite(
          path,
          statusMarkdown(
            unitRows,
            ledgerRows,
            currentFrontier,
            gateRows,
            currentSummary
          )
        );
        return {
          units: unitRows,
          ledger: ledgerRows,
          frontier: currentFrontier,
          gates: gateRows,
          summary: currentSummary,
          changed: change,
        };
      },
    },
    init: async () => {
      ensureOpen();
      await mkdir(store, { recursive: true });
      await ensureLock();
      await writeIfMissing(join(store, "units.tsv"), `${UNIT_HEADER}\n`);
      await writeIfMissing(join(store, "ledger.tsv"), `${LEDGER_HEADER}\n`);
      await mkdir(join(store, "inbox"), { recursive: true });
      await writeIfMissing(join(store, "gates.md"), "");
      await writeIfMissing(join(store, "preferences.md"), "");
      await writeIfMissing(join(store, "frontier.json"), "{}\n");
      return { store };
    },
    close: async () => {
      if (closed) {
        return;
      }
      if (lockRequest !== null) {
        try {
          await lockRequest;
        } catch {
          // A failed acquisition has no lock to release.
        }
      }
      const release = releaseLock;
      releaseLock = null;
      closed = true;
      if (release !== null) {
        await release();
      }
    },
  };
}
