# Settings loader requirements

SL-501. The loader reads a project's settings file written in YAML, TOML, or JSON. `timeout_seconds` is an integer from 1 through 300, inclusive. A value outside that range is rejected. A field whose value is empty falls back to its default.

SL-502. A user settings file overrides the project settings file field by field. Example: the loader reads `project.toml` with `log_level = "info"` and `retries = 3`, then reads `user.toml` with `log_level = "debug"`. The loaded settings are `log_level = "debug"` and `retries = 3`.
