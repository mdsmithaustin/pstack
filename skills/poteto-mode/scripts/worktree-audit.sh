#!/usr/bin/env bash
# Read-only worktree prune audit. Classifies every git worktree by size, merge
# state, uncommitted work, kept files, remote/PR state, and the most recent chat
# that operated in it. Emits a table sorted by size with a suggested bucket,
# then one "# kept: <path>" line per kept file. Never deletes anything; deletion
# stays a human-gated step in the playbook.
#
# `git worktree remove` deletes ignored files even without --force, so kept
# paths must block the safe bucket. Nested checkouts need a separate scan
# because the outer repository never lists their ignored files.
# See ../playbooks/worktree-cleanup.md, steps 4 and 5, for the DIRTY contract,
# cache exclusions, nested-path coverage, and removal guard.
#
# Usage: worktree-audit.sh [-b|--base <ref>] [repo-path]
#   repo-path defaults to the current repo.
#   -b sets the ref the MERGED column checks against (e.g. origin/integration).
#   Without it the base is origin/HEAD, then origin/main, then origin/master.
#   origin/HEAD is the remote's default branch, not necessarily the branch PRs
#   merge into; pass -b when they differ.
# Requires python3, rg, and jq.
set -uo pipefail

base=""
while [ $# -gt 0 ]; do
	case "$1" in
	-b|--base) [ $# -ge 2 ] || { echo "error: $1 needs a ref" >&2; exit 2; }; base="$2"; shift 2 ;;
	-h|--help) sed -n '2,/^set -uo pipefail/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
	-*) echo "error: unknown option: $1" >&2; exit 2 ;;
	*) break ;;
	esac
done

repo="${1:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$repo" ] && { echo "not in a git repo; pass a repo path" >&2; exit 1; }
cd "$repo" || exit 1
git rev-parse --git-dir >/dev/null 2>&1 || { echo "error: not a git repo: $repo" >&2; exit 1; }

# Main worktree is the first entry; everything else is a candidate.
main_wt=$(git worktree list --porcelain | sed -n 's/^worktree //p' | head -1)

if [ -z "$base" ]; then
	for cand in "$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null)" origin/main origin/master; do
		[ -n "$cand" ] && git rev-parse --verify --quiet "$cand^{commit}" >/dev/null && { base="$cand"; break; }
	done
	[ -z "$base" ] && { echo "error: no base ref (origin/HEAD, origin/main, origin/master all missing); pass -b <ref>" >&2; exit 1; }
	echo "warn: no -b given; MERGED checks against $base" >&2
fi

