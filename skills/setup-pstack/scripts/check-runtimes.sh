#!/usr/bin/env bash
# Report which runtimes pstack's bundled scripts need and what stops without each.
# Prints one line per runtime. Exits 1 when python3 is missing, does not run, or is
# older than 3.9, because the plan script, the model resolver and the preserve gate
# all need it. Exits 0 otherwise; a missing bun, node or gh is reported, not fatal.
# Installs nothing and changes nothing.
set -u

status=0

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3: missing. Stops: the plan script, the model resolver, and the preserve gate. Install Python 3.9 or newer."
  status=1
elif ! version=$(python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null); then
  echo "python3: found but does not run. Stops: the plan script, the model resolver, and the preserve gate."
  status=1
elif ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
  echo "python3: $version is older than 3.9. Stops: the plan script, the model resolver, and the preserve gate."
  status=1
else
  echo "python3: $version"
fi

optional() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "$1: found"
  else
    echo "$1: missing. $2"
  fi
}

optional bun "Stops: the PR watcher and merge gate, the orchestrate store, and PR recap sketches and image upload. Babysit falls back to gh."
optional node "Stops: the multi-PR plan check. The statechart compiler needs bun or a node that runs TypeScript."
optional gh "Stops: opening, watching, and landing GitHub pull requests."

exit "$status"
