import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

// Like mise, it walks up from its resolved cwd and stops at a MISE_CEILING_PATHS entry.
const FAKE_MISE = `#!/bin/sh
echo "$*" >> "$MISE_LOG"
locked=
d=$(pwd -P)
while :; do
  grep -qs '^locked = true' "$d/mise.toml" && locked=1
  case ":$MISE_CEILING_PATHS:" in *":$d:"*) break;; esac
  [ "$d" = / ] && break
  d=$(dirname "$d")
done
case $1 in
install)
  if [ -n "$locked" ]; then echo "mise ERROR No lockfile URL found for $3 (--locked mode)" >&2; exit 1; fi
  touch "$MISE_STATE/installed"
  exit 0;;
where) if [ -e "$MISE_STATE/installed" ]; then echo "$MISE_STATE"; exit 0; fi;;
which) if [ -e "$MISE_STATE/installed" ]; then echo "$FAKE_JAVA"; exit 0; fi;;
esac
echo "mise ERROR $2 is not installed" >&2
exit 1
`;

test("the command installs TLC with mise under a mise.toml that sets locked = true above a TMPDIR reached through a symlink", () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "statechart-ceiling-")));
  try {
    const bin = path.join(root, "bin");
    const state = path.join(root, "state");
    const locked = path.join(root, "locked");
    const work = path.join(root, "work");
    for (const d of [bin, state, locked, path.join(locked, "tmp"), work]) fs.mkdirSync(d);
    fs.writeFileSync(path.join(locked, "mise.toml"), "[settings]\nlocked = true\n");
    fs.symlinkSync(locked, path.join(root, "link"));
    fs.writeFileSync(path.join(bin, "mise"), FAKE_MISE, { mode: 0o755 });
    const java = path.join(bin, "java");
    fs.writeFileSync(java, "#!/bin/sh\nexit 150\n", { mode: 0o755 });
    for (const ext of ["tla", "cfg"])
      fs.copyFileSync(
        path.join(here, "corpus", "Counter", `Counter.${ext}`),
        path.join(work, `Counter.${ext}`),
      );
    const log = path.join(root, "mise.log");
    const r = spawnSync(
      process.execPath,
      [
        "--disable-warning=ExperimentalWarning",
        path.join(here, "../../../../../skills/statechart/scripts/statechart.ts"),
        "Counter.tla",
        "--out",
        "out",
      ],
      {
        cwd: work,
        encoding: "utf8",
        env: {
          ...process.env,
          PATH: `${bin}${path.delimiter}${process.env.PATH}`,
          TLA2TOOLS: "",
          JAVA: "",
          FAKE_JAVA: java,
          MISE_STATE: state,
          MISE_LOG: log,
          TMPDIR: path.join(root, "link", "tmp"),
        },
      },
    );
    assert.doesNotMatch(r.stderr, /Cannot find TLC/);
    assert.match(fs.readFileSync(log, "utf8"), /^install /m);
    assert.match(r.stderr, /SANY could not read Counter\.tla \(exit 150\)/);
    assert.equal(r.status, 2);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
