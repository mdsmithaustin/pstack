The loop now lives in `dev/lint/_framework.py` as `report_file_hits(argv, scan, label, footer)`. Each script's `main` is one call that passes its label and footer.

Both scripts still exit 1 on a dirty file and 0 on a clean one, and the existing exit-code tests pass.
