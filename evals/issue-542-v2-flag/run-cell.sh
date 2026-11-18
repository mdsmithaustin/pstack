#!/usr/bin/env bash
# usage: run-cell.sh <out-dir> <cell> <model> [enable:<feature> | disable:<feature> | agents-off]...
set -euo pipefail
umask 077
if [ $# -lt 3 ]; then echo "usage: run-cell.sh <out-dir> <cell> <model> [step]..." >&2; exit 2; fi
for step in "${@:4}"; do
  case $step in
    enable:* | disable:* | agents-off) ;;
    *) echo "unknown step $step" >&2; exit 2 ;;
  esac
done
out=$(mkdir -p "$1" && cd "$1" && pwd)
cell=$2 model=$3
shift 3
home=$out/$cell/home
mkdir -p "$home" "$out/$cell/work"
trap 'rm -f "$home/auth.json"' EXIT
install -m 600 "$HOME/.codex/auth.json" "$home/auth.json"
: >"$home/config.toml"
export CODEX_HOME=$home
for step in "$@"; do
  case $step in
    enable:*) codex features enable "${step#enable:}" >>"$out/$cell/setup.txt" 2>&1 ;;
    disable:*) codex features disable "${step#disable:}" >>"$out/$cell/setup.txt" 2>&1 ;;
    agents-off) printf '\n[agents]\nenabled = false\n' >>"$home/config.toml" ;;
  esac
done
cp "$home/config.toml" "$out/$cell/config.toml"
cd "$out/$cell/work"
codex features list >"$out/$cell/features.txt" 2>&1
prompt='Do exactly these steps and nothing else. 1. Say whether a tool named spawn_agent is available to you, and if it is, list its parameter names exactly. If your tool manifest lists deferred tool namespaces, search them for spawn_agent before you say it is missing. 2. If it is, call spawn_agent once with a message asking the child to reply with the single word PONG. Set fork_turns to "none" when the tool has a fork_turns parameter, or fork_context to false when it has a fork_context parameter. Then wait for the child to finish. 3. Print the child reply, or print NO_SPAWN if you had no spawn_agent tool.'
set +e
codex exec --skip-git-repo-check -s read-only -m "$model" -c model_reasoning_effort=low --json "$prompt" \
  </dev/null >"$out/$cell/exec.jsonl" 2>"$out/$cell/stderr.txt"
echo "exit $?" >"$out/$cell/exit.txt"
