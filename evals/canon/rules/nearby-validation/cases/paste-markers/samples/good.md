Fixed in `hermes_cli/input_sanitize.py`.

**Cause.** The degraded `[200~` form is only stripped after whitespace or punctuation, so that literal text such as `literal[200~tag` stays intact. Pasting right after a typed word puts a letter in front of the marker, so it survived.

**Fix.** A new `_GLUED_OPENING` pattern strips an opening `[200~` that follows any character, but only when a `[201~` closing marker follows it at a boundary. A glued paste always ends that way, and the literal case in the existing tests does not, so it is left alone.

**Verification.** `strip_leaked_bracketed_paste_wrappers("logs[200~Traceback ...[201~")` now returns `logsTraceback ...`. The whole `tests/hermes_cli/test_input_sanitize.py` and `tests/hermes_cli/test_cli_bracketed_paste_sanitizer.py` modules pass, including `test_does_not_strip_non_wrapper_bracket_forms_in_normal_text`.
