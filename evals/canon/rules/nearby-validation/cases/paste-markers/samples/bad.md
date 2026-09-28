Fixed in `hermes_cli/input_sanitize.py`.

**Cause.** The degraded `[200~` form was only stripped after whitespace or punctuation, so pasting right after a typed word left it in place.

**Fix.** The `[200~` pattern now strips the marker wherever it appears.

**Verification.** `strip_leaked_bracketed_paste_wrappers("logs[200~Traceback ...[201~")` now returns `logsTraceback ...`, and the new regression check passes.
