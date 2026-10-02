import { describe, expect, it } from "bun:test";
import {
  GATES,
  evaluateGates,
  type GateReport,
} from "../../../../../skills/poteto-mode/scripts/watch-pr/merge-gate.ts";
import { passingCheck, pendingCheck } from "./fakes.test-helper.ts";
import {
  CONTEXT,
  HEAD,
  MOVED_HEAD,
  OTHER_PATCH,
  REVIEW_URL,
  failingChecks,
  issueComment,
  openFlaggedReview,
  unreadReview,
  unresolvedThread,
  verdictBody,
  world,
  type WorldOptions,
} from "./merge-gate-fakes.test-helper.ts";

async function report(options: WorldOptions = {}): Promise<{
  readonly report: GateReport;
  readonly world: ReturnType<typeof world>;
}> {
  const built = world(options);
  return {
    report: await evaluateGates({
      reader: built.reader,
      port: built.port,
      context: CONTEXT,
    }),
    world: built,
  };
}
const failedNames = (gateReport: GateReport): readonly string[] =>
  gateReport.gates.filter((result) => !result.ok).map((result) => result.gate);
const detailOf = (gateReport: GateReport, gate: string): string =>
  gateReport.gates.find((result) => result.gate === gate)?.detail ?? "missing";

describe("evaluateGates", () => {
  it("is ready when every gate holds, and lists all eight gates in order", async () => {
    const { report: ready } = await report();
    expect(ready.ready).toBe(true);
    expect(ready.gates.map((result) => result.gate)).toEqual([...GATES]);
    expect(GATES).toEqual([
      "verdict",
      "head",
      "patch-id",
      "checks",
      "review-bodies",
      "threads",
      "mergeability",
      "draft",
    ]);
    expect(ready.headSha).toBe(HEAD);
    expect(ready.state).toBe("OPEN");
  });

  it("computes the patch-id for the PR base branch and head", async () => {
    const { world: built } = await report({
      facts: { baseRefName: "release/2" },
    });
    expect(built.port.calls).toContainEqual({
      kind: "patch-id",
      baseRef: "release/2",
      headSha: HEAD,
    });
  });

  describe("each gate failing alone", () => {
    it("verdict: no block", async () => {
      const { report: result } = await report({
        port: { comments: [issueComment({ body: "looks good" })] },
      });
      expect(failedNames(result)).toEqual(["verdict", "head", "patch-id"]);
      expect(detailOf(result, "verdict")).toBe("no verdict block");
    });

    it("verdict: FAIL", async () => {
      const { report: result } = await report({
        port: { comments: [issueComment({ body: verdictBody({ verdict: "FAIL" }) })] },
      });
      expect(failedNames(result)).toEqual(["verdict"]);
      expect(detailOf(result, "verdict")).toContain("Verdict: FAIL");
    });

    it("verdict: PASS+NOTES with Docs n/a is accepted", async () => {
      const { report: result } = await report({
        port: {
          comments: [
            issueComment({ body: verdictBody({ verdict: "PASS+NOTES", docs: "n/a" }) }),
          ],
        },
      });
      expect(result.ready).toBe(true);
    });

    it("verdict: Docs needs changes or unverified", async () => {
      for (const docs of ["needs changes", "unverified"]) {
        const { report: result } = await report({
          port: { comments: [issueComment({ body: verdictBody({ docs }) })] },
        });
        expect(failedNames(result)).toEqual(["verdict"]);
        expect(detailOf(result, "verdict")).toContain(`Docs: ${docs}`);
      }
    });

    it("verdict: names the trusted author who wrote it", async () => {
      const { report: ok } = await report({
        port: {
          comments: [issueComment({ login: "reviewer-agent", association: "COLLABORATOR" })],
        },
      });
      expect(detailOf(ok, "verdict")).toContain("by reviewer-agent");
      const { report: bad } = await report({
        port: {
          comments: [
            issueComment({
              login: "reviewer-agent",
              association: "COLLABORATOR",
              body: verdictBody({ verdict: "FAIL" }),
            }),
          ],
        },
      });
      expect(detailOf(bad, "verdict")).toContain("by reviewer-agent");
    });

    it("verdict: an untrusted commenter's PASS does not satisfy the gate", async () => {
      const { report: result } = await report({
        port: {
          comments: [issueComment({ login: "drive-by", association: "untrusted" })],
        },
      });
      expect(detailOf(result, "verdict")).toBe("no verdict block");
    });

    it("verdict: a malformed latest comment names its problem and URL", async () => {
      const { report: result } = await report({
        port: {
          comments: [
            issueComment({
              url: "https://github.com/owner/repo/pull/1#issuecomment-31",
              body: "Verdict: PASS\nHead: nope",
            }),
          ],
        },
      });
      expect(detailOf(result, "verdict")).toContain("malformed");
      expect(detailOf(result, "verdict")).toContain("issuecomment-31");
    });

    it("head: the verdict covers an older head, same patch", async () => {
      const { report: result } = await report({
        facts: { headRefOid: MOVED_HEAD },
      });
      expect(failedNames(result)).toEqual(["head"]);
      expect(detailOf(result, "head")).toBe(
        `verdict covers ${HEAD} but the PR head is ${MOVED_HEAD}`
      );
    });

    it("patch-id: the diff changed", async () => {
      const { report: result } = await report({ port: { patchId: OTHER_PATCH } });
      expect(failedNames(result)).toEqual(["patch-id"]);
      expect(detailOf(result, "patch-id")).toContain(OTHER_PATCH);
    });

    it("checks: a failed check is named", async () => {
      const { report: result } = await report({
        checks: failingChecks,
        rollupState: "FAILURE",
      });
      expect(failedNames(result)).toEqual(["checks"]);
      expect(detailOf(result, "checks")).toContain("unit-tests");
    });

    it("checks: a pending check fails, merge-gate does not wait", async () => {
      const { report: result } = await report({
        checks: { kind: "checks", checks: [passingCheck("a"), pendingCheck("slow-e2e")] },
      });
      expect(failedNames(result)).toEqual(["checks"]);
      expect(detailOf(result, "checks")).toContain("slow-e2e");
      expect(detailOf(result, "checks")).toContain("pending");
    });

    it("review-bodies: an unacknowledged bot review", async () => {
      const { report: result } = await report({
        flaggedReviews: [openFlaggedReview()],
      });
      expect(failedNames(result)).toEqual(["review-bodies"]);
      expect(detailOf(result, "review-bodies")).toContain(REVIEW_URL);
    });

    it("review-bodies: an acknowledged bot review passes", async () => {
      const acknowledged = {
        ...openFlaggedReview(),
        status: "acknowledged",
        ack: { author: "mdsmithaustin", url: "https://x/ack" },
      } as const;
      const { report: result } = await report({ flaggedReviews: [acknowledged] });
      expect(result.ready).toBe(true);
    });

    it("review-bodies: a bot review still pending", async () => {
      const { report: result } = await report({
        pendingBots: ["copilot-pull-request-reviewer"],
      });
      expect(failedNames(result)).toEqual(["review-bodies"]);
      expect(detailOf(result, "review-bodies")).toContain(
        "copilot-pull-request-reviewer"
      );
    });

    it("review-bodies: an unread bot body fails until a trusted comment links it", async () => {
      const unread = unreadReview();
      const open = await report({ unreadReviews: [unread] });
      expect(failedNames(open.report)).toEqual(["review-bodies"]);
      expect(detailOf(open.report, "review-bodies")).toContain(unread.url);
      const acked = await report({
        unreadReviews: [unread],
        port: {
          comments: [
            issueComment(),
            issueComment({ body: `Read ${unread.url}, nothing to fix.` }),
          ],
        },
      });
      expect(acked.report.ready).toBe(true);
    });

    it("threads: an unresolved thread", async () => {
      const { report: result } = await report({ threads: [unresolvedThread()] });
      expect(failedNames(result)).toEqual(["threads"]);
      expect(detailOf(result, "threads")).toContain("1 unresolved");
    });

    it("mergeability: conflicts, unknown, and changes requested", async () => {
      const cases: [WorldOptions["facts"], string][] = [
        [{ mergeable: "CONFLICTING", mergeStateStatus: "DIRTY" }, "conflict"],
        [{ mergeable: "UNKNOWN" }, "not computed"],
        [{ reviewDecision: "CHANGES_REQUESTED" }, "changes requested"],
      ];
      for (const [facts, words] of cases) {
        const { report: result } = await report({ facts });
        expect(failedNames(result)).toEqual(["mergeability"]);
        expect(detailOf(result, "mergeability")).toContain(words);
      }
    });

    it("draft: a draft PR", async () => {
      const { report: result } = await report({ facts: { isDraft: true } });
      expect(failedNames(result)).toEqual(["draft"]);
    });
  });

  it("reports every failing gate together instead of stopping at the first", async () => {
    const { report: result } = await report({
      facts: { mergeable: "CONFLICTING", mergeStateStatus: "DIRTY", isDraft: true },
      checks: failingChecks,
      rollupState: "FAILURE",
      threads: [unresolvedThread()],
      flaggedReviews: [openFlaggedReview()],
      port: { comments: [], patchId: OTHER_PATCH },
    });
    expect(result.ready).toBe(false);
    expect(failedNames(result)).toEqual([...GATES]);
  });

  it("refuses a PR that already merged and does not touch git", async () => {
    const { report: result, world: built } = await report({
      facts: { state: "MERGED", mergedAt: "2026-10-02T16:14:32Z" },
    });
    expect(result.ready).toBe(false);
    expect(result.state).toBe("MERGED");
    expect(detailOf(result, "mergeability")).toBe("PR is MERGED, not open");
    expect(detailOf(result, "checks")).toBe("not evaluated: PR is MERGED");
    expect(detailOf(result, "patch-id")).toBe("not evaluated: PR is MERGED");
    expect(built.port.calls.some((call) => call.kind === "patch-id")).toBe(false);
  });

  it("refuses a PR closed without merging", async () => {
    const { report: result } = await report({ facts: { state: "CLOSED" } });
    expect(detailOf(result, "mergeability")).toBe("PR is CLOSED, not open");
  });
});
