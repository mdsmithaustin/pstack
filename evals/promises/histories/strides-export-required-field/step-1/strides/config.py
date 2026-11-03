from pathlib import Path

LOG_PREFIX = "log://"


class ConfigError(Exception):
    pass


def log_path(value, base):
    if not value.startswith(LOG_PREFIX) or value == LOG_PREFIX:
        raise ConfigError(f"log must start with {LOG_PREFIX} and name a file")
    return base / value[len(LOG_PREFIX):]


FIELDS = {"log": log_path}


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
    return settings
