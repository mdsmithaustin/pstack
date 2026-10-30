import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SUMMARY, findings, flags, rendersSummary, summaryBodies } from "./review-body-oracle.test-helper.ts";

const FIXTURE = join(import.meta.dir, "fixtures", "github-render-calibration.json");
const S = SUMMARY;
const SHAPES = [
  `- text\n<br>\n- \`\`\`\n  ${S}`,
  `- ___\n<br>\n- \`\`\`\n  ${S}`,
  `- ___\ntext\n2. \`\`\`\n   ${S}`,
  `\`\n\`${S}\`\n`,
  `Foo\n===\n<br>\n- \`\`\`\n  ${S}`,
  `| a | b |\n|---|---|\n| \`x | ${S} | y\` | z |`,
  `-\n  \n  \`\`\`\n${S}`,
  `http://x/\`${S}\``,
  `www.x\`${S}\``,
  `<a title="\`">${S}<a title="\`">`,
  `<!doctype\n~~~\nx>\n~~~\n\n${S}`,
  `\\\`\`x\` ${S} \`y\``,
  `- * * *\n    ~~~\n  x\n    ~~~\n\n  ${S}`,
  `<!-- a -->\n${S}`,
  `<!-- a\n${S}\n-->`,
  `<!-- a --!>\n${S}\n-->`,
  `<!-- a --!>\n\`\`\`\n\n${S}`,
  `<!-->\n\`\`\`\n\n${S}`,
  `<!--->\n\`\`\`\n\n${S}`,
  `<pre>\n${S}`,
  `<script>\n${S}`,
  `<textarea>\n${S}`,
  `<?x\n\`\`\`\n${S}`,
  `<!X\n\`\`\`\n${S}`,
  `<![CDATA[\n\`\`\`\n${S}`,
  `x[^1]\n\n[^1]: <pre>\n\n    \`${S}\``,
  `x[^>]\n\n[^>]: <!X\n\n    a > b \`${S}\``,
  `\`${S}\`\``,
  `[a](/u "\`") ${S}\``,
  `[](\`)${S}\``,
  `http://x\u00a0\`${S}\``,
  `\`\u2028\`${S}\``,
  `\`\` \`x\` \`${S}\``,
  `a \`b\n \n\`${S}\``,
  `<?x>\n\n\`${S}\``,
  `<script>\n\n\`${S}\``,
  `<style>\n\n\`${S}\``,
  `<textarea>\n\n\`${S}\``,
  `<PRE>\n\n\`${S}\``,
  `<pre x\n\n\`${S}\``,
  `<pre></b>\n\n\`${S}\``,
  `<![CDATA[ ]>\n\n\`${S}\``,
  `-\t<pre>\n\n    \`${S}\``,
  `1. <pre>\n\n   \`${S}\``,
  `> <pre>\n>\n> \`${S}\``,
  `\`\`\`\nx\n\`\`\`\t\n${S}`,
  `\`\`\`\nx\n   \`\`\`\n${S}`,
  `\`\`\`\nx\n\`\`\`\`\n${S}`,
  `\`\` ${S} \`x\``,
  `\`x\`\` ${S} \``,
  `\`\`\`\n${S}\n\`\`\``,
  `Example:\n~~~\n${S}\n~~~`,
  `Quote \`${S}\` here.`,
  `- Quote \`${S}\` in a list.`,
  `\`\`x\` ${S} \`y`,
];

function githubShows(body: string): boolean {
  const html = execFileSync("gh", ["api", "markdown", "-f", "mode=gfm", "-f", `text=${body}`], { encoding: "utf8" });
  return /<summary>\s*<strong>Previously missed \(1\)<\/strong>\s*<\/summary>/.test(html);
}

function calibrate(): void {
  const corpus = [...summaryBodies()].filter((_, n) => n % 3000 === 0);
  const rows = [
    ...SHAPES.map((body) => ({ source: "shape", body })),
    ...corpus.map((body) => ({ source: "corpus", body })),
  ].map((row) => ({ ...row, shown: githubShows(row.body) }));
  writeFileSync(FIXTURE, `${JSON.stringify(rows, null, 1)}\n`);
  console.log(`${rows.length} bodies, ${rows.filter((row) => row.shown).length} shown`);
}

