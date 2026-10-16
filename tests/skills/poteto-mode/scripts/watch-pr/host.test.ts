import { describe, expect, it } from "bun:test";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer } from "node:http";
import { createSecureContext, TLSSocket } from "node:tls";

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

  it("binds every public GitHub query despite ambient GH_HOST", () => {
    const result = commandOutput("https://github.com/team/project.git", "example.invalid");
    expect(result.context).toEqual({
      host: "github.com",
      owner: "explicit",
      repo: "override",
      number: 14,
    });
    const commands = result.commands.split("---\n").filter(Boolean);
    expect(commands).toHaveLength(6);
    for (const command of commands.slice(0, 3))
      expect(command).toContain("--repo\ngithub.com/explicit/override\n");
    for (const command of commands.slice(3))
      expect(command).toContain("--hostname\ngithub.com\n");
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

function currentPrRun(gitScript: string, branchPr = 14): {
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
      `#!/bin/sh
printf '%s\\n' '---' "$@" >> "$WATCH_PR_COMMANDS"
case "$3" in 14) number=14;; *) number=${branchPr};; esac
case "$5" in example.com/*) host=example.com;; *) host=github.com;; esac
printf '{"number":%s,"url":"https://%s/team/project/pull/%s"}\\n' "$number" "$host" "$number"
`
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
const gitScript = (
  remote: string,
  branch: string,
  tracking = "",
  trackingRemote = "origin",
  aliases: Readonly<Record<string, string>> = {}
): string =>
  `case "$1" in
remote) case "$3" in
origin) ${remote === "" ? "exit 1" : `printf '%s\\n' '${remote}'`};;
${Object.entries(aliases).map(([name, url]) => `${name}) printf '%s\\n' '${url}';;`).join("\n")}
*) exit 1;; esac;;
ls-remote) case "$3" in
origin) printf '%s\\n' '${remote}';;
${Object.entries(aliases).map(([name, url]) => `${name}) printf '%s\\n' '${url}';;`).join("\n")}
*) printf '%s\\n' "$3";; esac;;
branch) printf '%s\\n' '${branch}';;
config) case "$3" in
'branch.${branch}.merge') printf '%s\\n' '${tracking}';;
'branch.${branch}.remote') ${trackingRemote === "" ? "exit 1" : `printf '%s\\n' '${trackingRemote}'`};;
*) exit 1;; esac;;
*) exit 1;; esac`;

describe("current PR lookup without --pr", () => {
  it("passes the origin repo and the checked-out branch to gh pr view", () => {
    const { result, commands } = currentPrRun(
      gitScript("https://github.com/team/project.git", "feature-x")
    );
    expect(commands).toEqual([
      ["pr", "view", "feature-x", "--repo", "github.com/team/project", "--json", "number,url"],
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
      ["pr", "view", "14", "--repo", "github.com/team/project", "--json", "number,url"],
    ]);
    expect(result.context).toEqual({ host: "github.com", owner: "team", repo: "project", number: 14 });
  });

  it("keeps the Enterprise origin for a tracked pull request", () => {
    const { result, commands } = currentPrRun(
      gitScript("ssh://git@example.com/team/project.git", "someone-feature", "refs/pull/14/head")
    );
    expect(commands).toEqual([
      ["pr", "view", "14", "--repo", "example.com/team/project", "--json", "number,url"],
    ]);
    expect(result.context).toEqual({ host: "example.com", owner: "team", repo: "project", number: 14 });
  });

  it("resolves matching tracking aliases and direct URLs against origin identity", () => {
    for (const origin of ["https://github.com/team/project.git", "https://example.com/team/project.git"]) {
      const url = origin.replace("https://", "ssh://git@");
      for (const trackingRemote of ["mirror", url]) {
        const { result, commands } = currentPrRun(
          gitScript(origin, "someone-feature", "refs/pull/14/head", trackingRemote, { mirror: url }),
          27
        );
        const host = new URL(origin).hostname;
        expect(commands).toEqual([
          ["pr", "view", "14", "--repo", `${host}/team/project`, "--json", "number,url"],
        ]);
        expect(result.context).toEqual({ host, owner: "team", repo: "project", number: 14 });
      }
    }
  });

  it("uses the branch PR when upstream has a colliding PR number", () => {
    const { result, commands } = currentPrRun(
      gitScript("https://github.com/team/project.git", "someone-feature", "refs/pull/14/head", "upstream", {
        upstream: "https://github.com/parent/project.git",
      }),
      27
    );
    expect(commands).toEqual([
      ["pr", "view", "someone-feature", "--repo", "github.com/team/project", "--json", "number,url"],
    ]);
    expect(result.context).toEqual({ host: "github.com", owner: "team", repo: "project", number: 27 });
  });

  it("falls back to the branch for unresolved or mismatched tracking identities", () => {
    for (const trackingRemote of [
      "", "missing", ".", "invalid",
      "https://example.com/team/other.git",
      "https://example.com/other/project.git",
      "https://example.net/team/project.git",
      "https://github.com/team/project.git",
    ]) {
      const { result, commands } = currentPrRun(
        gitScript("https://example.com/team/project.git", "someone-feature", "refs/pull/14/head", trackingRemote, {
          invalid: "/local/repository",
        }),
        27
      );
      expect(commands).toEqual([
        ["pr", "view", "someone-feature", "--repo", "example.com/team/project", "--json", "number,url"],
      ]);
      expect(result.context).toEqual({ host: "example.com", owner: "team", repo: "project", number: 27 });
    }
  });

  it("uses branch lookup for ordinary and invalid pull-request tracking refs", () => {
    for (const tracking of ["refs/heads/feature-x", "refs/pull/14/merge", "refs/pull/0/head"])
      expect(currentPrRun(gitScript("https://github.com/team/project.git", "feature-x", tracking)).commands).toEqual([
        ["pr", "view", "feature-x", "--repo", "github.com/team/project", "--json", "number,url"],
      ]);
  });
});

describe("native Git tracking identity through the watcher CLI", () => {
  for (const named of [false, true]) {
    for (const scenario of [
      { name: "matching", effective: "https://github.com/team/project.git", url: "https://github.com/team/project.git", from: "", to: "", selector: "14" },
      { name: "rewritten away to another owner", effective: "https://github.com/fork/project.git", url: "https://github.com/team/project.git", from: "https://github.com/team/", to: "https://github.com/fork/", selector: "feature-x" },
      { name: "rewritten away to another host", effective: "https://example.com/team/project.git", url: "https://github.com/team/project.git", from: "https://github.com/", to: "https://example.com/", selector: "feature-x" },
      { name: "rewritten toward origin", effective: "https://github.com/team/project.git", url: "https://github.com/fork/project.git", from: "https://github.com/fork/", to: "https://github.com/team/", selector: "14" },
      { name: "mismatched repository", effective: "https://github.com/team/other.git", url: "https://github.com/team/other.git", from: "", to: "", selector: "feature-x" },
      { name: "detached HEAD", effective: "https://github.com/team/project.git", url: "https://github.com/team/project.git", from: "", to: "", selector: "", refusal: "detached" },
      { name: "unavailable origin", effective: "https://github.com/team/project.git", url: "https://github.com/team/project.git", from: "", to: "", selector: "", refusal: "origin" },
    ]) {
      it(`${named ? "named" : "direct"} tracking ${scenario.name}`, () => {
        const directory = mkdtempSync(join(tmpdir(), "watch-pr-native-"));
        const env = {
          ...process.env,
          GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_NOSYSTEM: "1",
          GH_HOST: "example.invalid", WATCH_PR_COMMANDS: join(directory, "commands"),
          PATH: `${directory}:${process.env.PATH ?? ""}`,
        };
        const git = (...args: string[]) => {
          const result = Bun.spawnSync(["git", ...args], { cwd: directory, env });
          expect(result.exitCode, new TextDecoder().decode(result.stderr)).toBe(0);
          return new TextDecoder().decode(result.stdout).trim();
        };
        try {
          git("init", "-q", "-b", "feature-x");
          git("remote", "add", "origin", "git@github.com:team/project.git");
          if (named) git("remote", "add", "mirror", scenario.url);
          git("config", "branch.feature-x.remote", named ? "mirror" : scenario.url);
          git("config", "branch.feature-x.merge", "refs/pull/14/head");
          if (scenario.from) git("config", `url.${scenario.to}.insteadOf`, scenario.from);
          expect(git("ls-remote", "--get-url", named ? "mirror" : scenario.url)).toBe(
            scenario.effective
          );
          if (scenario.refusal !== undefined) {
            if (scenario.refusal === "origin") git("remote", "remove", "origin");
            else {
              git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "fixture");
              git("checkout", "-q", "--detach");
            }
          }
          writeFileSync(env.WATCH_PR_COMMANDS, "");
          writeFileSync(join(directory, "gh"), `#!/bin/sh
printf '%s\\n' '---' "$@" >> "$WATCH_PR_COMMANDS"
case "$3" in 14) number=14;; *) number=27;; esac
case "$7" in
number,url) printf '{"number":%s,"url":"https://github.com/team/project/pull/%s"}\\n' "$number" "$number";;
*) printf '%s\\n' '{"mergeable":"MERGEABLE","mergeStateStatus":"CLEAN","reviewDecision":"APPROVED","headRefOid":"abc","headRefName":"feature-x","baseRefName":"main","state":"MERGED","mergedAt":"2026-10-01T00:00:00Z","isDraft":false}';;
esac
`);
          chmodSync(join(directory, "gh"), 0o755);
          const result = Bun.spawnSync([process.execPath, join(SOURCE_DIR, "watch-pr"), "--status-only"], {
            cwd: directory, env,
          });
          if (scenario.refusal !== undefined) {
            expect(result.exitCode).toBe(7);
            expect(new TextDecoder().decode(result.stdout)).toContain(scenario.refusal);
            expect(readFileSync(env.WATCH_PR_COMMANDS, "utf8")).toBe("");
            return;
          }
          expect(result.exitCode, new TextDecoder().decode(result.stderr)).toBe(0);
          const output = JSON.parse(new TextDecoder().decode(result.stdout));
          expect(output.rows[0].context).toEqual({
            host: "github.com", owner: "team", repo: "project",
            number: scenario.selector === "14" ? 14 : 27,
          });
          const commands = readFileSync(env.WATCH_PR_COMMANDS, "utf8").split("---\n").filter(Boolean);
          expect(commands[0]?.trimEnd().split("\n")).toEqual([
            "pr", "view", scenario.selector, "--repo", "github.com/team/project", "--json", "number,url",
          ]);
        } finally {
          rmSync(directory, { recursive: true, force: true });
        }
      });
    }
  }
});

