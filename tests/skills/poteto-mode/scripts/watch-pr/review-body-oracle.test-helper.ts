import { readFileSync } from "node:fs";
import { init, render } from "gfm-wasm";
import * as github from "../../../../../skills/poteto-mode/scripts/watch-pr/github.ts";
import { botReview, reviewBodiesResponse } from "./review-fixtures.test-helper.ts";

await init(readFileSync(new URL(import.meta.resolve("gfm-wasm/wasm"))));

export const SUMMARY = "<summary><strong>Previously missed (1)</strong></summary>";

// gfm-wasm runs cmark-gfm, GitHub's renderer, in safe mode, which drops raw HTML rather
// than escape it. A summary rendered as HTML therefore leaves no escaped copy, while one
// rendered as code or text does. A link reference definition renders nothing either, and
// gfm-wasm enables no footnotes, so `[^1]: x` parses as one; the corpus keeps the summary
// out of both.
export const rendersSummary = (body: string): boolean =>
  !render(body).includes("&lt;summary&gt;");

type ReviewStateApi = Pick<typeof github, "buildReviewState" | "parseReviewStatePage">;
export const findings = (body: string, api: ReviewStateApi = github): unknown =>
  api
    .buildReviewState([
      api.parseReviewStatePage(
        reviewBodiesResponse({
          headRefOid: "head",
          reviews: [botReview({ id: 1, commit: "head", body })],
        })
      ),
    ])
    .flaggedReviews.map((review) => review.findings);
export const flags = (body: string, api: ReviewStateApi = github): boolean =>
  JSON.stringify(findings(body, api)) !== "[]";

const LINES = [
  "", "text", "`", "``", "\\`", "x`", "`x`", "<br>", "<div>", "<span>", "<pre>", "</pre>",
  "<!--", "<!-- c -->", "-->", "<?x", "?>", "<!X", "x>", "<![CDATA[", "]]>", "<!doctype",
  "<source>", "<search>", "```", "```js", "~~~", "````", "``` x`y", " ```", "   ```", "    ```",
  "\t```", "- ```", "1. ~~~", "> ```", "  - ```", "- - -", "* * *", "===", "---", "# h",
  "| a | b |", "|---|---|", "http://x`", "www.x`", "- text", "> text", "    text", "-",
  "- <pre>", "> <!--", "- <div>", "1) x", "-\t<pre>", "1. <pre>", "<script>", "<style>",
  "<textarea>", "<PRE>", "<pre x", "<pre></b>", "<!-- ->", "<?x>", "<![CDATA[ ]>", "```\t", "\u00a0",
  "a `b", "~~",
];
const SUMMARY_LINES = [
  SUMMARY, ` ${SUMMARY}`, `    ${SUMMARY}`, `- ${SUMMARY}`, `> ${SUMMARY}`, `1. ${SUMMARY}`,
  `\t${SUMMARY}`, `\`${SUMMARY}\``, `x \`${SUMMARY}\` y`, `\`\`${SUMMARY}\`\``, `- \`${SUMMARY}\``,
  `> \`${SUMMARY}\``, `\`x ${SUMMARY}`, `${SUMMARY}\``, `\\\`${SUMMARY}\``, `\`\`x\` ${SUMMARY} \`y`,
  `| \`x | ${SUMMARY} | y\` |`, `http://x/\`${SUMMARY}\``, `www.x\`${SUMMARY}\``, `<br>\`${SUMMARY}\``,
  `a:\`${SUMMARY}\``, `\`\` \` ${SUMMARY} \` \`\``, `  \`${SUMMARY}\``, `    \`${SUMMARY}\``,
  `\`\` ${SUMMARY} \`x\``, `\`x\`\` ${SUMMARY} \``, `\`${SUMMARY}\`\``,
];

function* random(count: number, seed: number): Generator<string> {
  let state = seed;
  const pick = <T>(items: readonly T[]): T => {
    state = (Math.imul(state, 1103515245) + 12345) >>> 0;
    return items[(state >>> 16) % items.length];
  };
  for (let n = 0; n < count; n++) {
    const lines = Array.from({ length: 3 + (n % 4) }, () => pick(LINES));
    lines.splice(n % (lines.length + 1), 0, pick(SUMMARY_LINES));
    yield lines.join("\n");
  }
}

function* contexts(depth: number): Generator<string[]> {
  if (depth === 0) yield [];
  else for (const rest of contexts(depth - 1)) for (const line of LINES) yield [line, ...rest];
}

export function* summaryBodies(depth = 2): Generator<string> {
  for (const summary of SUMMARY_LINES)
    for (const lines of contexts(depth))
      for (let at = 0; at <= depth; at++) yield lines.toSpliced(at, 0, summary).join("\n");
  yield* random(100_000, 361);
}
