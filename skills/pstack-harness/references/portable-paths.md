# Portable resource paths

pstack playbooks use three independent absolute paths. `PSTACK_SKILLS_ROOT` contains the loaded `pstack-harness`, `poteto-mode`, `unslop`, and other installed sibling skills. `PSTACK_SOURCE_ROOT` is a verified checkout of `mdsmithaustin/pstack` for fresh pstack trunk reads. `PROJECT_ROOT` is the consumer repository for consumer-owned control skill reads. Never substitute one root for another. Resolve only the roots that the next command needs.

Keep concrete root values and whether `PSTACK_TEMP_ROOT` is set only in the program's private, untracked run state. A tracked or shared plan records the variable names and this setup contract, never machine-local absolute values. Run each resolver once per program or new execution environment. Later ticks and resumes restore both the source and ownership bindings, then run the fetch and read directly. They do not rerun source initialization because it resets `PSTACK_TEMP_ROOT`. Quote every expansion.

## Resolve the installed skills root

Set `PSTACK_HARNESS_SKILL` to the absolute logical path of this `pstack-harness/SKILL.md` as the session loaded or read it. Preserve that logical path even when the directory is a symlink. This block does not require a Git repository or network access. Use it for installed sibling files and local tools. Run the plan check with `node "${PSTACK_SKILLS_ROOT:?}/poteto-mode/scripts/check-plan.mjs" "$PLAN_PATH"`.

```sh
case "${PSTACK_HARNESS_SKILL:-}" in
	/*/pstack-harness/SKILL.md) ;;
	*) printf '%s\n' 'pstack: PSTACK_HARNESS_SKILL must be the absolute path of the loaded pstack-harness/SKILL.md' >&2; exit 1 ;;
esac
PSTACK_SKILLS_ROOT=$(CDPATH= cd -L -- "$(dirname -- "$PSTACK_HARNESS_SKILL")/.." && pwd -L) || exit 1
export PSTACK_SKILLS_ROOT
```

## Resolve the pstack source root

Initialize this block once per program or new execution environment, before the first fresh pstack trunk read. In the same execution environment, later ticks and resumes restore both `PSTACK_SOURCE_ROOT` and `PSTACK_TEMP_ROOT`, then run the documented fetch and read directly. Do not rerun this block because it resets `PSTACK_TEMP_ROOT`. Set `PSTACK_SOURCE_ROOT` before initialization when the program already has an explicit checkout. The block rejects a supplied checkout with the wrong origin. Without one, it considers the loaded skill's physical Git ancestry. A copied installation has no verified source ancestry, so the block creates a private shallow clone. Git URL rewrites in the host configuration are trusted transport settings. The configured `origin` value must still name the canonical repository.

