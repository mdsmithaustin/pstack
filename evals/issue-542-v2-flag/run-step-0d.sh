#!/usr/bin/env bash
# usage: run-step-0d.sh <out-dir> <cell> <agents-off|features-off|features-off-flag> [model]
set -euo pipefail
out=$1 cell=$2 kind=$3 model=${4:-gpt-6.1-sol}
repo=${PSTACK_REPO:-$(git -C "$(dirname "$0")" rev-parse --show-toplevel)}
home=$out/$cell/home
mkdir -p "$home/skills" "$out/$cell/work"
flags=()
cp "$HOME/.codex/auth.json" "$home/auth.json"
for skill in setup-pstack pstack-harness; do
  cp -R "$repo/skills/$skill" "$home/skills/$skill"
done
case $kind in
  agents-off) printf '[agents]\nenabled = false\n' >"$home/config.toml" ;;
  features-off) printf '[features]\nmulti_agent = false\n\n[agents]\nenabled = false\n' >"$home/config.toml" ;;
  features-off-flag)
    printf '[features]\nmulti_agent = false\n' >"$home/config.toml"
    flags=(-c agents.enabled=false) ;;
  *) echo "unknown kind $kind" >&2; exit 2 ;;
esac
cp "$home/config.toml" "$out/$cell/config.toml"
export CODEX_HOME=$home
cd "$out/$cell/work"
codex features list >"$out/$cell/features.txt" 2>&1
prompt="Read $home/skills/setup-pstack/SKILL.md, and no other copy of the setup-pstack skill. Run only its step 0d (Check Codex subagents), in this session. Do not edit any file and do not run any other step. You cannot ask questions in this run, so end your reply with a section headed OFFERS that lists, in the order the skill offers them, each edit step 0d tells you to offer, or the word none."
set +e
codex exec ${flags[@]+"${flags[@]}"} --skip-git-repo-check -s read-only -m "$model" -c model_reasoning_effort=low --json "$prompt" \
  </dev/null >"$out/$cell/exec.jsonl" 2>"$out/$cell/stderr.txt"
echo "exit $?" >"$out/$cell/exit.txt"
