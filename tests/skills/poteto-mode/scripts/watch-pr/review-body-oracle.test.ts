import { describe, expect, it } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { SUMMARY, flags, rendersSummary, summaryBodies } from "./review-body-oracle.test-helper.ts";

describe("counted summaries that GitHub's renderer shows", () => {
  it("reads the oracle's two outcomes from cmark-gfm", () => {
    expect(rendersSummary(`text\n\n${SUMMARY}`)).toBe(true);
    expect(rendersSummary(`\`\`\`\n${SUMMARY}\n\`\`\``)).toBe(false);
  });

  it("flags every generated body whose counted summary cmark-gfm renders as HTML", () => {
    let shown = 0;
    let masked = 0;
    const missed: string[] = [];
    for (const body of summaryBodies()) {
      const flagged = flags(body);
      if (rendersSummary(body)) {
        shown++;
        if (!flagged) missed.push(body);
      } else if (!flagged) masked++;
    }
    expect(missed.slice(0, 5)).toEqual([]);
    expect(shown).toBeGreaterThan(100_000);
    expect(masked).toBeGreaterThan(10_000);
  }, 60_000);

  const recorded: readonly { readonly source: string; readonly body: string; readonly shown: boolean }[] =
    JSON.parse(readFileSync(join(import.meta.dir, "fixtures", "github-render-calibration.json"), "utf8"));
  const shown = recorded.filter((row) => row.shown);

  it("flags every recorded body whose counted summary GitHub's renderer showed", () => {
    expect(shown.filter((row) => !flags(row.body)).map((row) => row.body)).toEqual([]);
    expect(shown.length).toBeGreaterThan(50);
    expect(recorded.length - shown.length).toBeGreaterThan(50);
  });

  it("sees every summary GitHub showed among recorded bodies drawn from the generated corpus", () => {
    const corpus = shown.filter((row) => row.source === "corpus");
    expect(corpus.filter((row) => !rendersSummary(row.body)).map((row) => row.body)).toEqual([]);
    expect(corpus.length).toBeGreaterThan(50);
  });
});
