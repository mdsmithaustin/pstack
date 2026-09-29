Fixed the Windows boot loop in `hermes_cli/main_desktop.py`.

**Cause.** `_stop_desktop_processes_locking_build` spared a Desktop ancestor only on POSIX, so the launch-time update tail killed the Desktop it ran under before it cleared its markers.

**Fix.** The ancestor and its helpers are spared on every platform. A Windows packaged build under its own Desktop is skipped, since the exe lock would refuse the promotion anyway, and the notice says to quit and run `hermes desktop` from a terminal or use Update now in Settings, About. `hermes desktop` on that path reopens the app it kept instead of reporting that no app was found.

**Tests.** The Windows rows carry `@pytest.mark.platforms("windows")`, per AGENTS.md, instead of patching `sys.platform`.
