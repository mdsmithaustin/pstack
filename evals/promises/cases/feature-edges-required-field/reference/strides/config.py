import os
from pathlib import Path

# The held-out script runs the delivered tests against a mutant of this reference, chosen by STRIDES_MUTANT.
# `open-scheme` checks the export scheme while the config loads. `open-scheme-out` checks it when the files are written.
MUTANT = os.environ.get("STRIDES_MUTANT", "")
LOG_PREFIX = "log://"
EXPORT_PREFIX = "report://"


class ConfigError(Exception):
    pass


def log_path(value, base):
    if not value.startswith(LOG_PREFIX) or value == LOG_PREFIX:
        raise ConfigError(f"log must start with {LOG_PREFIX} and name a file")
    return base / value[len(LOG_PREFIX):]


def export_path(value, base):
    if MUTANT == "open-scheme" and not value.startswith(EXPORT_PREFIX):
        raise ConfigError(f"export must start with {EXPORT_PREFIX}")
    if not value.partition("://")[2]:
        raise ConfigError("export must name a folder after ://")
    return value


FIELDS = {"log": log_path, "export": export_path}


def read_config(path):
    path = Path(path)
    settings = {}
    with open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, colon, value = line.partition(":")
            key = key.strip()
            if not colon:
                raise ConfigError(f"{path.name} line {number}: expected key: value")
            if key not in FIELDS:
                raise ConfigError(f"{path.name} line {number}: unknown key {key}")
            try:
                settings[key] = FIELDS[key](value.strip(), path.parent)
            except ConfigError as error:
                raise ConfigError(f"{path.name} line {number}: {error}") from None
    if "export" not in settings:
        raise ConfigError(f"{path.name}: export is required")
    return settings
