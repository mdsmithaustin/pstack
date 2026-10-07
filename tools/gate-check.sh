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
pinned=/Users/msmith1/.local/share/mise/installs/python/3.14.7/bin/python3.14
if [[ -n ${PSTACK_GATE_PYTHON:-} ]]; then
  py=("$PSTACK_GATE_PYTHON")
elif [[ -x $pinned ]]; then
  py=("$pinned")
else
  py=(uv run -q --no-project --python 3.12 --with-requirements tools/requirements.txt python)
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
run lint "skill frontmatter" . "${py[@]}" tools/check-skill-frontmatter.py skills --triggers tools/skill-trigger-cases.json
run lint "skill content" . "${py[@]}" tools/check-skill-content.py skills --conventions-file tools/skill-content-conventions.json
run lint "subagent bundle" . "${py[@]}" tools/generate-subagents.py --check
run lint "promise ledger" . "${py[@]}" evals/promises/ledger.py audit
run lint "pstack-models default" . "${py[@]}" skills/setup-pstack/scripts/check-models-config.py skills/setup-pstack/examples/pstack-models.md

run test "tools unit tests" . "${py[@]}" -m unittest discover -s tools -p 'test_*.py'
run test "promise unit tests" . "${py[@]}" -m unittest discover -s evals/promises -p 'test_*.py'
run test "setup-pstack unit tests" . "${py[@]}" -m unittest discover -s tests/skills/setup-pstack/scripts -p 'test_*.py'
run test "poteto-mode bun install" skills/poteto-mode/scripts bun install --frozen-lockfile
run test "poteto-mode bun tests" skills/poteto-mode/scripts bun run test
run test "poteto-mode typecheck" skills/poteto-mode/scripts bun run typecheck

exit "$failed"
