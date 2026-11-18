#!/usr/bin/env bash
# usage: config-forms.sh > results/config-forms.txt
# Shows what `codex features enable|disable multi_agent_v2` does to each form of the setting, and which second key Codex rejects.
set -uo pipefail
home=$(mktemp -d)
trap 'rm -rf "$home"' EXIT
export CODEX_HOME=$home HOME=$home
codex --version
row() { codex features list 2>&1 | awk '$1 == "multi_agent_v2" { print "row: " $NF } $1 == "Error:" { print }'; }
show() { sed 's/^/| /' "$home/config.toml"; }
try() {
  printf '\n== %s\n' "$1"
  printf "$2" >"$home/config.toml"
  shift 2
  "$@" >/dev/null 2>&1
  echo "exit $?"
  show
  row
}
try "disable on an empty file" '' codex features disable multi_agent_v2
try "enable on the [features.multi_agent_v2] table" '[features.multi_agent_v2]\nenabled = false\n' codex features enable multi_agent_v2
try "enable on multi_agent_v2 = false under [features]" '[features]\nmulti_agent_v2 = false\nmulti_agent = true\n' codex features enable multi_agent_v2
try "enable on a top-level features.multi_agent_v2 = false" 'features.multi_agent_v2 = false\n' codex features enable multi_agent_v2
try "enable on a file with [features] and no multi_agent_v2" '[features]\nmulti_agent = true\n' codex features enable multi_agent_v2
try "second key: [features] multi_agent_v2 = true beside the table" '[features.multi_agent_v2]\nenabled = false\n\n[features]\nmulti_agent_v2 = true\n' codex features list
try "second key: [features] multi_agent_v2 = true beside a top-level dotted key" 'features.multi_agent_v2 = false\n\n[features]\nmulti_agent_v2 = true\n' codex features list
try "second [features] table" '[features]\nmulti_agent = true\n\n[features]\nmulti_agent_v2 = true\n' codex features list
