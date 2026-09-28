Fixed in `hermes_cli/completion.py`.

**Cause.** When compinit autoloads `_hermes` from your fpath, the first TAB runs the whole file as the body of `_hermes`. The generated file only defined the functions and ended with `compdef _hermes hermes`, so that first call registered the completer and returned without completing anything. The second TAB called the function the file had just defined.

**Fix.** The script now ends by checking `${funcstack[1]}`. Autoloaded as `_hermes`, it calls `_hermes "$@"` so the first TAB completes. Sourced with `eval "$(hermes completion zsh)"`, as the script's own header and git history show people install it, it still runs `compdef _hermes hermes`. An earlier version ended with a bare `_hermes "$@"`, which broke that eval install, and 8c4bec6155 swapped it for `compdef`.

**Verification.** A fresh `zsh -f -i` with the file on fpath lists the subcommands on the first TAB, and one that runs `eval "$(hermes completion zsh)"` does too, with no error at startup. `tests/hermes_cli/test_completion.py` passes.
