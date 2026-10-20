#!/bin/bash
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$HOME/.local/share/mise/shims:/usr/bin:/bin:/usr/sbin:/sbin"

umask 077
STATE_DIR="${PSTACK_SYNC_STATE_DIR:-$HOME/.local/state/pstack-sync}"
mkdir -p "$STATE_DIR"
STATE_DIR=$(cd "$STATE_DIR" && pwd -P)
exec >>"$STATE_DIR/sync.log" 2>&1
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) run start"

REPO="mdsmithaustin/pstack"
export GH_REPO="$REPO"
attempt=$(mktemp -d "$STATE_DIR/attempt-$(date -u +%Y%m%dT%H%M%SZ).XXXXXX")
trap 'echo "retained attempt at $attempt"' EXIT
repo="$attempt/repo"

git clone --quiet "https://github.com/$REPO.git" "$repo"
cd "$repo"
base=$(git rev-parse --verify 'HEAD^{commit}')
printf '%s\n' "$base" >"$attempt/base-sha"
git remote add upstream https://github.com/cursor/plugins.git
git fetch upstream main --quiet

latest=$(git rev-list -1 upstream/main -- pstack)
recorded=$(cat .github/upstream-sha)
if [ "$latest" = "$recorded" ]; then
  echo "upstream unchanged at $latest; done"
  printf 'upstream unchanged\n' >"$attempt/complete"
  rm -rf -- "$repo"
  exit 0
fi

open=$(gh pr list -R "$REPO" --state open --limit 1000 --json headRefName --jq '[.[] | select(.headRefName | startswith("sync/upstream-"))] | length')
if [ "$open" != "0" ]; then
  echo "a sync/upstream PR is already open; skipping until it lands"
  printf 'sync PR already open\n' >"$attempt/complete"
  rm -rf -- "$repo"
  exit 0
fi

for prompt in "$STATE_DIR"/attempt-*/prompt.txt; do
  [ -f "$prompt" ] || continue
  pending=${prompt%/*}
  if [ ! -f "$pending/complete" ]; then
    echo "unfinished sync at $pending; resolve it before another Claude run"
    rm -rf -- "$repo"
    exit 1
  fi
done

echo "upstream moved $recorded -> $latest; invoking claude"
branch="sync/upstream-${attempt##*/}"
printf '%s\n' "$latest" >"$attempt/upstream-sha"
prompt="$attempt/prompt.txt"
cat >"$prompt" <<PROMPT
You are in a fresh clone of mdsmithaustin/pstack at $repo, a CLI-agnostic port
of the pstack/ directory of cursor/plugins. The 'upstream' remote is fetched.
Last synced upstream commit: $recorded (in .github/upstream-sha). Latest
upstream commit touching pstack/: $latest.

PORTING.md at the repo root is the porting contract. Read it in full, then run
its "Syncing from upstream" procedure for $recorded..$latest. That procedure
and every list it points to remain required, including all local checks.

Facts this prompt adds:
- Use branch $branch. Publish it as a DRAFT PR to main
  with gh pr create --draft. GH_REPO is set to $REPO.
- The user explicitly authorizes bypassing no-mistakes ONLY to publish this
  scheduled sync branch, $branch, and create its draft PR in $REPO.
  This authorization does not relax any local check in PORTING.md. It does
  not authorize marking a PR ready, merging, pushing to main, force-pushing,
  or publishing any other branch or PR. All other publication rules remain.
- Publish every outcome as a draft PR, including a run where only
  .github/upstream-sha changes. Never push to main. Never force-push.
- Do not commit this prompt file; it lives outside the clone.
- If you are unsure whether a change is portable, include it in the draft PR
  with a "needs judgment" note rather than dropping it.
PROMPT
agent_status=0
claude -p --allowedTools "Bash,Read,Write,Edit,Glob,Grep" <"$prompt" >"$attempt/claude.log" 2>&1 || agent_status=$?
cat "$attempt/claude.log"
echo "claude run finished with exit $agent_status"
if [ "$agent_status" -ne 0 ]; then
  exit "$agent_status"