describe("real gh host routing", () => {
  it("selects the attachment host token despite ambient GH_HOST", () => {
    expect(Bun.which("gh"), "required executable missing from PATH: gh").not.toBeNull();
    for (const [host, token] of [["github.com", "public-test-token"], ["example.com", "enterprise-test-token"]]) {
      const result = Bun.spawnSync(["gh", "auth", "token", "--hostname", host], {
        env: { ...process.env, GH_HOST: "example.invalid", GH_TOKEN: "public-test-token", GH_ENTERPRISE_TOKEN: "enterprise-test-token" },
      });
      expect(result.exitCode, new TextDecoder().decode(result.stderr)).toBe(0);
      expect(new TextDecoder().decode(result.stdout).trim()).toBe(token);
    }
  });

  it("keeps watcher, merge, and workflow commands on their resolved HTTPS host", async () => {
    for (const tool of ["gh", "openssl"])
      expect(Bun.which(tool), `required executable missing from PATH: ${tool}`).not.toBeNull();
    const directory = mkdtempSync(join(tmpdir(), "watch-pr-https-"));
    const requests: { target: string; path: string }[] = [];
    const cert = join(directory, "cert.pem");
    const key = join(directory, "key.pem");
    const generated = Bun.spawnSync([
      "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
      "-keyout", key, "-out", cert, "-days", "1", "-subj", "/CN=api.github.com",
      "-addext", "subjectAltName=DNS:api.github.com,DNS:example.com,DNS:example.invalid",
    ]);
    expect(generated.exitCode).toBe(0);
    const secureContext = createSecureContext({ key: readFileSync(key), cert: readFileSync(cert) });
    const server = createServer();
    server.on("connect", (request, socket) => {
      socket.write("HTTP/1.1 200 Connection Established\r\n\r\n");
      const tls = new TLSSocket(socket, { isServer: true, secureContext });
      let input = "";
      tls.on("error", () => {});
      tls.on("data", (data) => {
        input += data.toString();
        if (!input.includes("\r\n\r\n")) return;
        tls.removeAllListeners("data");
        requests.push({ target: request.url ?? "", path: input.split(" ")[1] ?? "" });
        tls.end('HTTP/1.1 404 Not Found\r\nContent-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}');
      });
    });
    try {
      await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
      const address = server.address();
      if (address === null || typeof address === "string") throw new Error("proxy address missing");
      const git = join(directory, "git");
      writeFileSync(git, "#!/bin/sh\nprintf '%s\\n' 'https://github.com/team/project.git'\n");
      chmodSync(git, 0o755);
      for (const scenario of [
        { operation: "reader.openPullRequests(context)", host: "github.com", target: "api.github.com:443", path: "/graphql" },
        { operation: "port.conversation(context)", host: "github.com", target: "api.github.com:443", path: "/graphql" },
        { operation: "port.conversation(context)", host: "example.com", target: "example.com:443", path: "/api/graphql" },
        ...[
          ["pr", "edit", "14", "-R", "github.com/team/project", "--base", "main"],
          ["pr", "view", "14", "-R", "github.com/team/project", "--json", "state,mergedAt,mergeStateStatus,statusCheckRollup,autoMergeRequest"],
          ["pr", "view", "14", "-R", "github.com/team/project", "--json", "body,comments"],
          ["pr", "diff", "14", "-R", "github.com/team/project"],
          ["pr", "view", "feature-x", "-R", "github.com/team/project", "--json", "baseRefName"],
          ["pr", "view", "14", "-R", "github.com/team/project", "--json", "title,body,author,createdAt,mergedAt,labels,closingIssuesReferences,comments,reviews,files"],
          ["pr", "comment", "14", "-R", "github.com/team/project", "--body", "test"],
        ].map((argv) => ({ operation: `command(${JSON.stringify(argv)})`, host: "github.com", target: "api.github.com:443", path: null })),
        { operation: 'command(["api", "--hostname", "github.com", "--method", "POST", "repos/team/project/pulls/14/comments/1/replies", "-f", "body=test"])', host: "github.com", target: "api.github.com:443", path: "/repos/team/project/pulls/14/comments/1/replies" },
      ]) {
        requests.length = 0;
        const script = `
          import { GhGitHubReader, resolveContext } from ${JSON.stringify(join(SOURCE_DIR, "github.ts"))};
          import { GhGitMergePort } from ${JSON.stringify(join(SOURCE_DIR, "merge-effects.ts"))};
          async function command(argv) {
            const child = Bun.spawn(["gh", ...argv], { stdout: "ignore", stderr: "ignore" });
            await child.exited;
          }
          const reader = new GhGitHubReader();
          const port = new GhGitMergePort();
          const context = ${scenario.host === "github.com"
            ? 'await resolveContext({ reader, owner: "team", repo: "project", pr: 14 })'
            : '{ host: "example.com", owner: "team", repo: "project", number: 14 }'};
          try { await ${scenario.operation}; } catch {}
          console.log(JSON.stringify(context));
        `;
        const child = Bun.spawn([process.execPath, "-e", script], {
          cwd: directory,
          env: {
            ...process.env, PATH: `${directory}:${process.env.PATH ?? ""}`,
            GH_HOST: "example.invalid", GH_TOKEN: "test", GH_ENTERPRISE_TOKEN: "test",
            GH_CONFIG_DIR: directory, SSL_CERT_FILE: cert,
            HTTPS_PROXY: `http://127.0.0.1:${address.port}`, NO_PROXY: "", no_proxy: "",
          }, stdout: "pipe", stderr: "pipe",
        });
        const [code, stdout, stderr] = await Promise.all([
          child.exited, new Response(child.stdout).text(), new Response(child.stderr).text(),
        ]);
        expect({ code, stderr }).toEqual({ code: 0, stderr: "" });
        expect(JSON.parse(stdout)).toEqual({ host: scenario.host, owner: "team", repo: "project", number: 14 });
        expect(requests.length).toBeGreaterThan(0);
        for (const request of requests) {
          expect(request.target).toBe(scenario.target);
          if (scenario.path !== null) expect(request.path).toBe(scenario.path);
        }
      }
    } finally {
      server.closeAllConnections();
      await new Promise<void>((resolve) => server.close(() => resolve()));
      rmSync(directory, { recursive: true, force: true });
    }
  }, 20_000);
});
