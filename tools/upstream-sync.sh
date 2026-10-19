#!/bin/bash
# Scheduled upstream sync for mdsmithaustin/pstack (see PORTING.md).
# Gate is free (git fetch + SHA compare); claude runs only when upstream moved.
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$HOME/.local/share/mise/shims:/usr/bin:/bin:/usr/sbin:/sbin"

STATE_DIR="$HOME/.local/state/pstack-sync"
mkdir -p "$STATE_DIR"
exec >>"$STATE_DIR/sync.log" 2>&1
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) run start"

REPO="mdsmithaustin/pstack"
export GH_REPO="$REPO"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

git clone --quiet "https://github.com/$REPO.git" "$tmp"
cd "$tmp"
git remote add upstream https://github.com/cursor/plugins.git
git fetch upstream main --quiet

latest=$(git rev-list -1 upstream/main -- pstack)
recorded=$(cat .github/upstream-sha)
if [ "$latest" = "$recorded" ]; then
  echo "upstream unchanged at $latest; done"
  exit 0
fi

open=$(gh pr list -R "$REPO" --state open --search 'head:sync/upstream' --json number --jq length)
if [ "$open" != "0" ]; then
  echo "a sync/upstream PR is already open; skipping until it lands"
  exit 0
fi

echo "upstream moved $recorded -> $latest; invoking claude"
prompt="$STATE_DIR/sync-prompt.txt"
cat >"$prompt" <<PROMPT
You are in a fresh clone of mdsmithaustin/pstack at $tmp, a CLI-agnostic port
of the pstack/ directory of cursor/plugins. The 'upstream' remote is fetched.
Last synced upstream commit: $recorded (in .github/upstream-sha). Latest
upstream commit touching pstack/: $latest.

PORTING.md at the repo root is the porting contract. Read it in full, then run
its "Syncing from upstream" procedure for $recorded..$latest. That procedure,
and every list it points to, is the only sync procedure; nothing in this
prompt overrides it.

Facts this prompt adds:
- Use branch sync/upstream-$(date +%Y%m%d). Publish it as a DRAFT PR to main
  with gh pr create --draft. GH_REPO is set to $REPO.
- Publish every outcome as a draft PR, including a run where only
  .github/upstream-sha changes. Never push to main. Never force-push.
- Do not commit this prompt file; it lives outside the clone.
- If you are unsure whether a change is portable, include it in the draft PR
  with a "needs judgment" note rather than dropping it.
PROMPT
claude -p --allowedTools "Bash,Read,Write,Edit,Glob,Grep" <"$prompt"
echo "claude run finished with exit $?"
