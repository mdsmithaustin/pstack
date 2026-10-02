import {
  exitCodeOf,
  type GateReport,
  type MergeGateResult,
} from "./merge-gate.ts";

interface Stamp {
  readonly observedAt: string;
}

export const renderJson = (result: MergeGateResult, stamp: Stamp): string =>
  `${JSON.stringify({
    schemaVersion: 1,
    observedAt: stamp.observedAt,
    exitCode: exitCodeOf(result),
    ...result,
  })}\n`;

function reportLines(report: GateReport): readonly string[] {
  return report.gates.map(
    (result) => `${result.ok ? "ok  " : "FAIL"} ${result.gate}: ${result.detail}`
  );
}
const headline = (label: string, report: GateReport): string =>
  `${label}: pr=#${report.pr.number} ${report.ready ? "READY" : "NOT READY"} head=${report.headSha ?? "unknown"}`;

export function renderPretty(result: MergeGateResult): string {
  switch (result.kind) {
    case "CHECK":
      return `${[headline("CHECK", result.report), ...reportLines(result.report)].join("\n")}\n`;
    case "REFUSED":
      return `${[
        headline("REFUSED", result.report),
        ...reportLines(result.report),
        ...(result.note === null ? [] : [`note: ${result.note}`]),
      ].join("\n")}\n`;
    case "MERGED": {
      const failed = result.report.gates
        .filter((gate) => !gate.ok)
        .map((gate) => gate.gate);
      return `${[
        `MERGED: pr=#${result.receipt.pr}`,
        `commit=${result.receipt.mergeCommit ?? "unknown"}`,
        `head=${result.receipt.head}`,
        `patch-id=${result.receipt.patchId ?? "unknown"}`,
        `verdict=${result.receipt.verdictUrl ?? "none"}`,
        ...(result.override === null
          ? []
          : [`overridden=${JSON.stringify(result.override)}`, `failed=${failed.join(",")}`]),
      ].join(" ")}\n`;
    }
    case "ERROR":
      return `ERROR: ${result.source}: ${result.detail}\n`;
    default: {
      const exhaustive: never = result;
      return exhaustive;
    }
  }
}