fi

if [ "$(git symbolic-ref --quiet --short HEAD)" != "$branch" ]; then
  echo "sync did not finish on $branch"
  exit 1
fi
head=$(git rev-parse --verify 'HEAD^{commit}')
if [ "$(cat .github/upstream-sha)" != "$latest" ] || [ "$(git show "$head:.github/upstream-sha")" != "$latest" ]; then
  echo "sync did not commit the intended upstream SHA $latest"
  exit 1
fi
status=$(git status --porcelain=v1 --untracked-files=all --ignore-submodules=none)
if [ -n "$status" ]; then
  echo "sync left uncommitted work"
  exit 1
fi

python3 - "$base" "$head" <<'PY'
import json
import subprocess
import sys

base, head = sys.argv[1:]
live_owners = {}
for revision in (base, head):
    try:
        ledger = json.loads(subprocess.check_output(
            ["git", "show", f"{revision}:evals/promises/ledger.json"],
        ))
        promises = ledger["promises"]
        if not isinstance(promises, dict):
            raise ValueError("promises must be a mapping")
        for promise_id, promise in promises.items():
            if not isinstance(promise, dict) or not isinstance(promise.get("check"), str):
                raise ValueError(f"invalid promise {promise_id}")
            if promise["check"] != "live":
                continue
            owners = promise["owners"]
            if not isinstance(owners, list) or not owners or any(
                not isinstance(owner, str) or not owner for owner in owners
            ):
                raise ValueError(f"invalid live owners for {promise_id}")
            for owner in owners:
                live_owners.setdefault(owner, set()).add(promise_id)
    except (subprocess.CalledProcessError, ValueError, KeyError, TypeError) as error:
        sys.exit(f"cannot verify committed promise ledger at {revision}: {error}")

changed = set(subprocess.check_output([
    "git", "diff", "--no-renames", "--name-only", "-z", base, head,
]).decode().split("\0"))
changed_owners = sorted(changed.intersection(live_owners))
if changed_owners:
    reports = subprocess.check_output([
        "git", "diff", "--no-renames", "--diff-filter=AM", "--name-only", "-z",
        base, head, "--", "evals/promises/results/",
    ]).decode().split("\0")
    for report in reports:
        if not report.endswith(".md"):
            continue
        previous_blob = subprocess.run(
            ["git", "rev-parse", "--verify", f"{base}:{report}"], capture_output=True,
        )
        current_blob = subprocess.check_output([
            "git", "rev-parse", "--verify", f"{head}:{report}",
        ])
        if previous_blob.returncode == 0 and previous_blob.stdout == current_blob:
            continue
        if subprocess.check_output(["git", "show", f"{head}:{report}"]).strip():
            break
    else:
        for owner in changed_owners:
            print(f"changed live promise owner {owner}: {', '.join(sorted(live_owners[owner]))}",
                  file=sys.stderr)
        sys.exit("sync lacks added or modified nonempty committed results Markdown under evals/promises/results/")
PY

gh api --method GET "repos/$REPO/pulls" -f state=open -f "head=${REPO%/*}:$branch" -f base=main >"$attempt/pull-requests.json"
python3 - "$attempt/pull-requests.json" "$REPO" "$branch" "$head" >"$attempt/verified-pr" <<'PY'
import json
import sys

path, repo, branch, head = sys.argv[1:]
with open(path, encoding="utf-8") as source:
    pulls = json.load(source)
matches = [pr for pr in pulls if (
    pr["base"]["repo"]["full_name"] == repo
    and pr["head"]["repo"]["full_name"] == repo
    and pr["base"]["ref"] == "main"
    and pr["head"]["ref"] == branch
    and pr["head"]["sha"] == head
    and pr["draft"] is True
    and pr["state"] == "open"
)]
if len(matches) != 1:
    sys.exit("sync lacks one open draft PR for the committed branch and SHA")
print(matches[0]["html_url"])
PY
mv "$attempt/verified-pr" "$attempt/complete"
echo "verified draft PR $(cat "$attempt/complete")"
