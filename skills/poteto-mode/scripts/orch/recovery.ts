import {
  UserError,
  parseVerdict,
  type InboxPointer,
  type Unit,
  type LedgerEntry,
  type Verdict,
} from "./store.ts";

export interface Event {
  readonly id: string;
  readonly pointer: InboxPointer;
}
export interface Batch {
  readonly id: string;
  readonly events: readonly Event[];
}
export interface UnitOutcome {
  readonly kind: "unit";
  readonly state: string;
  readonly branch?: string;
  readonly pr?: number;
  readonly sha?: string;
  readonly ledger?: VerdictOutcome;
}
export interface VerdictOutcome {
  readonly kind: "verdict";
  readonly pr: number;
  readonly sha: string;
  readonly verdict: Verdict;
  readonly evidence: string;
  readonly verifier?: string;
}
export type AckOutcome =
  | UnitOutcome
  | VerdictOutcome
  | { readonly kind: "discard"; readonly reason: string };
export interface AckDecision {
  readonly event: string;
  readonly outcome: AckOutcome;
}
export interface Receipt extends Batch {
  readonly decisions: readonly SavedDecision[];
}
export interface WriteIntent {
  readonly unit?: Unit;
  readonly ledger?: LedgerEntry;
  readonly attempt?: Attempt;
  readonly completed: boolean;
}
export interface SavedDecision extends AckDecision, WriteIntent {}
export type Authority = "worker" | "verifier";
export interface AttemptSlot {
  readonly unit: string;
  readonly role: string;
  readonly arm: string;
  readonly authority: Authority;
}
export interface Resolution {
  readonly harness: string;
  readonly model: string;
  readonly effort: string;
}
export interface BeginAttempt extends AttemptSlot {
  readonly requestId: string;
  readonly replace?: string;
  readonly brief: string;
  readonly checkout: string;
  readonly resolution: Resolution;
}
export type Observation =
  | { readonly kind: "native"; readonly identity: string }
  | { readonly kind: "cli"; readonly receipt: string }
  | { readonly kind: "unknown" };
