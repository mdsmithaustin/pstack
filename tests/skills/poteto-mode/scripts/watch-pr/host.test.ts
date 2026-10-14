import { describe, expect, it } from "bun:test";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const SOURCE_DIR = join(import.meta.dir, "../../../../../skills/poteto-mode/scripts/watch-pr");

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
    const script = `import { GhGitHubReader, resolveContext } from ${JSON.stringify(join(SOURCE_DIR, "github.ts"))}; import { parsePrNumber } from ${JSON.stringify(join(SOURCE_DIR, "types.ts"))}; const context = await resolveContext({ reader: new GhGitHubReader(), owner: null, repo: null, pr: parsePrNumber(14) }); console.log(JSON.stringify(context));`;
    const result = Bun.spawnSync([process.execPath, "-e", script], {
      cwd: SOURCE_DIR,
      env: { ...process.env, PATH: `${directory}:${process.env.PATH ?? ""}` },
    });
    if (result.exitCode !== 0)
      throw new Error(new TextDecoder().decode(result.stderr));
    return JSON.parse(new TextDecoder().decode(result.stdout));
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

function commandOutput(
  remote: string,
  host = ""
): { context: unknown; commands: string } {
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
    const script = `import { GhGitHubReader, resolveContext } from ${JSON.stringify(join(SOURCE_DIR, "github.ts"))}; import { parsePrNumber } from ${JSON.stringify(join(SOURCE_DIR, "types.ts"))}; const reader = new GhGitHubReader(); const context = await resolveContext({ reader, owner: "explicit", repo: "override", pr: parsePrNumber(14) }); for (const operation of [() => reader.pullRequest(context), () => reader.openPullRequests(context), () => reader.checksFastPath(context), () => reader.checkRollupPage(context, null), () => reader.reviewStatePage(context, "page-2"), () => reader.commitRollups(context)]) { try { await operation(); } catch {} } console.log(JSON.stringify(context));`;
    const result = Bun.spawnSync([process.execPath, "-e", script], {
      cwd: SOURCE_DIR,
      env: {
        ...process.env,
        GH_HOST: host,
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
        "printf '%s\\n' 'git@example.com:team/project.git'",
        "https://github.com/wrong/project/pull/14"
      )
    ).toEqual({
      host: "example.com",
      owner: "team",
      repo: "project",
      number: 14,
    });
  });

  it("refuses PR-number lookup when origin is unavailable", () => {
    expect(() =>
      readerOutput("exit 1", "https://example.com/team/project/pull/14")
    ).toThrow("origin");
  });

  it("uses a GHES HTTPS origin remote", () => {
    expect(
      readerOutput(
        "printf '%s\\n' 'https://example.com/team/project.git'",
        "https://github.com/wrong/project/pull/14"
      )
    ).toEqual({
      host: "example.com",
      owner: "team",
      repo: "project",
      number: 14,
    });
  });

  it("rejects HTTPS userinfo and non-git scp users as origin remotes", () => {
    for (const remote of [
      "https://git@example.com/team/project.git",
      "bob@example.com:team/project.git",
      "https://@example.com/team/project.git",
      "https://example.com/team/%2Fproject.git",
      "https://example.com/team/project.git?token=PUBLIC_TEST_SENTINEL",
      "https://example.com/team/project.git#PUBLIC_TEST_SENTINEL",
      "https://example.com/team//project.git",
      "https://example.com/other/../team/project.git",
      "ssh://git:PUBLIC_TEST_SENTINEL@" + "example.com/team/project.git",
      "https://example.com:443/team/project.git",
    ]) {
      expect(() =>
        readerOutput(
          `printf '%s\\n' '${remote}'`,
          "https://github.com/public/repo/pull/14"
        )
      ).toThrow("origin");
    }
  }, 20_000);

  it("targets every gh query to the origin GHES host with explicit owner and repo", () => {
    const result = commandOutput("ssh://git@example.com/team/project.git");
    expect(result.context).toEqual({
      host: "example.com",
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
          command.includes("--repo\nexample.com/explicit/override\n")
        )
    ).toBe(true);
    expect(
      commands
        .slice(3)
        .every((command) =>
          command.includes("--hostname\nexample.com\n")
        )
    ).toBe(true);
    expect(
      commands.some(
        (command) =>
          command.includes("after=page-2\n") &&
          command.includes("--hostname\nexample.com\n")
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

  it("uses GH_HOST when explicit context has no origin", () => {
    const result = commandOutput("", "example.com");
    expect(result.context).toEqual({
      host: "example.com",
      owner: "explicit",
      repo: "override",
      number: 14,
    });
    expect(result.commands).toContain(
      "--repo\nexample.com/explicit/override\n"
    );
    expect(result.commands).toContain("--hostname\nexample.com\n");
  });
});

function currentPrRun(gitScript: string): {
  result: { context?: unknown; error?: string };
  commands: string[][];
} {
  const directory = mkdtempSync(join(tmpdir(), "watch-pr-current-"));
  try {
    const log = join(directory, "commands");
    writeFileSync(log, "");
    const git = join(directory, "git");
    const gh = join(directory, "gh");
    writeFileSync(git, `#!/bin/sh\n${gitScript}\n`);
    writeFileSync(
      gh,
      "#!/bin/sh\nprintf '%s\\n' '---' \"$@\" >> \"$WATCH_PR_COMMANDS\"\nprintf '%s\\n' '{\"number\":14,\"url\":\"https://github.com/team/project/pull/14\"}'\n"
    );
    chmodSync(git, 0o755);
    chmodSync(gh, 0o755);
    const script = `import { GhGitHubReader, resolveContext } from ${JSON.stringify(join(SOURCE_DIR, "github.ts"))}; try { console.log(JSON.stringify({ context: await resolveContext({ reader: new GhGitHubReader(), owner: null, repo: null, pr: null }) })); } catch (error) { console.log(JSON.stringify({ error: error.message })); }`;
    const spawned = Bun.spawnSync([process.execPath, "-e", script], {
      cwd: SOURCE_DIR,
      env: {
        ...process.env,
        PATH: `${directory}:${process.env.PATH ?? ""}`,
        WATCH_PR_COMMANDS: log,
      },
    });
    if (spawned.exitCode !== 0)
      throw new Error(new TextDecoder().decode(spawned.stderr));
    return {
      result: JSON.parse(new TextDecoder().decode(spawned.stdout)),
      commands: readFileSync(log, "utf8")
        .split("---\n")
        .filter(Boolean)
        .map((command) => command.trimEnd().split("\n")),
    };
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}
const gitScript = (remote: string, branch: string, tracking = ""): string =>
  `case "$1" in remote) ${remote === "" ? "exit 1" : `printf '%s\\n' '${remote}'`};; branch) printf '%s\\n' '${branch}';; config) printf '%s\\n' '${tracking}';; esac`;

describe("current PR lookup without --pr", () => {
  it("passes the origin repo and the checked-out branch to gh pr view", () => {
    const { result, commands } = currentPrRun(
      gitScript("https://github.com/team/project.git", "feature-x")
    );
    expect(commands).toEqual([
      ["pr", "view", "feature-x", "--repo", "team/project", "--json", "number,url"],
    ]);
    expect(result.context).toEqual({
      host: "github.com",
      owner: "team",
      repo: "project",
      number: 14,
    });
  });

  it("prefixes the host for a GHES origin", () => {
    const { commands } = currentPrRun(
      gitScript("ssh://git@example.com/team/project.git", "feature-x")
    );
    expect(commands).toEqual([
      ["pr", "view", "feature-x", "--repo", "example.com/team/project", "--json", "number,url"],
    ]);
  });

  it("stops without calling gh when HEAD is detached", () => {
    const { result, commands } = currentPrRun(
      gitScript("https://github.com/team/project.git", "")
    );
    expect(commands).toEqual([]);
    expect(result.error).toContain("detached");
  });

  it("refuses lookup without calling gh when origin is unavailable", () => {
    const { result, commands } = currentPrRun(gitScript("", "feature-x"));
    expect(result.error).toContain("origin");
    expect(commands).toEqual([]);
  });

  it("uses the tracked pull-request number in the origin fork", () => {
    const { result, commands } = currentPrRun(
      gitScript("git@github.com:team/project.git", "someone-feature", "refs/pull/14/head")
    );
    expect(commands).toEqual([
      ["pr", "view", "14", "--repo", "team/project", "--json", "number,url"],
    ]);
    expect(result.context).toEqual({ host: "github.com", owner: "team", repo: "project", number: 14 });
  });

  it("keeps the Enterprise origin for a tracked pull request", () => {
    const { commands } = currentPrRun(
      gitScript("ssh://git@example.com/team/project.git", "someone-feature", "refs/pull/14/head")
    );
    expect(commands).toEqual([
      ["pr", "view", "14", "--repo", "example.com/team/project", "--json", "number,url"],
    ]);
  });

  it("uses branch lookup for ordinary and invalid pull-request tracking refs", () => {
    for (const tracking of ["refs/heads/feature-x", "refs/pull/14/merge", "refs/pull/0/head"])
      expect(currentPrRun(gitScript("https://github.com/team/project.git", "feature-x", tracking)).commands).toEqual([
        ["pr", "view", "feature-x", "--repo", "team/project", "--json", "number,url"],
      ]);
  });
});
