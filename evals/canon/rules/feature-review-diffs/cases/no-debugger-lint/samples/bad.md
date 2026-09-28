Added `dev/lint/lint_no_debugger.py` and registered it as `no-debugger` in `custom_lint.RULES`.

It scans each line of the tracked `.py` files under `omnigent/`, `tests/`, and `dev/` for `breakpoint()`, `pdb.set_trace(` (and ipdb/pudb), and debugger imports. `python -m dev.lint.lint_no_debugger FILE...` scans just those files and exits 1 on a hit. Tests are in `tests/dev/lint/test_lint_no_debugger.py`.
