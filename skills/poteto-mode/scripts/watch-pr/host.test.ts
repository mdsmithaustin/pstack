import { describe, expect, it } from "bun:test";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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

function commandOutput(remote: string): { context: unknown; commands: string } {
  const directory = mkdtempSync(join(tmpdir(), "watch-pr-commands-"));
  try {
    const log = join(directory, "commands");
    const git = join(directory, "git");
    const gh = join(directory, "gh");
    writeFileSync(git, `#!/bin/sh\nprintf '%s\\n' '${remote}'\n`);
    writeFileSync(
      gh,
      "#!/bin/sh\nprintf '%s\\n' '---' \"$@\" >> \"$WATCH_PR_COMMANDS\"\nprintf '%s\\n' '[]'\n"
    );
    chmodSync(git, 0o755);
    chmodSync(gh, 0o755);
    const script = `import { GhGitHubReader, resolveContext } from ${JSON.stringify(join(import.meta.dir, "github.ts"))}; import { parsePrNumber } from ${JSON.stringify(join(import.meta.dir, "types.ts"))}; const reader = new GhGitHubReader(); const context = await resolveContext({ reader, owner: "explicit", repo: "override", pr: parsePrNumber(14) }); for (const operation of [() => reader.pullRequest(context), () => reader.openPullRequests(context), () => reader.checksFastPath(context), () => reader.checkRollupPage(context, null), () => reader.reviewState(context), () => reader.commitRollups(context)]) { try { await operation(); } catch {} } console.log(JSON.stringify(context));`;
    const result = Bun.spawnSync([process.execPath, "-e", script], {
      cwd: import.meta.dir,
      env: {
        ...process.env,
        PATH: `${directory}:${process.env.PATH ?? ""}`,
        WATCH_PR_COMMANDS: log,
      },
    });
    if (result.exitCode !== 0)
      throw new Error(new TextDecoder().decode(result.stderr));
    return {
      context: JSON.parse(new TextDecoder().decode(result.stdout)),
      commands: readFileSync(log, "utf8"),
    };
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

  it("uses a GHES HTTPS origin remote", () => {
    expect(
      readerOutput(
        "printf '%s\\n' 'https://github.sie.sony.com/team/project.git'",
        "https://github.com/wrong/project/pull/14"
      )
    ).toEqual({
      host: "github.sie.sony.com",
      owner: "team",
      repo: "project",
      number: 14,
    });
  });

  it("rejects HTTPS userinfo and non-git scp users as origin remotes", () => {
    for (const remote of [
      "https://git@github.sie.sony.com/team/project.git",
      "bob@github.sie.sony.com:team/project.git",
    ]) {
      expect(
        readerOutput(
          `printf '%s\\n' '${remote}'`,
          "https://github.com/public/repo/pull/14"
        )
      ).toEqual({ host: "github.com", owner: "public", repo: "repo", number: 14 });
    }
  });

  it("targets every gh query to the origin GHES host with explicit owner and repo", () => {
    const result = commandOutput("ssh://git@github.sie.sony.com/team/project.git");
    expect(result.context).toEqual({
      host: "github.sie.sony.com",
      owner: "explicit",
      repo: "override",
      number: 14,
    });
    const commands = result.commands.split("---\n").filter(Boolean);
    expect(commands).toHaveLength(6);
    expect(
      commands
        .slice(0, 3)
        .every((command) =>
          command.includes("--repo\ngithub.sie.sony.com/explicit/override\n")
        )
    ).toBe(true);
    expect(
      commands
        .slice(3)
        .every((command) =>
          command.includes("--hostname\ngithub.sie.sony.com\n")
        )
    ).toBe(true);
  });

  it("keeps public GitHub gh arguments", () => {
    const result = commandOutput("https://github.com/team/project.git");
    expect(result.context).toEqual({
      host: "github.com",
      owner: "explicit",
      repo: "override",
      number: 14,
    });
    expect(result.commands).toContain("--repo\nexplicit/override\n");
    expect(result.commands).not.toContain("--hostname\n");
    expect(result.commands).not.toContain("--repo\ngithub.com/");
  });
});
