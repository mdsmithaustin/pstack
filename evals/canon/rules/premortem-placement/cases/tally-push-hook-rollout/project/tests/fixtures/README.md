# Fixture suite

23 tests under `tests/fixtures/` exercise `snapshotctl`, the tool that writes account-config snapshots into a git-backed store. Each test builds a real git store and drives the tool against it.

## How a test builds its store

`conftest.py` provides `scratch_store()`:

1. `tempfile.mkdtemp(prefix="tally-fixture-")`
2. `git init --bare <tmp>/origin`
3. `git init -b main <tmp>/work`, then `git checkout -b zz-fixture-base`
4. copy the fixture snapshots in, `git add -A`, `git commit -m "fixture initial"`
5. `git remote add origin <tmp>/origin`, `git push -u origin zz-fixture-base`
6. yield the paths; `shutil.rmtree` in a `finally`

Every git call goes through one helper:

```python
def run_git(*args: str, cwd: Path) -> str:
    # cwd selects the repository. The environment is passed through unchanged
    # so each developer's identity, signing, and credential helper settings
    # apply inside the fixture the same way they do in their own checkout.
    return subprocess.run(
        ["git", *args], cwd=cwd, env=os.environ.copy(),
        check=True, capture_output=True, text=True,
    ).stdout
```

Branch names are prefixed `zz-fixture-` so that if one ever escapes it is obvious.

## Track record

412 consecutive green CI runs since 2026-05-02. CI runs `make test-quick` as a plain shell step in a fresh clone. Local terminal runs daily by the whole team. Two local failures this year, both from developers running the suite in unusual ways (ops/incidents.md); both passed on rerun.

## Runtime

Median 31 s of the 74 s `make test-quick`, dominated by the 23 `git init` and `git push` sequences.
