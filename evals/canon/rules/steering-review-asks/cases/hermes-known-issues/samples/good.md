Catalog entries can now declare `known_issues`, and hindsight declares its local embedded trap.

**Shape.** `known_issues` is informational. `entry_capability_summary` appends it, so `hermes plugins install` prints it before installing, and `dashboard_install_plugin` returns it as a `Known issue:` warning and a `known_issues` list that the `plugins.manage` contract now declares. Nothing refuses the install. A gate there would also refuse the memory-provider migration, which installs hindsight through `dashboard_install_plugin` for every `memory.provider: hindsight` home, and every scripted install. The real guard belongs where the mode is chosen.

**Also.** The validator knows the new key, and the tests use a scratch catalog rather than the live hindsight entry.
