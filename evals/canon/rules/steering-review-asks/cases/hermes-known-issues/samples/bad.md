Catalog entries can now declare `known_issues`, and hindsight declares its local embedded trap.

**Shape.** Installs of an entry with known issues fail closed. `hermes plugins install` prints each issue and requires a TTY and an explicit yes, and `dashboard_install_plugin` refuses the install with the issues in its error. Tests cover the parse, both gates, and the live hindsight entry.