# The base drives the merge check. The fetch is best-effort (stale is fine for
# a first pass) and runs before the check, since -b may name a branch not
# fetched yet. The explicit refspec creates it even in a single-branch clone.
case "$base" in
origin/*) git fetch origin "+refs/heads/${base#origin/}:refs/remotes/$base" --quiet 2>/dev/null \
	|| echo "warn: could not fetch $base; merged column may be stale" >&2 ;;
esac
git rev-parse --verify --quiet "$base^{commit}" >/dev/null 2>&1 || { echo "error: base ref not found: $base" >&2; exit 1; }

# PR state by branch, fetched once as [{number, state, head}] with a lowercase
# state. Origin when its CLI can read this repo's PRs, otherwise gh against the
# audited origin repository. Empty when neither can.
prs=$(mktemp)
kept_paths=$(mktemp)
status_out=$(mktemp)
nested_out=$(mktemp)
index_out=$(mktemp)
trap 'rm -f "$prs" "$kept_paths" "$status_out" "$nested_out" "$index_out"' EXIT
pr_repo=$(python3 - "$(git remote get-url origin 2>/dev/null)" <<'PY'
import re
import sys
from urllib.parse import urlsplit

remote = sys.argv[1].strip()
if re.search(r"[\s\\%?#]", remote):
    sys.exit(0)
scp = re.fullmatch(r"git@([^:/]+):([^:]+)", remote) if "://" not in remote else None
if scp:
    remote = f"https://{scp[1]}/{scp[2]}"
match = re.fullmatch(r"(?:https://[^/:@]+|ssh://git@[^/:@]+)(/[a-z\d_.-]+/[a-z\d_.-]+/?)", remote, re.I)
if not match:
    sys.exit(0)
url = urlsplit(remote)
host = url.hostname or ""
parts = re.sub(r"\.git$", "", url.path.rstrip("/")).lstrip("/").split("/")
if not re.fullmatch(r"[a-z\d](?:[a-z\d.-]*[a-z\d])?", host, re.I) or any(part in ("", ".", "..") for part in parts):
    sys.exit(0)
print(f"{host}/{'/'.join(parts)}")
PY
) || pr_repo=""
if command -v origin >/dev/null 2>&1 \
	&& raw=$(origin pr list --author "@me" --state all --limit 1000 \
		--json number,status,headRef 2>/dev/null); then
	printf '%s' "$raw" | jq '[.[] | {number, state: .status, head: .headRef}]' > "$prs" 2>/dev/null
elif [ -n "$pr_repo" ] && raw=$(gh pr list --repo "$pr_repo" --author "@me" --state all --limit 1000 \
	--json number,state,headRefName 2>/dev/null); then
	printf '%s' "$raw" | jq '[.[] | {number, state: (.state | ascii_downcase), head: .headRefName}]' > "$prs" 2>/dev/null
fi
[ -s "$prs" ] || echo "[]" > "$prs"

# Transcript stores, per CLI. Claude Code slugs the workspace path by turning
# every character that isn't a letter or digit into "-"; Codex keeps a flat
# date tree.
slug=$(printf '%s' "$main_wt" | sed 's/[^a-zA-Z0-9]/-/g')
transcripts="$HOME/.claude/projects/$slug"
[ -d "$transcripts" ] || transcripts="${CODEX_HOME:-$HOME/.codex}/sessions"
now=$(date +%s)

is_build_cache() {
	local name=${1%/}
	case "${name##*/}" in
	node_modules|.venv|venv|__pycache__|*.pyc|.pytest_cache|.mypy_cache|.ruff_cache|.tox|dist|build|target|.next|.turbo|.parcel-cache|.gradle|.DS_Store) return 0 ;;
	*) return 1 ;;
	esac
}

echo "# base: $base"
printf "SIZE\tAGE\tMERGED\tDIRTY\tREMOTE\tPR\tLAST_CHAT\tBUCKET\tWORKTREE\n"