function fetchReviews(repo: string, out: string): void {
  const gh = <T>(path: string): T[] =>
    JSON.parse(execFileSync("gh", ["api", "--paginate", "--slurp", path], { encoding: "utf8", maxBuffer: 1 << 28 })).flat();
  const pulls = gh<{ number: number }>(`repos/${repo}/pulls?state=all&per_page=100`);
  const rows = pulls.flatMap((pull) =>
    gh<{ id: number; html_url: string; body: string; user: { login: string; type: string } }>(
      `repos/${repo}/pulls/${pull.number}/reviews?per_page=100`
    )
      .filter((review) => review.user.type === "Bot" && review.body !== "")
      .map((review) => ({ pr: pull.number, id: review.id, url: review.html_url, login: review.user.login, body: review.body }))
  );
  writeFileSync(out, JSON.stringify(rows));
  console.log(`${rows.length} bot review bodies from ${pulls.length} pull requests`);
}

async function compare(base: string, reviewsPath: string | undefined, depth: number): Promise<number> {
  const root = execFileSync("git", ["rev-parse", "--show-toplevel"], { encoding: "utf8" }).trim();
  const dir = mkdtempSync(join(tmpdir(), "review-body-base-"));
  execFileSync("sh", ["-c", `git -C "$1" archive "$2" skills/poteto-mode/scripts/watch-pr | tar -x -C "$3"`, "sh", root, base, dir]);
  const baseApi = await import(join(dir, "skills/poteto-mode/scripts/watch-pr/github.ts"));
  rmSync(dir, { recursive: true });
  const tally = (name: string, rows: Iterable<{ body: string; shown: boolean }>): boolean => {
    const count = { bodies: 0, shown: 0, headMisses: 0, baseMisses: 0, headFalseBlocks: 0, baseFalseBlocks: 0, headOnlyFlags: 0, baseOnlyFlags: 0 };
    const missed: string[] = [];
    for (const { body, shown } of rows) {
      const head = flags(body);
      const was = flags(body, baseApi);
      count.bodies++;
      if (shown) count.shown++;
      if (shown && !head) missed.push(body);
      if (shown && !was) count.baseMisses++;
      if (!shown && head) count.headFalseBlocks++;
      if (!shown && was) count.baseFalseBlocks++;
      if (head && !was) count.headOnlyFlags++;
      if (was && !head) count.baseOnlyFlags++;
    }
    count.headMisses = missed.length;
    console.log(name, JSON.stringify(count));
    for (const body of missed.slice(0, 5)) console.log("  head misses", JSON.stringify(body));
    return missed.length === 0;
  };
  const generated = function* () {
    for (const body of summaryBodies(depth)) yield { body, shown: rendersSummary(body) };
  };
  const recorded: { body: string; shown: boolean }[] = JSON.parse(readFileSync(FIXTURE, "utf8"));
  const clean = [tally(`generated corpus (depth ${depth}, cmark-gfm oracle)`, generated()), tally("recorded GitHub renders", recorded)];
  if (reviewsPath !== undefined) {
    const reviews: { pr: number; id: number; body: string }[] = JSON.parse(readFileSync(reviewsPath, "utf8"));
    const changed = reviews.flatMap((review) => {
      const [head, was] = [findings(review.body), findings(review.body, baseApi)].map((rows) => JSON.stringify(rows));
      if (head === was) return [];
      const side = was === "[]" ? "head only flags" : head === "[]" ? "base only flags" : "both flag, findings differ";
      return [`  #${review.pr} review ${review.id}: ${side}\n    head ${head}\n    base ${was}`];
    });
    console.log(`real bot reviews: ${reviews.length}, identical ${reviews.length - changed.length}, differ ${changed.length}`);
    for (const line of changed) console.log(line);
  }
  return clean.every(Boolean) ? 0 : 1;
}

const [command, ...args] = process.argv.slice(2);
if (command === "calibrate") calibrate();
else if (command === "fetch" && args[0] !== undefined && args[1] !== undefined) fetchReviews(args[0], args[1]);
else if (command === "compare" && args[0] !== undefined) process.exit(await compare(args[0], args[1], Number(args[2] ?? 2)));
else {
  console.error("usage: review-body-oracle.ts calibrate | fetch <owner/repo> <out.json> | compare <base-ref> [reviews.json] [depth]");
  process.exit(2);
}
