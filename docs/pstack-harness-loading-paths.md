# Harness loading paths

Issue [254](https://github.com/mdsmithaustin/pstack/issues/254) splits harness instructions by action and runtime. The shared guide selects the procedure. A spawn adds shared role, isolation, fallback, and reporting instructions plus the portable-root contract and one runtime adapter. Transcript lookups select a separate location file, so they do not load spawn instructions.

The [source-byte receipts](pstack-harness-loading-paths.json) record every selected file and its exact UTF-8 byte count. They compare the declared loading contract against base `d3d8fd4d1354385390050a4e18e8cd579c565f75`. Its unsplit guide matches the issue's pinned `b5622490de2db0b32108bc071df32ae477f117fe` guide byte for byte. The `after` counts follow the current files, so the test below fails when a harness edit changes one, and you regenerate that entry.

These counts measure harness instruction source bytes. They do not measure provider tokens, billing, cache behavior, task quality, or actual agent file reads. Conditional external reads, such as the models config reference or a persona's own skill, are outside this harness-only comparison. Both revisions retain those conditions.

To reproduce one receipt, run this command from the repository root. A nonzero exit means the route, file, or baseline could not be read.

```sh
python3 skills/pstack-harness/scripts/loading-path.py --action worklist --baseline d3d8fd4d1354385390050a4e18e8cd579c565f75
```

The baseline comparison reads the old guide from Git history, so it needs `git` and a checkout that contains the baseline commit. Without `--baseline`, the script prints a current-only report whose `baseline` and `before` are `null`. That works from an installed copy outside any checkout. A missing `git`, a checkout that git refuses because another user owns it, a copy outside a Git checkout, a baseline commit the checkout lacks, and a baseline that lacks a harness file each exit 1 with a separate error. The ownership error keeps git's `safe.directory` hint.

The script resolves its own path before it looks for the checkout. When a project links the skill directory to a copy elsewhere, `--baseline` reads the history of the repository that holds the link target, not the project's, and the errors name that directory. To compare against a commit, fetch it into the target's repository. To use the project's history, copy the skill into the project instead of linking it.

Run the script with `--help` for the valid `--action` values, which come from the action table in the guide, and what `--baseline` needs.

For a runtime spawn, use `--action spawn --runtime codex`. The supported runtime names are `claude-code`, `codex`, `hermes`, `grok`, and `other`. Add `--persona` when the spawn needs a persona. Every spawn includes portable-root instructions in both revisions because role resolution uses `PSTACK_SKILLS_ROOT`. A persona additionally includes the persona contract. For a transcript lookup, use `--action transcript --runtime hermes`.

The action and runtime tables in `skills/pstack-harness/SKILL.md` own the routes. `tests/skills/pstack-harness/scripts/test_loading_path.py` invokes the receipt command and checks their normalized file sets, the issue's pinned baseline byte total, worklist byte reduction, invalid-route failures, and the `--help` text. It also reruns every recorded receipt and fails when an entry differs from the script's current output. To regenerate an entry, run its command from the repository root and replace the entry with the printed report.

The same test file covers the repository cases. An installed copy outside any repository gives a current-only report, and with `--baseline` it reports the missing repository or the missing `git`. A copy in a new repository reports a commit it lacks and a baseline without the harness. A repository git treats as owned by another user reports that ownership refusal. A copy inside another repository compares against a commit from that repository, and a symlinked install compares against the symlink target's repository. A Git error that holds bytes outside UTF-8 still appears in the script's exit-1 message. Those runs set `LC_ALL=C` and ignore global and system Git config, and the test stages its copy with `git add --force`, so a maintainer's locale, hooks, or ignore files cannot change the result. These are structural checks of an owned loading contract. They do not establish that a model follows the instructions.

The existing worklist check now reads the worklist procedure. The spelling exemption and three promise-ledger evidence paths follow their moved instructions. The public guide keeps the same delegation and verification contracts, so it needs no text change.
