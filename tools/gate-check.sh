#!/usr/bin/env bash
set -euo pipefail

tier=${1:-}
if [[ $tier != lint && $tier != test ]]; then
  echo "usage: tools/gate-check.sh lint|test" >&2
  exit 2
fi

cd "$(git rev-parse --show-toplevel)"

# no-mistakes runs in worktrees where mise and the .venv are unavailable, so the
# interpreter comes from the environment, then the native 3.14 that evals/promises
# pins (Python 3.12 fails its native fsmonitor test on this host), then CI's 3.12.
pinned=$HOME/.local/share/mise/installs/python/3.14.7/bin/python3.14
if [[ -n ${PSTACK_GATE_PYTHON:-} ]]; then
  py=("$PSTACK_GATE_PYTHON")
elif [[ -x $pinned ]]; then
  py=("$pinned")
else
  py=(uv run -q --no-project --python 3.12 python)
fi

failed=0
run() {
  local only=$1 name=$2 dir=$3
  shift 3
  [[ $only == "$tier" ]] || return 0
  if (cd "$dir" && "$@"); then
    echo "PASS $tier: $name"
  else
    echo "FAIL $tier: $name"
    failed=1
  fi
}

run lint "cross-suite references" . "${py[@]}" tools/check-cross-suite-references.py --foreign-file tools/cross-suite-foreign.txt skills
run lint "mode entry byte budget" . "${py[@]}" tools/check-mode-entry-size.py
run lint "personal paths" . "${py[@]}" tools/check-personal-paths.py
run lint "subagent bundle" . "${py[@]}" tools/generate-subagents.py --check
run lint "promise ledger" . "${py[@]}" evals/promises/ledger.py audit
run lint "promise ledger canonical form" . "${py[@]}" evals/promises/ledger.py format --check
run lint "pstack-models default" . "${py[@]}" skills/setup-pstack/scripts/check-models-config.py skills/setup-pstack/examples/pstack-models.md
run lint "skill reference spelling" . "${py[@]}" -m unittest discover -s tools -p test_skill_references.py

run test "tools unit tests" . "${py[@]}" -m unittest discover -s tools -p 'test_*.py'
run test "promise unit tests" . "${py[@]}" -m unittest discover -s evals/promises -p 'test_*.py'
run test "setup-pstack unit tests" . "${py[@]}" -m unittest discover -s tests/skills/setup-pstack/scripts -p 'test_*.py'
run test "pstack-harness unit tests" . "${py[@]}" -m unittest discover -s tests/skills/pstack-harness/scripts -p 'test_*.py'
run test "poteto-mode bun install" skills/poteto-mode/scripts bun install --frozen-lockfile
run test "poteto-mode bun tests" skills/poteto-mode/scripts bun run test
run test "poteto-mode typecheck" skills/poteto-mode/scripts bun run typecheck
run test "pr-recap bun install" skills/pr-recap/scripts/sketch bun install --frozen-lockfile
run test "pr-recap sketch tests" skills/pr-recap/scripts/sketch bun run test
run test "statechart node tests" . node --test tests/skills/statechart/scripts/test/*.test.mjs

exit "$failed"
