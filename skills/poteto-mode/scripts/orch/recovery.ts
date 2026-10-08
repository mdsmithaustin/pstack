import { isAbsolute } from "node:path";
import roleContract from "./role-contract.json";
import { UserError, parseVerdict, type Verdict } from "./validation.ts";
import {
  type InboxPointer,
  type Unit,
  type LedgerEntry,
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
declare const panelArm: unique symbol;
export type NumericPanelArm = number & { readonly [panelArm]: true };
declare const executionIdentity: unique symbol;
export type ConcreteExecutionIdentity = string & { readonly [executionIdentity]: true };

export interface AttemptSlot {
  readonly unit: string;
  readonly role: string;
  readonly arm: NumericPanelArm;
  readonly authority: Authority;
}
export interface Resolution {
  readonly harness: string;
  readonly model: ConcreteExecutionIdentity;
  readonly effort: ConcreteExecutionIdentity;
}
export interface CanonicalResolvedArm {
  readonly role: string;
  readonly arm: NumericPanelArm;
  readonly model: string;
  readonly effort: string;
  readonly source: string;
  readonly notes?: readonly string[];
  readonly step?: "up" | "down" | "same-model";
}
export interface ResolutionContext {
  readonly workModel: string | null;
  readonly resolvedArm: CanonicalResolvedArm;
}
export interface BeginAttempt extends AttemptSlot {
  readonly requestId: string;
  readonly replace?: string;
  readonly brief: string;
  readonly checkout: string;
  readonly resolution: Resolution;
  readonly resolutionContext?: ResolutionContext;
}
export type Observation =
  | { readonly kind: "native"; readonly identity: string }
  | { readonly kind: "cli"; readonly receipt: string }
  | { readonly kind: "unknown" };
export interface CompletionBinding {
  readonly binding: string;
  readonly pr: string;
  readonly sha: string;
}
export type Settlement =
  | { readonly kind: "accepted"; readonly at: string }
  | { readonly kind: "finished"; readonly reason: string };
export interface Attempt extends BeginAttempt {
  readonly id: string;
  readonly binding: string;
  readonly target: { readonly pr: string; readonly sha: string };
  readonly observation: Observation;
  readonly settled: Settlement | null;
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
function isNumericPanelArm(value: unknown): value is NumericPanelArm {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 1;
}
function parseArm(role: string, value: unknown): NumericPanelArm {
  if (!isNumericPanelArm(value))
    throw new UserError("arm must be a positive one-based integer");
  if (roleContract.panelRoles.includes(role)) return value;
  if (!roleContract.singleRoles.includes(role))
    throw new UserError("unknown delegation role");
  if (value !== 1) throw new UserError("single-value roles require arm 1");
  return value;
}
function isConcreteExecutionIdentity(value: string): value is ConcreteExecutionIdentity {
  return !roleContract.unresolvedAliases.includes(value.trim());
}
function concreteIdentity(value: unknown): ConcreteExecutionIdentity {
  const identity = text(value);
  if (!isConcreteExecutionIdentity(identity))
    throw new UserError("execution identity must be concrete");
  return identity;
}
function parseResolutionContext(
  value: unknown,
  role: string,
  arm: NumericPanelArm,
): ResolutionContext {
  const row = record(value);
  if (row.workModel !== null && typeof row.workModel !== "string")
    throw new UserError("resolutionContext workModel must be a string or null");
  const resolved = record(row.resolvedArm);
  if (resolved.role !== role || resolved.arm !== arm)
    throw new UserError("resolutionContext role and arm must match the attempt");
  if (
    resolved.step !== undefined && resolved.step !== "up" &&
    resolved.step !== "down" && resolved.step !== "same-model"
  )
    throw new UserError("invalid canonical reviewer step");
  return {
    workModel: row.workModel,
    resolvedArm: {
      role,
      arm,
      model: text(resolved.model),
      effort: text(resolved.effort),
      source: text(resolved.source),
      ...(resolved.notes === undefined ? {} : { notes: array(resolved.notes).map(text) }),
      ...(resolved.step === undefined ? {} : { step: resolved.step }),
    },
  };
}
export function parseBeginAttempt(value: unknown): BeginAttempt {
  const row = record(value);
  const resolution = record(row.resolution);
  const harness = text(resolution.harness);
  if (!roleContract.harnesses.includes(harness))
    throw new UserError("unknown execution harness");
  const role = text(row.role);
  if (row.authority !== "worker" && row.authority !== "verifier")
    throw new UserError("authority must be worker or verifier");
  const unit = text(row.unit);
  const arm = parseArm(role, row.arm);
  const checkout = text(row.checkout);
  if (!isAbsolute(checkout))
    throw new UserError("checkout must be an absolute path");
  return {
    unit,
    role,
    arm,
    authority: row.authority,
    requestId: text(row.requestId),
    ...(row.replace === undefined ? {} : { replace: safeId(row.replace) }),
    brief: text(row.brief),
    checkout,
    resolution: {
      harness,
      model: concreteIdentity(resolution.model),
      effort: concreteIdentity(resolution.effort),
    },
    ...(row.resolutionContext === undefined
      ? {}
      : { resolutionContext: parseResolutionContext(row.resolutionContext, role, arm) }),
  };
}
export function parseAttempt(value: unknown): Attempt {
  const row = record(value);
  const target = record(row.target);
  if (
    typeof target.pr !== "string" ||
    typeof target.sha !== "string"
  )
    throw new UserError("invalid saved attempt");
  return {
    ...parseBeginAttempt(row),
    id: safeId(row.id),
    binding: row.binding === undefined ? safeId(row.id) : safeId(row.binding),
    target: { pr: target.pr, sha: target.sha },
    observation: parseObservation(row.observation),
    settled: parseSettlement(row.settled),
  };
}
function parseSettlement(value: unknown): Settlement | null {
  if (value === null) return null;
  if (typeof value === "string")
    return { kind: "finished", reason: disposition(value) };
  const row = record(value);
  if (row.kind === "accepted") return { kind: "accepted", at: text(row.at) };
  if (row.kind === "finished")
    return { kind: "finished", reason: disposition(row.reason) };
  throw new UserError("invalid attempt settlement");
}
function disposition(value: unknown): string {
  if (typeof value !== "string" || value.trim().length === 0 || /[\r\n]/.test(value))
    throw new UserError("invalid terminal disposition");
  return value;
}
export function parseCompletionBinding(value: unknown): CompletionBinding {
  const row = record(value);
  if (typeof row.pr !== "string" || typeof row.sha !== "string")
    throw new UserError("invalid completion head");
  if (row.pr !== "") {
    if (!/^[1-9]\d*$/.test(row.pr)) throw new UserError("invalid completion PR");
    integer(Number(row.pr));
  }
  if (row.sha !== "") text(row.sha);
  return { binding: safeId(row.binding), pr: row.pr, sha: row.sha };
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
