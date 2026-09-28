Added `dev/lint/lint_no_debugger.py` and registered it as `no-debugger`, third in `custom_lint.RULES`.

- **Detection.** An AST walk flags `breakpoint()`, `pdb`/`ipdb`/`pudb` `.set_trace()` calls, and `import`/`from ... import` of those modules. Strings, comments, and names like `breakpoints` never match.
- **Suppression.** Hits on a line carrying `# custom-lint: disable=no-debugger` are dropped through `disabled_rules_by_line`.
- **Surface.** `check()` scans tracked `.py` files under `omnigent/`, `tests/`, and `dev/`. `python -m dev.lint.lint_no_debugger FILE...` scans just those files, prints `path:line: ...` per hit, and exits 1, or exits 0 when clean.
- **Tests.** `tests/dev/lint/test_lint_no_debugger.py` covers each shape, strings and comments, the disable comment, exit codes, and registration. The repo is clean under the new rule.
