# Harness loading paths

Issue [254](https://github.com/mdsmithaustin/pstack/issues/254) splits harness instructions by action and runtime. The shared guide selects the procedure. A spawn adds shared role, isolation, fallback, and reporting instructions plus one runtime adapter. Transcript lookups select a separate location file, so they do not load spawn instructions.

The [source-byte receipts](pstack-harness-loading-paths.json) record every selected file and its exact UTF-8 byte count. They compare the declared loading contract against base `d3d8fd4d1354385390050a4e18e8cd579c565f75`. Its unsplit guide matches the issue's pinned `b5622490de2db0b32108bc071df32ae477f117fe` guide byte for byte.

These counts measure harness instruction source bytes. They do not measure provider tokens, billing, cache behavior, task quality, or actual agent file reads. Conditional external reads, such as the models config reference or a persona's own skill, are outside this harness-only comparison. Both revisions retain those conditions.

To reproduce one receipt, run this command from the repository root. A nonzero exit means the route, file, or baseline could not be read.

```sh
python3 skills/pstack-harness/scripts/loading-path.py --action worklist --baseline d3d8fd4d1354385390050a4e18e8cd579c565f75
```

For a runtime spawn, use `--action spawn --runtime codex`. The supported runtime names are `claude-code`, `codex`, `hermes`, `grok`, and `other`. Add `--persona` when the spawn needs a persona. That route includes the persona contract and its required portable-root instructions in both revisions. For a transcript lookup, use `--action transcript --runtime hermes`.

The action and runtime tables in `skills/pstack-harness/SKILL.md` own the routes. `tools/test_harness_loading_paths.py` invokes the receipt command and checks their normalized file sets, byte totals, and invalid-route failures. These are structural checks of an owned loading contract. They do not establish that a model follows the instructions.

The existing worklist check now reads the worklist procedure. The spelling exemption and three promise-ledger evidence paths follow their moved instructions. The public guide keeps the same delegation and verification contracts, so it needs no text change.
