Fixed the Windows boot loop in `hermes_cli/main_desktop.py`.

**Fix.** The Desktop ancestor is spared on every platform, and a Windows packaged build under its own Desktop is skipped with a notice to quit and run `hermes desktop` from a terminal.

**Tests.** Regression tests patch `sys.platform` to cover the Windows and POSIX paths.
