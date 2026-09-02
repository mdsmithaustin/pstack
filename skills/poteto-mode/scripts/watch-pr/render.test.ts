import { describe, expect, it } from "bun:test";
import { renderPretty } from "./render.ts";
import { parsePrNumber } from "./types.ts";
import type * as T from "./types.ts";

const context = {
  owner: "owner",
  repo: "repo",
  number: parsePrNumber(9),
} satisfies T.PrContext;

describe("renderPretty", () => {
  it("prints a thread's bot login and pass count, or bot=none for a human thread", () => {
    const verdict = {
      schemaVersion: 1,
      sequence: 1,
      observedAt: "2026-07-26T00:00:00.000Z",
      mode: "single",
      kind: "BLOCKER",
      terminal: true,
      exitCode: 3,
      blocker: {
        kind: "review-threads",
        pr: context,
        threads: [
          {
            id: "bot-thread",
            firstComment: null,
            bot: { login: "copilot-pull-request-reviewer", passes: 2 },
          },
          {
            id: "human-thread",
            firstComment: null,
            bot: null,
          },
        ],
      },
    } satisfies Extract<T.TerminalVerdict, { kind: "BLOCKER" }>;
    const text = renderPretty(verdict);
    expect(text).toContain("bot=copilot-pull-request-reviewer passes=2");
    expect(text).toContain("bot=none");
  });

  it("reports pending review bots while waiting", () => {
    const verdict = {
      schemaVersion: 1,
      sequence: 1,
      observedAt: "2026-07-26T00:00:00.000Z",
      mode: "single",
      kind: "WAITING",
      terminal: false,
      frontier: context,
      reason: {
        kind: "pending-review-bots",
        bots: ["copilot-pull-request-reviewer"],
      },
    } satisfies Extract<T.ProgressVerdict, { kind: "WAITING" }>;
    expect(renderPretty(verdict)).toBe(
      "WAITING: frontier=#9; review bot(s) pending: copilot-pull-request-reviewer\n"
    );
  });

  it("reports pending review bots on timeout", () => {
    const verdict = {
      schemaVersion: 1,
      sequence: 1,
      observedAt: "2026-07-26T00:00:00.000Z",
      mode: "single",
      kind: "TIMEOUT",
      terminal: true,
      exitCode: 5,
      reason: {
        kind: "pending-review-bots",
        bots: ["copilot-pull-request-reviewer"],
      },
    } satisfies T.TimeoutVerdict;
    expect(renderPretty(verdict)).toBe("TIMEOUT: review bots still pending\n");
  });
});
