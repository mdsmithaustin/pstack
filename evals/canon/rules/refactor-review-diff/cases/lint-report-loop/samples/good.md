The loop now lives in `dev/lint/_framework.py` as `report_file_hits(argv, scan, format_hit, footer)`. Each script's `main` is one call.

- `lint_no_skipped_tests.py` formats a hit as `path:line: message`.
- `lint_no_global_asyncio_patch.py` formats a hit as its detection line followed by its `hint:` line, so each hit still prints both lines.
- Both footers moved to module constants with the same text.

I ran both scripts on the same dirty and clean files before and after the change and diffed stdout and exit codes. They match byte for byte.
