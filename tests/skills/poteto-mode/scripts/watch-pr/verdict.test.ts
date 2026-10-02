import { describe, expect, it } from "bun:test";
import { latestVerdict } from "../../../../../skills/poteto-mode/scripts/watch-pr/verdict.ts";
import {
  HEAD,
  PATCH,
  issueComment,
  verdictBody,
} from "./merge-gate-fakes.test-helper.ts";

const PR_AUTHOR = "mdsmithaustin";
const read = (comments: Parameters<typeof latestVerdict>[0]) =>
  latestVerdict(comments, PR_AUTHOR);

describe("latestVerdict", () => {
  it("reads a block at the top of the comment, with prose after it and blank lines before it", () => {
    const reading = read([
      issueComment({
        url: "https://github.com/owner/repo/pull/1#issuecomment-9",
        login: "reviewer-agent",
        createdAt: "2026-10-02T11:00:00Z",
        body: `\n  \n${verdictBody({ verdict: "PASS+NOTES", docs: "n/a" })}`,
      }),
    ]);
    expect(reading).toEqual({
      kind: "recorded",
      record: {
        verdict: "PASS+NOTES",
        head: HEAD,
        patchId: PATCH,
        docs: "n/a",
        url: "https://github.com/owner/repo/pull/1#issuecomment-9",
        createdAt: "2026-10-02T11:00:00Z",
        author: "reviewer-agent",
      },
    });
  });

  it("reports absent when no comment carries a verdict line", () => {
    expect(
      read([
        issueComment({ body: "Read Copilot's review body, all fixed." }),
      ])
    ).toEqual({ kind: "absent" });
    expect(read([])).toEqual({ kind: "absent" });
  });

  it("lets the latest verdict by createdAt win, whatever the array order", () => {
    const pass = issueComment({
      createdAt: "2026-10-02T11:00:00Z",
      body: verdictBody({ verdict: "PASS" }),
    });
    const fail = issueComment({
      createdAt: "2026-10-02T12:00:00Z",
      body: verdictBody({ verdict: "FAIL" }),
    });
    const winner = (comments: Parameters<typeof latestVerdict>[0]) => {
      const reading = read(comments);
      return reading.kind === "recorded" ? reading.record.verdict : reading.kind;
    };
    expect(winner([pass, fail])).toBe("FAIL");
    expect(winner([fail, pass])).toBe("FAIL");
    const rescinded = issueComment({
      createdAt: "2026-10-02T13:00:00Z",
      body: verdictBody({ verdict: "PASS+NOTES" }),
    });
    expect(winner([pass, fail, rescinded])).toBe("PASS+NOTES");
  });

  it("accepts every documented Docs status", () => {
    for (const docs of ["pass", "needs changes", "unverified", "n/a"] as const) {
      const reading = read([
        issueComment({ body: verdictBody({ docs }) }),
      ]);
      expect(reading.kind === "recorded" ? reading.record.docs : reading.kind).toBe(
        docs
      );
    }
  });

  it("accepts CRLF line endings", () => {
    const reading = read([
      issueComment({ body: verdictBody().replaceAll("\n", "\r\n") }),
    ]);
    expect(reading.kind).toBe("recorded");
  });

  it("fails closed, naming the position, when a block line is missing", () => {
    const full = verdictBody().split("\n");
    for (const [key, position] of [
      ["Head", 2],
      ["Patch-id", 3],
      ["Docs", 4],
    ] as const) {
      const body = full.filter((line) => !line.startsWith(`${key}:`)).join("\n");
      const reading = read([issueComment({ body })]);
      expect(reading.kind).toBe("malformed");
      expect(reading.kind === "malformed" ? reading.problems[0] : "").toBe(
        `expected "${key}:" as non-empty line ${position}`
      );
    }
    const withoutVerdict = full.filter((line) => !line.startsWith("Verdict:")).join("\n");
    expect(read([issueComment({ body: withoutVerdict })])).toEqual({ kind: "absent" });
  });

  it("names every missing line of a comment that stops early", () => {
    expect(read([issueComment({ body: "Verdict: PASS" })])).toMatchObject({
      kind: "malformed",
      problems: ['missing "Head:" line', 'missing "Patch-id:" line', 'missing "Docs:" line'],
    });
  });

  it("ignores a block quoted later in a trusted comment: not a verdict, not malformed", () => {
    const quoted = issueComment({
      createdAt: "2026-10-02T12:00:00Z",
      body: `Re-running the review. The old verdict was:\n\n${verdictBody({ verdict: "PASS" })}`,
    });
    expect(read([quoted])).toEqual({ kind: "absent" });
    const trustedFail = issueComment({
      createdAt: "2026-10-02T11:00:00Z",
      body: verdictBody({ verdict: "FAIL" }),
    });
    const reading = read([trustedFail, quoted]);
    expect(reading.kind === "recorded" ? reading.record.verdict : reading.kind).toBe("FAIL");
  });

  it("ignores a half-quoted block later in a trusted comment instead of failing closed", () => {
    const trustedPass = issueComment({
      createdAt: "2026-10-02T11:00:00Z",
      body: verdictBody({ verdict: "PASS" }),
    });
    const mention = issueComment({
      createdAt: "2026-10-02T12:00:00Z",
      body: "See above.\nVerdict: FAIL\nHead: abc",
    });
    expect(read([trustedPass, mention]).kind).toBe("recorded");
  });

  it("rejects values outside the grammar", () => {
    const cases: readonly [Parameters<typeof verdictBody>[0], string][] = [
      [{ verdict: "LGTM" }, 'invalid "Verdict:" value "LGTM"'],
      [{ verdict: "pass" }, 'invalid "Verdict:" value "pass"'],
      [{ head: "a1b2c3" }, 'invalid "Head:" value "a1b2c3"'],
      [{ head: "A1".repeat(20) }, `invalid "Head:" value "${"A1".repeat(20)}"`],
      [{ patchId: "z".repeat(40) }, `invalid "Patch-id:" value "${"z".repeat(40)}"`],
      [{ docs: "fine" }, 'invalid "Docs:" value "fine"'],
    ];
    for (const [args, problem] of cases) {
      const reading = read([
        issueComment({ body: verdictBody(args) }),
      ]);
      expect(reading).toMatchObject({ kind: "malformed", problems: [problem] });
    }
  });

  it("refuses a block whose keys repeat or arrive out of order", () => {
    for (const body of [
      `Verdict: PASS\nVerdict: FAIL\nHead: ${HEAD}\nPatch-id: ${PATCH}\nDocs: pass`,
      `Verdict: PASS\nPatch-id: ${PATCH}\nHead: ${HEAD}\nDocs: pass`,
    ])
      expect(read([issueComment({ body })]).kind).toBe("malformed");
  });

  it("does not read keys with other casing or markdown decoration", () => {
    for (const body of [
      verdictBody().replace("Verdict:", "verdict:"),
      verdictBody().replace("Verdict: PASS", "**Verdict: PASS**"),
      verdictBody().replace("Verdict: PASS", "> Verdict: PASS"),
      verdictBody().replace("Verdict: PASS", "  Verdict: PASS"),
    ])
      expect(read([issueComment({ body })])).toEqual({ kind: "absent" });
  });

  it("lets a newer malformed verdict comment hide an older PASS", () => {
    const older = issueComment({
      createdAt: "2026-10-02T11:00:00Z",
      body: verdictBody({ verdict: "PASS" }),
    });
    const newer = issueComment({
      createdAt: "2026-10-02T12:00:00Z",
      url: "https://github.com/owner/repo/pull/1#issuecomment-55",
      body: "Verdict: FAIL\nHead: abc",
    });
    expect(read([older, newer])).toMatchObject({
      kind: "malformed",
      url: "https://github.com/owner/repo/pull/1#issuecomment-55",
    });
  });

  describe("trust", () => {
    const trustedFail = issueComment({
      createdAt: "2026-10-02T11:00:00Z",
      url: "https://github.com/owner/repo/pull/1#issuecomment-71",
      body: verdictBody({ verdict: "FAIL" }),
    });
    const trustedPass = issueComment({
      createdAt: "2026-10-02T11:00:00Z",
      body: verdictBody({ verdict: "PASS" }),
    });

    it("ignores a newer untrusted PASS, so it cannot override a trusted FAIL", () => {
      const forged = issueComment({
        createdAt: "2026-10-02T12:00:00Z",
        login: "drive-by",
        association: "untrusted",
        body: verdictBody({ verdict: "PASS" }),
      });
      const reading = read([trustedFail, forged]);
      expect(
        reading.kind === "recorded"
          ? [reading.record.verdict, reading.record.author]
          : reading.kind
      ).toEqual(["FAIL", "mdsmithaustin"]);
    });

    it("ignores a newer untrusted malformed block, so it cannot fail-close a trusted PASS", () => {
      const noise = issueComment({
        createdAt: "2026-10-02T12:00:00Z",
        login: "drive-by",
        association: "untrusted",
        body: "Verdict: FAIL\nHead: nope",
      });
      expect(read([trustedPass, noise]).kind).toBe("recorded");
    });

    it("reads nothing when only untrusted comments carry a block", () => {
      const forged = issueComment({
        login: "drive-by",
        association: "untrusted",
        body: verdictBody(),
      });
      expect(read([forged])).toEqual({ kind: "absent" });
    });

    it("counts a block from each trusted association", () => {
      for (const association of ["OWNER", "MEMBER", "COLLABORATOR"] as const) {
        const reading = read([
          issueComment({ login: "reviewer-agent", association, body: verdictBody() }),
        ]);
        expect(
          reading.kind === "recorded" ? reading.record.author : reading.kind
        ).toBe("reviewer-agent");
      }
    });

    it("counts the PR author even without a trusted association", () => {
      const reading = read([
        issueComment({ login: PR_AUTHOR, association: "untrusted", body: verdictBody() }),
      ]);
      expect(reading.kind).toBe("recorded");
    });

    it("never trusts a bot, whatever its association", () => {
      const bot = { ...issueComment({ association: "OWNER" }), author: { login: "some-app", isBot: true } };
      expect(read([bot])).toEqual({ kind: "absent" });
    });
  });
});
