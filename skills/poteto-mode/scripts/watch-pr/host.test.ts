import { describe, expect, it } from "bun:test";
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function readerOutput(gitResult: string, prUrl: string): unknown {
  const directory = mkdtempSync(join(tmpdir(), "watch-pr-host-"));
  try {
    const git = join(directory, "git");
    const gh = join(directory, "gh");
    writeFileSync(git, `#!/bin/sh\n${gitResult}\n`);
    writeFileSync(
      gh,
      `#!/bin/sh\nprintf '%s\\n' '{"number":14,"url":"${prUrl}"}'\n`
    );
    chmodSync(git, 0o755);
    chmodSync(gh, 0o755);
    const script = `import { GhGitHubReader, resolveContext } from ${JSON.stringify(join(import.meta.dir, "github.ts"))}; import { parsePrNumber } from ${JSON.stringify(join(import.meta.dir, "types.ts"))}; const context = await resolveContext({ reader: new GhGitHubReader(), owner: null, repo: null, pr: parsePrNumber(14) }); console.log(JSON.stringify(context));`;
    const result = Bun.spawnSync([process.execPath, "-e", script], {
      cwd: import.meta.dir,
      env: { ...process.env, PATH: `${directory}:${process.env.PATH ?? ""}` },
    });
    if (result.exitCode !== 0)
      throw new Error(new TextDecoder().decode(result.stderr));
    return JSON.parse(new TextDecoder().decode(result.stdout));
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

describe("repository host inference", () => {
  it("uses a GHES origin remote for an explicit PR number", () => {
    expect(
      readerOutput(
        "printf '%s\\n' 'git@github.sie.sony.com:team/project.git'",
        "https://github.com/wrong/project/pull/14"
      )
    ).toEqual({
      host: "github.sie.sony.com",
      owner: "team",
      repo: "project",
      number: 14,
    });
  });

  it("uses the current GHES PR URL when origin is unavailable", () => {
    expect(
      readerOutput("exit 1", "https://github.sie.sony.com/team/project/pull/14")
    ).toEqual({
      host: "github.sie.sony.com",
      owner: "team",
      repo: "project",
      number: 14,
    });
  });
});
