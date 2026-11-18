#!/usr/bin/env bash
# usage: run-step-0d.sh <out-dir> <cell> <agents-off|features-off|features-off-flag|v1-default|v2-disabled|dotted|dotted-edit> [model]
# PSTACK_REPO names the tree whose skills/ the session reads, default this checkout.
# The session runs with HOME and CODEX_HOME both private to the cell, so the host's ~/.codex and ~/.agents never reach it.
set -euo pipefail
umask 077
if [ $# -lt 3 ]; then echo "usage: run-step-0d.sh <out-dir> <cell> <kind> [model]" >&2; exit 2; fi
kind=$3
case $kind in
  agents-off | features-off | features-off-flag) model=${4:-gpt-6.1-sol} ;;
  v1-default | v2-disabled | dotted | dotted-edit) model=${4:-gpt-5.6-luna} ;;
  *) echo "unknown kind $kind" >&2; exit 2 ;;
esac
out=$(mkdir -p "$1" && cd "$1" && pwd -P)
cell=$2
repo=${PSTACK_REPO:-$(git -C "$(dirname "$0")" rev-parse --show-toplevel)}
home=$out/$cell/home
user_home=$out/$cell/user-home
mkdir -p "$home/skills" "$user_home" "$out/$cell/work"
trap 'rm -f "$home/auth.json"' EXIT
install -m 600 "$HOME/.codex/auth.json" "$home/auth.json"
for skill in setup-pstack pstack-harness; do
  cp -R "$repo/skills/$skill" "$home/skills/$skill"
done
flags=()
case $kind in
  agents-off) printf '[agents]\nenabled = false\n' >"$home/config.toml" ;;
  features-off) printf '[features]\nmulti_agent = false\n\n[agents]\nenabled = false\n' >"$home/config.toml" ;;
  features-off-flag)
    printf '[features]\nmulti_agent = false\n' >"$home/config.toml"
    flags=(-c agents.enabled=false) ;;
  v1-default | v2-disabled) : >"$home/config.toml" ;;
  dotted | dotted-edit) printf 'features.multi_agent = false\n' >"$home/config.toml" ;;
esac
export CODEX_HOME=$home HOME=$user_home
if [ "$kind" = v2-disabled ]; then codex features disable multi_agent_v2 >"$out/$cell/setup.txt" 2>&1; fi
cp "$home/config.toml" "$out/$cell/config.toml"
printf 'HOME=%s\nCODEX_HOME=%s\n' "$HOME" "$CODEX_HOME" >"$out/$cell/env.txt"
cd "$out/$cell/work"
codex --version >"$out/$cell/version.txt" 2>&1
codex features list >"$out/$cell/features.txt" 2>&1
prompt="Read $home/skills/setup-pstack/SKILL.md, and no other copy of the setup-pstack skill. Run only its step 0d (Check Codex subagents), in this session. Do not edit any file and do not run any other step. You cannot ask questions in this run, so end your reply with a section headed OFFERS that lists, in the order the skill offers them, each edit step 0d tells you to offer, or the word none."
if [ "$kind" = dotted-edit ]; then
  prompt="$prompt Assume the command codex features enable is not available to this user, so offer the edit to the file by hand."
fi
if [ "$kind" = dotted ] || [ "$kind" = dotted-edit ]; then
  prompt="$prompt Then add a last section headed PROPOSED, after OFFERS. For each offered edit to a config file, show the complete config.toml that results from applying it to the starting config, in one fenced toml block. For an offered command, write the command on its own line instead. Keep OFFERS to one line per offer, and put every config file and command only in PROPOSED."
fi
set +e
codex exec ${flags[@]+"${flags[@]}"} --skip-git-repo-check -s read-only -m "$model" -c model_reasoning_effort=low --json "$prompt" \
  </dev/null >"$out/$cell/exec.jsonl" 2>"$out/$cell/stderr.txt"
echo "exit $?" >"$out/$cell/exit.txt"
