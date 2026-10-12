import { describe, expect, it } from "bun:test";
import { failRounds, latestVerdict } from "../../../../../skills/poteto-mode/scripts/watch-pr/verdict.ts";
import {
  HEAD,
  MOVED_HEAD,
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

describe("failRounds", () => {
  const head = (digit: string) => digit.repeat(40);
  const fail = (digit: string, createdAt: string, extra = {}) =>
    issueComment({
      createdAt,
      body: verdictBody({ verdict: "FAIL", head: head(digit) }),
      ...extra,
    });
  const count = (comments: Parameters<typeof failRounds>[0]) =>
    failRounds(comments, PR_AUTHOR).count;

  it("counts one FAIL block per distinct Head, whatever the array order", () => {
    const rounds = [
      fail("a", "2026-10-02T10:00:00Z"),
      fail("b", "2026-10-02T11:00:00Z"),
      fail("c", "2026-10-02T12:00:00Z"),
    ];
    expect(count(rounds)).toBe(3);
    expect(count([...rounds].reverse())).toBe(3);
  });

  it("counts a second FAIL at the same Head once", () => {
    expect(
      count([
        fail("a", "2026-10-02T10:00:00Z"),
        fail("a", "2026-10-02T11:00:00Z"),
      ])
    ).toBe(1);
  });

  it("ignores PASS and PASS+NOTES blocks", () => {
    expect(
      count([
        issueComment({ body: verdictBody({ verdict: "PASS", head: head("a") }) }),
        issueComment({
          body: verdictBody({ verdict: "PASS+NOTES", head: head("b") }),
        }),
        fail("c", "2026-10-02T12:00:00Z"),
      ])
    ).toBe(1);
  });

  it("counts a malformed FAIL claim, by its Head when it parses and on its own when not", () => {
    expect(
      count([
        fail("a", "2026-10-02T10:00:00Z"),
        issueComment({ body: `Verdict: FAIL\nHead: ${head("a")}` }),
        issueComment({
          body: verdictBody({ verdict: "FAIL", head: head("b"), docs: "PASS" }),
        }),
        issueComment({
          body: verdictBody({ verdict: "FAIL", head: head("d").toUpperCase() }),
        }),
        issueComment({ body: "Verdict: FAIL" }),
      ])
    ).toBe(4);
  });

  it("counts a claim whose word is neither PASS nor PASS+NOTES as a FAIL", () => {
    expect(
      count(
        ["pass", "fail", "", "PASS (with notes)"].map((word, index) =>
          issueComment({
            body: verdictBody({ verdict: "PASS", head: head(String(index)) }).replace(
              "Verdict: PASS",
              `Verdict: ${word}`
            ),
          })
        )
      )
    ).toBe(4);
  });

  it("counts nothing for a PASS or PASS+NOTES claim, even a malformed one", () => {
    expect(
      count([
        issueComment({ body: `Verdict: PASS\nHead: ${head("a")}` }),
        issueComment({
          body: verdictBody({ verdict: "PASS+NOTES", head: head("b"), docs: "PASS" }),
        }),
      ])
    ).toBe(0);
  });

  it("counts nothing for quoted or decorated blocks", () => {
    expect(
      count([
        issueComment({
          body: `Earlier round:\n\n${verdictBody({ verdict: "FAIL", head: head("b") })}`,
        }),
        issueComment({
          body: verdictBody({ verdict: "FAIL", head: head("c") }).replace(
            "Verdict: FAIL",
            "**Verdict: FAIL**"
          ),
        }),
      ])
    ).toBe(0);
  });

  it("counts nothing from an untrusted commenter or a bot", () => {
    const forged = fail("a", "2026-10-02T10:00:00Z", {
      login: "drive-by",
      association: "untrusted",
    });
    const bot = {
      ...fail("b", "2026-10-02T11:00:00Z"),
      author: { login: "some-app", isBot: true },
    };
    expect(count([forged, bot])).toBe(0);
  });

  it("counts a FAIL from the PR author and from a trusted association", () => {
    expect(
      count([
        fail("a", "2026-10-02T10:00:00Z", {
          login: PR_AUTHOR,
          association: "untrusted",
        }),
        fail("b", "2026-10-02T11:00:00Z", {
          login: "reviewer-agent",
          association: "COLLABORATOR",
        }),
      ])
    ).toBe(2);
  });

  describe("state", () => {
    const state = (comments: Parameters<typeof failRounds>[0]) =>
      failRounds(comments, PR_AUTHOR).state;
    const marker = (createdAt: string, body: string, extra = {}) =>
      issueComment({ createdAt, body, ...extra });
    const reset = (createdAt: string, body = "Fail-count reset: operator allowed one more round") =>
      marker(createdAt, body);
    const stopped = (createdAt: string, body = "Stopped: open findings filed as #301, #302") =>
      marker(createdAt, body);
    const askOnly = (digit: string, createdAt: string) =>
      issueComment({
        createdAt,
        body: verdictBody({
          verdict: "FAIL",
          head: head(digit),
          prose: "Operator ask: open",
        }),
      });
    const rounds = [
      fail("a", "2026-10-02T10:00:00Z"),
      fail("b", "2026-10-02T11:00:00Z"),
      fail("c", "2026-10-02T12:00:00Z"),
    ];

    it("stays open below three counted FAIL rounds and stops at the third", () => {
      expect(state([])).toBe("open");
      expect(state(rounds.slice(0, 2))).toBe("open");
      expect(state(rounds)).toBe("stop");
      expect(state([...rounds].reverse())).toBe("stop");
    });

    it("stops at a third round whose FAIL block is malformed", () => {
      const slipped = (digit: string, createdAt: string) =>
        issueComment({
          createdAt,
          body: verdictBody({ verdict: "FAIL", head: head(digit), docs: "PASS" }),
        });
      expect(
        failRounds([...rounds.slice(0, 2), slipped("c", "2026-10-02T12:00:00Z")], PR_AUTHOR)
      ).toEqual({ count: 3, state: "stop" });
      const everyRoundSlipped = "abcdef"
        .split("")
        .map((digit, index) => slipped(digit, `2026-10-02T1${index}:00:00Z`));
      expect(failRounds(everyRoundSlipped, PR_AUTHOR)).toEqual({ count: 6, state: "stop" });
    });

    it("grants exactly one more round after a reset: the next FAIL stops", () => {
      expect(state([...rounds, reset("2026-10-02T12:30:00Z")])).toBe("open");
      const once = [...rounds, reset("2026-10-02T12:30:00Z"), fail("d", "2026-10-02T13:00:00Z")];
      expect(state(once)).toBe("stop");
      expect(failRounds(once, PR_AUTHOR)).toEqual({ count: 4, state: "stop" });
    });

    it("grants one round per reset, newest first", () => {
      const twice = [
        ...rounds,
        reset("2026-10-02T12:30:00Z"),
        fail("d", "2026-10-02T13:00:00Z"),
        stopped("2026-10-02T13:10:00Z"),
        reset("2026-10-02T13:30:00Z"),
      ];
      expect(state(twice)).toBe("open");
      expect(state([...twice, fail("e", "2026-10-02T14:00:00Z")])).toBe("stop");
    });

    it("holds a stop until the next reset, even below three heads", () => {
      const early = [fail("a", "2026-10-02T10:00:00Z"), reset("2026-10-02T10:30:00Z"), fail("b", "2026-10-02T11:00:00Z")];
      expect(failRounds(early, PR_AUTHOR)).toEqual({ count: 2, state: "stop" });
      expect(state([...early, fail("b", "2026-10-02T11:30:00Z")])).toBe("stop");
      expect(
        state([...early, stopped("2026-10-02T11:10:00Z"), fail("b", "2026-10-02T11:30:00Z")])
      ).toBe("stop");
    });

    it("orders a FAIL in the same second as a reset after it, so a tie stops", () => {
      expect(
        state([...rounds.slice(0, 2), fail("c", "2026-10-02T12:30:00Z"), reset("2026-10-02T12:30:00Z")])
      ).toBe("stop");
    });

    it("ignores a reset from an untrusted commenter or a bot", () => {
      const forged = marker("2026-10-02T12:30:00Z", "Fail-count reset: please", {
        login: "drive-by",
        association: "untrusted",
      });
      const bot = { ...reset("2026-10-02T12:40:00Z"), author: { login: "some-app", isBot: true } };
      expect(state([...rounds, forged, bot])).toBe("stop");
    });

    it("ignores a reset with no reason, a quoted reset, and a decorated one", () => {
      for (const body of [
        "Fail-count reset:",
        "Fail-count reset:   ",
        "Noting that\nFail-count reset: later",
        "**Fail-count reset: now**",
        "fail-count reset: now",
      ])
        expect(state([...rounds, reset("2026-10-02T12:30:00Z", body)])).toBe("stop");
    });

    it("reads a reset whose reason is followed by prose, after leading blank lines", () => {
      expect(
        state([...rounds, reset("2026-10-02T12:30:00Z", "\n\nFail-count reset: operator go\n\nBecause.")])
      ).toBe("open");
    });

    it("reads a trusted Stopped: comment newer than every FAIL as stopped", () => {
      expect(state([...rounds, stopped("2026-10-02T12:30:00Z")])).toBe("stopped");
      expect(state([...rounds, stopped("2026-10-02T12:30:00Z", "\nStopped:\n\n- #301")])).toBe(
        "stopped"
      );
    });

    it("stops again on a FAIL newer than the Stopped: comment", () => {
      expect(
        state([...rounds, stopped("2026-10-02T12:30:00Z"), fail("d", "2026-10-02T13:00:00Z")])
      ).toBe("stop");
    });

    it("orders a FAIL in the same second as Stopped: after it, so a tie stops", () => {
      expect(
        state([...rounds.slice(0, 2), fail("c", "2026-10-02T12:30:00Z"), stopped("2026-10-02T12:30:00Z")])
      ).toBe("stop");
    });

    it("lets a newer reset supersede Stopped:, and keeps Stopped: on a same-second tie", () => {
      expect(state([...rounds, stopped("2026-10-02T12:30:00Z"), reset("2026-10-02T12:40:00Z")])).toBe(
        "open"
      );
      expect(state([...rounds, stopped("2026-10-02T12:30:00Z"), reset("2026-10-02T12:30:00Z")])).toBe(
        "stopped"
      );
    });

    it("ignores a Stopped: comment from an untrusted commenter, quoted, or decorated", () => {
      const forged = marker("2026-10-02T12:30:00Z", "Stopped: by a drive-by", {
        login: "drive-by",
        association: "untrusted",
      });
      expect(state([...rounds, forged])).toBe("stop");
      for (const body of ["Earlier:\nStopped: x", "**Stopped:** x", "stopped: x", "> Stopped: x"])
        expect(state([...rounds, stopped("2026-10-02T12:30:00Z", body)])).toBe("stop");
    });

    it("skips a FAIL marked Operator ask: open, in the count and the stop", () => {
      const asked = [...rounds.slice(0, 2), askOnly("c", "2026-10-02T12:00:00Z")];
      expect(failRounds(asked, PR_AUTHOR)).toEqual({ count: 2, state: "open" });
      expect(
        state([...rounds, reset("2026-10-02T12:30:00Z"), askOnly("d", "2026-10-02T13:00:00Z")])
      ).toBe("open");
    });

    it("counts the third FAIL with the retired Security ask marker", () => {
      const third = issueComment({
        createdAt: "2026-10-02T12:00:00Z",
        body: verdictBody({
          verdict: "FAIL",
          head: head("c"),
          prose: "Security ask: open",
        }),
      });
      expect(failRounds([...rounds.slice(0, 2), third], PR_AUTHOR)).toEqual({
        count: 3,
        state: "stop",
      });
    });

    it("counts a FAIL whose Operator ask line is quoted, decorated, or mid-sentence", () => {
      for (const prose of [
        "> Operator ask: open",
        "**Operator ask: open**",
        "The Operator ask: open line is for ask-only rounds.",
      ])
        expect(
          count([
            ...rounds.slice(0, 2),
            issueComment({
              createdAt: "2026-10-02T12:00:00Z",
              body: verdictBody({ verdict: "FAIL", head: head("c"), prose }),
            }),
          ])
        ).toBe(3);
    });
  });

  it("uses a distinct Head even when the patch-id repeats", () => {
    expect(
      count([
        issueComment({
          createdAt: "2026-10-02T10:00:00Z",
          body: verdictBody({ verdict: "FAIL", head: HEAD }),
        }),
        issueComment({
          createdAt: "2026-10-02T11:00:00Z",
          body: verdictBody({ verdict: "FAIL", head: MOVED_HEAD }),
        }),
      ])
    ).toBe(2);
  });
});
