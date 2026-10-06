export class UserError extends Error {}

export type Verdict =
  | "live-ui-verified"
  | "unit-test-verified"
  | "type-check-only"
  | "verifier-blocked"
  | "verifier-failed";

export function verdictOrNull(value: string): Verdict | null {
  switch (value) {
    case "live-ui-verified":
    case "unit-test-verified":
    case "type-check-only":
    case "verifier-blocked":
    case "verifier-failed":
      return value;
    default:
      return null;
  }
}

export function parseVerdict(value: string): Verdict {
  const verdict = verdictOrNull(value);
  if (verdict === null) {
    throw new UserError(
      "verdict must be live-ui-verified, unit-test-verified, type-check-only, verifier-blocked, or verifier-failed"
    );
  }
  return verdict;
}
