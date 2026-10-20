# Historical evaluation source

The canon screens, placement comparisons, stub arms, and process census are
frozen research. Their complete source remains at commit
`7a9a3ddb0118b8026f16a7820bbd0ff65db60df2`, including all 68 configurations,
their fixtures, original graders, tests, and historical README. They are no
longer part of the maintained source or normal test discovery.

[`canon.json`](canon.json) records that commit's canon tree identity, original
file count, configuration names, and the original paths retained in the active
core. The archived set is the original tree minus those retained paths.
The original versions of retained paths are also recoverable from the pin.

This preserves source, not an assertion that every historical runtime still
works. Raw traces and private reports remain in their existing external stores.
Published port-value and promise results, pipeline closure, and their recorded
hashes are unchanged. A new grader must not silently replace a historical grade.

## Recover the original source

Run these commands from a full repository checkout. A nonzero exit is a failed
recovery. If the commit is absent, obtain the repository history before proceeding.

```sh
git cat-file -e 7a9a3ddb0118b8026f16a7820bbd0ff65db60df2^{commit}
git show 7a9a3ddb0118b8026f16a7820bbd0ff65db60df2:evals/canon/README.md
```

For the original directory layout and callers, create a separate detached checkout.
Do not copy old controllers into the maintained tree.

```sh
replay_root=$(mktemp -d)
git worktree add --detach "$replay_root/source" 7a9a3ddb0118b8026f16a7820bbd0ff65db60df2
```

A nonzero exit means checkout recovery failed. Follow the pinned README's
runtime and evidence requirements. Recovery alone grants no study calls,
replacement slots, Docker changes, or confirmation budget. Preserve any new
output before normal worktree cleanup.

The maintained archive check runs through the real `git archive` interface:

```sh
python3 -m unittest discover -s evals/canon -p test_archive.py -v
```

A nonzero exit, failed test, or zero-test summary means preservation was not
verified. This checks recoverable source and the declared active/archive split,
not model quality, historical results, or native runtime compatibility.
