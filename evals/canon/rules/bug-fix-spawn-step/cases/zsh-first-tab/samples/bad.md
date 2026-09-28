Fixed in `hermes_cli/completion.py`.

**Cause.** An autoloaded completion file runs as the body of its function on the first TAB. The generated file ended with `compdef _hermes hermes`, which only registers the completer, so the first TAB completed nothing.

**Fix.** The file now ends with `_hermes "$@"`, the usual last line of a zsh completion file, so the first call completes.

**Verification.** With the file on fpath, the first `hermes <TAB>` lists the subcommands, and `tests/hermes_cli/test_completion.py` passes.