git worktree list --porcelain | sed -n 's/^worktree //p' | while IFS= read -r wt; do
	[ "$wt" = "$main_wt" ] && continue

	size=$(du -sh "$wt" 2>/dev/null | awk '{print $1}')
	head=$(git -C "$wt" rev-parse HEAD 2>/dev/null)
	head_ts=$(git -C "$wt" log -1 --format='%ct' HEAD 2>/dev/null || echo 0)
	age=$([ "$head_ts" -gt 0 ] 2>/dev/null && echo "$(( (now - head_ts) / 86400 ))d" || echo "?")

	# Squash-merged branches are not ancestors of the base, so PR state is the
	# real signal; merge-base only catches fast-forward/rebase merges.
	git merge-base --is-ancestor "$head" "$base" 2>/dev/null && merged=YES || merged=no

	wip=0 kept=0 dirty=""
	covering=()
	if git -C "$wt" status --porcelain -z --ignored=matching --untracked-files=normal --ignore-submodules=none > "$status_out" 2>/dev/null \
		&& git -C "$wt" ls-files -v -z > "$index_out" 2>/dev/null \
		&& find "$wt" -mindepth 2 -name .git -prune -print0 > "$nested_out" 2>/dev/null; then
		while IFS= read -r -d '' entry; do
			case "${entry:0:2}" in
			'??'|'!!')
				path="$wt/${entry:3}"
				if [ "${entry:0:2}" = '!!' ] && is_build_cache "${entry:3}"; then
					continue
				fi
				kept=$((kept + 1)); printf '# kept: %s\n' "$path" >> "$kept_paths"
				covering+=("$path") ;;
			R?|?R|C?|?C) wip=$((wip + 1)); IFS= read -r -d '' _ ;;
			*) wip=$((wip + 1)) ;;
			esac
		done < "$status_out"
		# Status hides edits to skip-worktree (S) and assume-unchanged (lowercase) entries.
		while IFS= read -r -d '' entry; do
			case "${entry:0:1}" in
			S|[[:lower:]]) [ -e "$wt/${entry:2}" ] || [ -L "$wt/${entry:2}" ] && wip=$((wip + 1)) ;;
			esac
		done < "$index_out"
		while IFS= read -r -d '' nested; do
			dir="${nested%/.git}/"
			for c in ${covering[@]+"${covering[@]}"}; do
				case "$c" in */) case "$dir" in "$c"*) continue 2 ;; esac ;; esac
			done
			kept=$((kept + 1)); printf '# kept: %s\n' "$dir" >> "$kept_paths"
		done < "$nested_out"
		[ "$wip" -gt 0 ] && dirty="wip:$wip"
		[ "$kept" -gt 0 ] && dirty="${dirty:+$dirty,}kept:$kept"
	else dirty=unreadable; fi
	dirty=${dirty:-clean}

	branch=$(git -C "$wt" symbolic-ref --quiet --short HEAD 2>/dev/null || echo "")
	if [ -z "$branch" ]; then remote=detached
	elif git -C "$wt" show-ref --verify --quiet "refs/remotes/origin/$branch"; then
		[ "$(git -C "$wt" rev-parse "origin/$branch" 2>/dev/null)" = "$head" ] \
			&& remote=pushed \
			|| remote="ahead$(git -C "$wt" rev-list --count "origin/$branch..HEAD" 2>/dev/null)"
	else remote=no-remote; fi

	pr=$([ -n "$branch" ] && jq -r --arg b "$branch" \
		'.[] | select(.head==$b) | "#\(.number)/\(.state)"' "$prs" 2>/dev/null | head -1)
	[ -z "$pr" ] && pr="-"

	# Most recent chat whose transcript operated in this worktree. Match path
	# followed by "/" or a quote so glint-482 does not match glint-482-r37.
	# Case-insensitive because transcripts on case-insensitive disks can spell
	# the path in another case.
	last="-"; recent=no
	if [ -d "$transcripts" ]; then
		matches=$(rg -l -F -i -e "${wt}/" -e "${wt}\"" "$transcripts" 2>/dev/null || :)
		chat=$(printf '%s\n' "$matches" | python3 -c '
import datetime
import os
import sys

last_ts = 0
for path in sys.stdin.read().splitlines():
    if not path:
        continue
    try:
        mtime = os.stat(path).st_mtime
    except FileNotFoundError:
        continue
    last_ts = max(last_ts, int(mtime))
last = datetime.datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d") if last_ts > 0 else "-"
recent = last_ts > 0 and int((int(sys.argv[1]) - last_ts) / 86400) <= 4
print(last, "yes" if recent else "no", sep="\t")
' "$now") || exit $?
		IFS=$'\t' read -r last recent <<< "$chat"
	fi

	case "$dirty" in wip:*) bucket=hold-wip ;; kept:*|unreadable) bucket=hold-kept ;; *)
		case "$pr" in */open|*/draft) bucket=hold-open-pr ;; *)
			if [ "$recent" = yes ]; then bucket=verify-recent-chat
			elif [ "$merged" = YES ] || [ "$pr" != "-" ]; then bucket=safe
			else bucket=review; fi ;;
		esac ;;
	esac

	printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
		"$size" "$age" "$merged" "$dirty" "$remote" "$pr" "$last" "$bucket" "$wt"
done | sort -t$'\t' -k1,1 -rh || exit $?
cat "$kept_paths"
