import { readFileSync } from "node:fs";
import { formatReport, summarize } from "./format.ts";

const USAGE = "usage: node src/cli.ts <file>";

function main(argv: string[]): number {
  const paths: string[] = [];
  for (const arg of argv) {
    if (arg === "-h" || arg === "--help") {
      console.log(USAGE);
      return 0;
    }
    if (arg.startsWith("-")) {
      console.error(`unknown option: ${arg}`);
      return 2;
    }
    paths.push(arg);
  }
  if (paths.length !== 1) {
    console.error(USAGE);
    return 2;
  }
  const text = readFileSync(paths[0], "utf8");
  for (const line of formatReport(summarize(text))) console.log(line);
  return 0;
}

process.exitCode = main(process.argv.slice(2));
