# Repository rulesets

`copilot-code-review.json` records the desired default-branch ruleset. It asks Copilot to review every pull request, including drafts, and to review again after each push. It permits merge, squash, and rebase after the required GitHub Actions `skills` check succeeds. The rule requires a pull request, no human approvals, resolved review threads, stale-review dismissal after a push, and protection from deletion or force pushes.

Do not create a second ruleset. Update existing ruleset `22124319` only after the pull request has a successful `skills` check for its exact head from GitHub Actions app `15368`.

Run this from a clean checkout of the reviewed pull-request head after setting `PR_NUMBER` to its number. Each guard exits nonzero on failure, so it stops before the PUT.

```bash
set -euo pipefail
repository=mdsmithaustin/pstack
ruleset=22124319
pr=${PR_NUMBER:?set PR_NUMBER to the reviewed pull-request number}
workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT
head=$(git rev-parse HEAD)
test "$(git status --porcelain)" = ""
gh pr view "$pr" --repo "$repository" --json headRefOid --jq '.headRefOid' > "$workdir/pr-head"
test "$(<"$workdir/pr-head")" = "$head"
gh api "repos/$repository/commits/$head/check-runs?per_page=100" > "$workdir/check-runs.json"
jq -e --arg head "$head" '
  any(.check_runs[]; .name == "skills" and .head_sha == $head and .conclusion == "success" and .app.id == 15368)
' "$workdir/check-runs.json" >/dev/null
gh api "repos/$repository/rulesets/$ruleset" > "$workdir/ruleset-before.json"
jq -e --slurpfile desired .github/rulesets/copilot-code-review.json '
  .enforcement == "active" and
  .conditions.ref_name.include == ["~DEFAULT_BRANCH"] and
  all(.rules[]; .type as $type | any($desired[0].rules[]; .type == $type))
' "$workdir/ruleset-before.json" >/dev/null
jq -s '.[1] + {bypass_actors: .[0].bypass_actors}' \
  "$workdir/ruleset-before.json" .github/rulesets/copilot-code-review.json > "$workdir/ruleset-put.json"
gh api --method PUT "repos/$repository/rulesets/$ruleset" --input "$workdir/ruleset-put.json" > "$workdir/ruleset-put-response.json"
gh api "repos/$repository/rulesets/$ruleset" > "$workdir/ruleset-after.json"
jq -e --slurpfile expected "$workdir/ruleset-put.json" '
  .name == $expected[0].name and
  .target == $expected[0].target and
  .enforcement == $expected[0].enforcement and
  .conditions == $expected[0].conditions and
  .bypass_actors == $expected[0].bypass_actors and
  ([.rules[] | {type, parameters}] | sort_by(.type)) ==
  ([$expected[0].rules[] | {type, parameters}] | sort_by(.type))
' "$workdir/ruleset-after.json" >/dev/null
default_branch=$(gh api "repos/$repository" --jq '.default_branch')
gh api "repos/$repository/rules/branches/$default_branch" > "$workdir/effective-default-branch-rules.json"
```

The temporary directory holds the readback record until the command exits. The fresh GET preserves bypass actors and stops if the live ruleset contains an unowned rule type. Do not run the PUT from CI or a local hook.
