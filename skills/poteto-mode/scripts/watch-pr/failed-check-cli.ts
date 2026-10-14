import { Command, CommanderError, InvalidArgumentError } from "commander";
import { GhFailedCheckReader, parseCheckedHead, parseRunId, renderEvidence, type CheckedHead, type RunId, type EvidenceRequest, type FailedCheckReader } from "./failed-check-evidence.ts";

export interface EvidenceRuntime {
  readonly reader: FailedCheckReader;
  readonly stdout: (value: string) => void;
  readonly stderr: (value: string) => void;
}
function positiveInteger(value: string): number {
  if (!/^[1-9][0-9]*$/.test(value) || !Number.isSafeInteger(Number(value))) throw new InvalidArgumentError("must be a positive safe integer");
  return Number(value);
}
function coordinate(value: string): string {
  if (!/^[a-zA-Z0-9_.-]{1,100}$/.test(value) || value === "." || value === "..") throw new InvalidArgumentError("must be a repository coordinate");
  return value;
}
function host(value: string): string {
  try {
    const url = new URL(`https://${value}`);
    if (url.hostname !== value.toLowerCase() || url.port || url.username || url.password || url.pathname !== "/" || url.search || url.hash) throw new Error("invalid host");
    return url.hostname;
  } catch { throw new InvalidArgumentError("must be a hostname"); }
}
interface RawOptions {
  readonly owner: string;
  readonly repo: string;
  readonly host: string;
  readonly run: RunId;
  readonly head: CheckedHead;
  readonly attempt: number;
  readonly pretty: boolean;
}
export async function main(argv: readonly string[], runtime: EvidenceRuntime = {
  reader: new GhFailedCheckReader(),
  stdout: (value) => process.stdout.write(value),
  stderr: (value) => process.stderr.write(value),
}): Promise<number> {
  const program = new Command("failed-check-evidence")
    .description("Read logs and JUnit artifacts for one exact Actions run and checked head. Requires Bun, gh, and Python 3.9 or newer. Never reruns CI.")
    .configureOutput({ writeOut: runtime.stdout, writeErr: runtime.stderr })
    .exitOverride()
    .requiredOption("--owner <owner>", "GitHub repository owner", coordinate)
    .requiredOption("--repo <repo>", "GitHub repository name", coordinate)
    .option("--host <host>", "GitHub hostname", process.env.GH_HOST || "github.com")
    .requiredOption("--run <id>", "exact Actions run id", (value) => { try { return parseRunId(value); } catch { throw new InvalidArgumentError("must be a positive safe integer"); } })
    .requiredOption("--head <sha>", "checked head SHA", (value) => { try { return parseCheckedHead(value); } catch { throw new InvalidArgumentError("must be a full hexadecimal commit SHA"); } })
    .requiredOption("--attempt <number>", "observed run attempt", positiveInteger)
    .option("--pretty", "indent the bounded JSON receipt", false)
    .addHelpText("after", "\nExit 0 means a verified receipt without gaps. Exit 2 means evidence gaps. Exit 64 means invalid arguments. Failure records do not mean the check passed.\n");
  try {
    program.parse(argv, { from: "user" });
    const options = program.opts<RawOptions>();
    const request: EvidenceRequest = {
      repository: { host: host(options.host), owner: options.owner, repo: options.repo },
      runId: options.run, checkedHead: options.head, attempt: options.attempt,
    };
    const report = await runtime.reader.recover(request);
    const rendered = renderEvidence(report, options.pretty);
    runtime.stdout(rendered.output);
    return rendered.exitCode;
  } catch (error) {
    if (error instanceof InvalidArgumentError) { runtime.stderr(`${error.message}\n`); return 64; }
    if (error instanceof CommanderError) return error.exitCode === 0 ? 0 : 64;
    throw error;
  }
}