```sh
PSTACK_TEMP_ROOT=
pstack_source_explicit=0
if [ -n "${PSTACK_SOURCE_ROOT:-}" ]; then
	pstack_source_explicit=1
else
	pstack_physical_skill_dir=$(CDPATH= cd -P -- "$(dirname -- "${PSTACK_HARNESS_SKILL:?}")" && pwd -P) || exit 1
	pstack_source_candidate=$(git -C "$pstack_physical_skill_dir" rev-parse --show-toplevel 2>/dev/null || true)
	pstack_candidate_origin=
	if [ -n "$pstack_source_candidate" ]; then
		pstack_candidate_origin=$(git -C "$pstack_source_candidate" config --get remote.origin.url 2>/dev/null || true)
	fi
	case "$pstack_candidate_origin" in
		https://github.com/mdsmithaustin/pstack|https://github.com/mdsmithaustin/pstack.git|git@github.com:mdsmithaustin/pstack|git@github.com:mdsmithaustin/pstack.git|ssh://git@github.com/mdsmithaustin/pstack|ssh://git@github.com/mdsmithaustin/pstack.git)
			PSTACK_SOURCE_ROOT=$pstack_source_candidate
			;;
	esac
fi
if [ -z "${PSTACK_SOURCE_ROOT:-}" ]; then
	PSTACK_TEMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/pstack-source.XXXXXX") || {
		printf '%s\n' 'pstack: could not create a private directory for canonical pstack source' >&2
		exit 1
	}
	if ! git clone --depth 1 --branch main --single-branch 'https://github.com/mdsmithaustin/pstack.git' "$PSTACK_TEMP_ROOT/source"; then
		printf '%s\n' 'pstack: could not clone canonical pstack source' >&2
		rm -rf -- "$PSTACK_TEMP_ROOT"
		exit 1
	fi
	PSTACK_SOURCE_ROOT=$PSTACK_TEMP_ROOT/source
	printf '%s\n' "$PSTACK_SOURCE_ROOT" > "$PSTACK_TEMP_ROOT/.pstack-program-owned"
fi
case "$PSTACK_SOURCE_ROOT" in
	/*) ;;
	*) printf '%s\n' 'pstack: PSTACK_SOURCE_ROOT must be absolute' >&2; exit 1 ;;
esac
pstack_origin=$(git -C "$PSTACK_SOURCE_ROOT" config --get remote.origin.url 2>/dev/null || true)
case "$pstack_origin" in
	https://github.com/mdsmithaustin/pstack|https://github.com/mdsmithaustin/pstack.git|git@github.com:mdsmithaustin/pstack|git@github.com:mdsmithaustin/pstack.git|ssh://git@github.com/mdsmithaustin/pstack|ssh://git@github.com/mdsmithaustin/pstack.git) ;;
	*)
		printf '%s\n' 'pstack: PSTACK_SOURCE_ROOT does not have the canonical mdsmithaustin/pstack origin' >&2
		[ "$pstack_source_explicit" -eq 1 ] || rm -rf -- "$PSTACK_TEMP_ROOT"
		exit 1
		;;
esac
if ! git -C "$PSTACK_SOURCE_ROOT" fetch origin '+refs/heads/main:refs/remotes/origin/main'; then
	printf '%s\n' 'pstack: could not fetch canonical pstack main' >&2
	[ -z "$PSTACK_TEMP_ROOT" ] || rm -rf -- "$PSTACK_TEMP_ROOT"
	exit 1
fi
if ! git -C "$PSTACK_SOURCE_ROOT" cat-file -e 'origin/main:skills/pstack-harness/SKILL.md'; then
	printf '%s\n' 'pstack: canonical pstack main lacks skills/pstack-harness/SKILL.md' >&2
	[ -z "$PSTACK_TEMP_ROOT" ] || rm -rf -- "$PSTACK_TEMP_ROOT"
	exit 1
fi
export PSTACK_SOURCE_ROOT PSTACK_TEMP_ROOT
```

A fresh pstack trunk read fetches the exact remote-tracking ref before it reads the object. For example, use `git -C "${PSTACK_SOURCE_ROOT:?}" fetch origin '+refs/heads/main:refs/remotes/origin/main' && git -C "$PSTACK_SOURCE_ROOT" show 'origin/main:skills/poteto-mode/playbooks/autopilot-full.md'`. A fetch, clone, identity, or object failure stops the read. Installed bytes are not a fallback for pstack trunk.

## Resolve the consumer project root

Run this block only before reading a consumer-owned control skill. It uses the current directory unless the program restores an existing `PROJECT_ROOT`. Read the skill with `git -C "${PROJECT_ROOT:?}" show "origin/main:$CONTROL_SKILL_PATH"`.

```sh
PROJECT_ROOT=$(git -C "${PROJECT_ROOT:-.}" rev-parse --show-toplevel 2>/dev/null) || {
	printf '%s\n' 'pstack: PROJECT_ROOT is not a Git worktree' >&2
	exit 1
}
export PROJECT_ROOT
```

## Clean up a program-owned source clone

Run this block after the program stops, and only when that program created `PSTACK_TEMP_ROOT`. Never remove an installed skill root, an explicit source checkout, or the consumer project.

```sh
if [ -n "${PSTACK_TEMP_ROOT:-}" ]; then
	case "$(basename -- "$PSTACK_TEMP_ROOT")" in
		pstack-source.??????) ;;
		*) printf '%s\n' 'pstack: refusing to remove a source root without the generated pstack-source name' >&2; exit 1 ;;
	esac
	[ "${PSTACK_SOURCE_ROOT:-}" = "$PSTACK_TEMP_ROOT/source" ] || {
		printf '%s\n' 'pstack: refusing to remove a source root that does not own the exact source child' >&2
		exit 1
	}
	[ -f "$PSTACK_TEMP_ROOT/.pstack-program-owned" ] &&
		[ "$(cat "$PSTACK_TEMP_ROOT/.pstack-program-owned")" = "$PSTACK_SOURCE_ROOT" ] || {
		printf '%s\n' 'pstack: refusing to remove a source root without its ownership marker' >&2
		exit 1
	}
	rm -rf -- "$PSTACK_TEMP_ROOT"
fi
```
