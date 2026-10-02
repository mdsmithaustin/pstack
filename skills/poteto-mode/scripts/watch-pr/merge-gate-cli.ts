import { existsSync } from "node:fs";
import { Command, CommanderError, InvalidArgumentError, Option } from "commander";
import { GhGitHubReader, WatcherQueryError, resolveContext } from "./github.ts";
import {
  MergeGateError,
  exitCodeOf,
  runMergeGate,
  type MergeAction,
  type MergeGateResult,
  type MergePort,
} from "./merge-gate.ts";
import { GhGitMergePort } from "./merge-effects.ts";
import { renderJson, renderPretty } from "./merge-gate-render.ts";
import type * as T from "./types.ts";
import { parsePrNumber } from "./types.ts";

export interface MergeGateOptions {
  readonly owner: string | null;
  readonly repo: string | null;
  readonly pr: T.PrNumber;
  readonly pretty: boolean;
  readonly action: MergeAction;
}

function prNumber(value: string): T.PrNumber {
  try {
    return parsePrNumber(Number(value.replace(/^#/, "")));
  } catch {
    throw new InvalidArgumentError("must be a positive integer");
  }
}
function overrideReason(value: string): string {
  const reason = value.trim();
  if (reason === "")
    throw new InvalidArgumentError("the reason must not be empty");
  return reason;
}
interface RawOptions {
  readonly owner?: string;
  readonly repo?: string;
  readonly pr: T.PrNumber;
  readonly subject?: string;
  readonly bodyFile?: string;
  readonly check: boolean;
  readonly override?: string;
  readonly pretty: boolean;
}

export function parseArgs(
  argv: readonly string[],
  io: Pick<MergeGateRuntime, "stdout" | "stderr">
): MergeGateOptions {
  const program = new Command("merge-gate")
    .description(
      "Merge a pull request only when every Shipping gate holds.\nJSON is the default; --pretty renders human text. Exit 0 merged or ready, 10 not ready, 64 usage, 1 query or merge error."
    )
    .configureOutput({ writeOut: io.stdout, writeErr: io.stderr })
    .exitOverride()
    .option("--owner <owner>", "GitHub repository owner")
    .option("--repo <repo>", "GitHub repository name")
    .requiredOption("--pr <number>", "pull request number", prNumber)
    .option("--subject <subject>", "squash commit subject")
    .option("--body-file <path>", "squash commit body file")
    .addOption(
      new Option("--check", "print the gate report and exit; never merge")
        .default(false)
        .conflicts("override")
    )
    .option(
      "--override <reason>",
      "merge past failed gates, after posting the reason and the failed gates as a PR comment",
      overrideReason
    )
    .option("--pretty", "render human text instead of JSON", false);
  program.parse(argv, { from: "user" });
  const raw = program.opts<RawOptions>();
  const subject = raw.subject?.trim() ?? "";
  const bodyFile = raw.bodyFile?.trim() ?? "";
  if (!raw.check && subject === "")
    program.error("error: --subject is required unless --check is given");
  if (!raw.check && bodyFile === "")
    program.error("error: --body-file is required unless --check is given");
  return {
    owner: raw.owner ?? null,
    repo: raw.repo ?? null,
    pr: raw.pr,
    pretty: raw.pretty,
    action: raw.check
      ? { kind: "check" }
      : { kind: "merge", subject, bodyFile, override: raw.override ?? null },
  };
}

export interface MergeGateRuntime {
  readonly reader: T.GitHubReader;
  readonly port: MergePort;
  readonly clock: { observedAt(): string };
  readonly bodyFileReadable: (path: string) => boolean;
  readonly stdout: (value: string) => void;
  readonly stderr: (value: string) => void;
}
function realRuntime(): MergeGateRuntime {
  return {
    reader: new GhGitHubReader(),
    port: new GhGitMergePort(),
    clock: { observedAt: () => new Date().toISOString() },
    bodyFileReadable: (path) => existsSync(path),
    stdout: (value) => process.stdout.write(value),
    stderr: (value) => process.stderr.write(value),
  };
}

async function runOrError(
  runtime: MergeGateRuntime,
  options: MergeGateOptions
): Promise<MergeGateResult> {
  try {
    const context = await resolveContext({
      reader: runtime.reader,
      owner: options.owner,
      repo: options.repo,
      pr: options.pr,
    });
    return await runMergeGate({
      reader: runtime.reader,
      port: runtime.port,
      context,
      action: options.action,
    });
  } catch (error) {
    if (error instanceof WatcherQueryError)
      return { kind: "ERROR", source: "github", detail: error.failure.detail };
    if (error instanceof MergeGateError)
      return { kind: "ERROR", source: error.source, detail: error.message };
    throw error;
  }
}

export async function main(
  argv: readonly string[],
  runtime: MergeGateRuntime = realRuntime()
): Promise<number> {
  let options: MergeGateOptions;
  try {
    options = parseArgs(argv, runtime);
  } catch (error) {
    if (!(error instanceof CommanderError)) throw error;
    return error.exitCode === 0 ? 0 : 64;
  }
  if (
    options.action.kind === "merge" &&
    !runtime.bodyFileReadable(options.action.bodyFile)
  ) {
    runtime.stderr(
      `error: --body-file ${options.action.bodyFile} is not readable\n`
    );
    return 64;
  }
  const result = await runOrError(runtime, options);
  const stamp = { observedAt: runtime.clock.observedAt() };
  runtime.stdout(
    options.pretty ? renderPretty(result) : renderJson(result, stamp)
  );
  return exitCodeOf(result);
}