export interface Attempt extends BeginAttempt {
  readonly id: string;
  readonly target: { readonly pr: string; readonly sha: string };
  readonly observation: Observation;
  readonly settled: string | null;
}
export interface Requirement {
  readonly id: string;
  readonly unit: string;
  readonly states?: readonly string[];
  readonly ledger?: {
    readonly pr: number;
    readonly sha: string;
    readonly verdicts: readonly Verdict[];
  };
}
export interface Closeout {
  readonly ok: boolean;
  readonly failures: readonly string[];
  readonly pendingEvents: number;
  readonly pendingAttempts: readonly string[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function record(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) throw new UserError("expected a JSON object");
  return value;
}
function array(value: unknown): readonly unknown[] {
  if (!Array.isArray(value)) throw new UserError("expected a JSON array");
  return value;
}
function text(value: unknown): string {
  if (
    typeof value !== "string" ||
    value.trim().length === 0 ||
    /[\t\r\n]/.test(value)
  )
    throw new UserError("expected a nonempty single-line string");
  return value;
}
export function safeId(value: unknown): string {
  const id = text(value);
  if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(id))
    throw new UserError("invalid receipt or attempt id");
  return id;
}
function integer(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 1)
    throw new UserError("expected a positive integer");
  return value;
}
export function parseObservation(value: unknown): Observation {
  const row = record(value);
  switch (row.kind) {
    case "native":
      return { kind: "native", identity: text(row.identity) };
    case "cli":
      return { kind: "cli", receipt: text(row.receipt) };
    case "unknown":
      return { kind: "unknown" };
    default:
      throw new UserError("observation kind must be native, cli, or unknown");
  }
}
export function parseBeginAttempt(value: unknown): BeginAttempt {
  const row = record(value);
  const resolution = record(row.resolution);
  if (row.authority !== "worker" && row.authority !== "verifier")
    throw new UserError("authority must be worker or verifier");
  return {
    unit: text(row.unit),
    role: text(row.role),
    arm: text(row.arm),
    authority: row.authority,
    requestId: text(row.requestId),
    ...(row.replace === undefined ? {} : { replace: safeId(row.replace) }),
    brief: text(row.brief),
    checkout: text(row.checkout),
    resolution: {
      harness: text(resolution.harness),
      model: text(resolution.model),
      effort: text(resolution.effort),
    },
  };
}
export function parseAttempt(value: unknown): Attempt {
  const row = record(value);
  const target = record(row.target);
  if (
    typeof target.pr !== "string" ||
    typeof target.sha !== "string" ||
    !(row.settled === null || typeof row.settled === "string")
  )
    throw new UserError("invalid saved attempt");
  return {
    ...parseBeginAttempt(row),
    id: safeId(row.id),
    target: { pr: target.pr, sha: target.sha },
    observation: parseObservation(row.observation),
    settled: row.settled,
  };
}
function parseVerdictOutcome(value: unknown): VerdictOutcome {
  const row = record(value);
  if (row.kind !== "verdict") throw new UserError("expected a verdict outcome");
  return {
    kind: "verdict",
    pr: integer(row.pr),
    sha: text(row.sha),
    verdict: parseVerdict(text(row.verdict)),
    evidence: text(row.evidence),
    ...(row.verifier === undefined ? {} : { verifier: text(row.verifier) }),
  };
}
function parseOutcome(value: unknown): AckOutcome {
  const row = record(value);
  switch (row.kind) {
    case "discard":
      return { kind: "discard", reason: text(row.reason) };
    case "verdict":
      return parseVerdictOutcome(row);
    case "unit":
      return {
        kind: "unit",
        state: text(row.state),
        ...(row.branch === undefined ? {} : { branch: text(row.branch) }),
        ...(row.pr === undefined ? {} : { pr: integer(row.pr) }),
        ...(row.sha === undefined ? {} : { sha: text(row.sha) }),
        ...(row.ledger === undefined
          ? {}
          : { ledger: parseVerdictOutcome(row.ledger) }),
      };
    default:
      throw new UserError("outcome kind must be unit, verdict, or discard");
  }
}
export function parseAckDecisions(value: unknown): readonly AckDecision[] {
  const decisions = array(value).map((value) => {
    const row = record(value);
    return { event: safeId(row.event), outcome: parseOutcome(row.outcome) };
  });
  if (
    new Set(decisions.map((decision) => decision.event)).size !==
    decisions.length
  )
    throw new UserError("duplicate event decision");
  return decisions;
}
export function parseWriteIntent(value: unknown): WriteIntent {
  const row = record(value);
  if (typeof row.completed !== "boolean")
    throw new UserError("invalid saved write intent");
  let unit: Unit | undefined;
  if (row.unit !== undefined) {
    const u = record(row.unit);
    if (
      typeof u.branch !== "string" ||
      typeof u.pr !== "string" ||
      typeof u.sha !== "string" ||
      typeof u.brief !== "string"
    )
      throw new UserError("invalid saved unit effect");
    unit = {
      id: text(u.id),
      track: text(u.track),
      state: text(u.state),
      branch: u.branch,
      pr: u.pr,
      sha: u.sha,
      brief: u.brief,
    };
  }
  let ledger: LedgerEntry | undefined;
  if (row.ledger !== undefined) {
    const l = record(row.ledger);
    if (typeof l.verifier !== "string")
      throw new UserError("invalid saved ledger effect");
    ledger = {
      pr: text(l.pr),
      sha: text(l.sha),
      verdict: parseVerdict(text(l.verdict)),
      evidence: text(l.evidence),
      verifier: l.verifier,
      ts: text(l.ts),
    };
  }
  return {
    ...(unit === undefined ? {} : { unit }),
    ...(ledger === undefined ? {} : { ledger }),
    ...(row.attempt === undefined
      ? {}
      : { attempt: parseAttempt(row.attempt) }),
    completed: row.completed,
  };
}
export function parseSavedDecision(value: unknown): SavedDecision {
  const decision = parseAckDecisions([value])[0];
  if (decision === undefined) throw new UserError("invalid saved decision");
  return { ...decision, ...parseWriteIntent(value) };
}
export function parseRequirements(value: unknown): readonly Requirement[] {
  const rows = array(value).map((value) => {
    const row = record(value);
    const states =
      row.states === undefined ? undefined : array(row.states).map(text);
    const l = row.ledger === undefined ? undefined : record(row.ledger);
    const ledger =
      l === undefined
        ? undefined
        : {
            pr: integer(l.pr),
            sha: text(l.sha),
            verdicts: array(l.verdicts).map((value) =>
              parseVerdict(text(value)),
            ),
          };
    if (
      states?.length === 0 ||
      ledger?.verdicts.length === 0 ||
      (states === undefined && ledger === undefined)
    )
      throw new UserError(
        "requirement needs explicit states or ledger verdicts",
      );
    return {
      id: text(row.id),
      unit: text(row.unit),
      ...(states === undefined ? {} : { states }),
      ...(ledger === undefined ? {} : { ledger }),
    };
  });
  if (
    rows.length === 0 ||
    new Set(rows.map((row) => row.id)).size !== rows.length
  )
    throw new UserError("requirements must be nonempty with unique ids");
  return rows;
}
export function sameSlot(left: AttemptSlot, right: AttemptSlot): boolean {
  return (
    left.unit === right.unit &&
    left.role === right.role &&
    left.arm === right.arm &&
    left.authority === right.authority
  );
}
export function currentAttempts(rows: readonly Attempt[]): readonly Attempt[] {
  return rows.filter((row) => !rows.some((other) => other.replace === row.id));
}
