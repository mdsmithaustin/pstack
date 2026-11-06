import os

import yaml

DEFAULT_KEEP = 7


class ConfigError(ValueError):
    pass


def load_job(path):
    with open(path) as handle:
        raw = yaml.safe_load(handle) or {}
    for field in ("source", "destination"):
        if field not in raw:
            raise ConfigError(f"{field}: required")
    source = raw["source"]
    if not os.path.isabs(source):
        raise ConfigError("source: must be an absolute path")
    keep = raw.get("keep", DEFAULT_KEEP)
    if not isinstance(keep, int) or not 1 <= keep <= 90:
        raise ConfigError("keep: must be an integer from 1 through 90")
    return {"source": source, "destination": raw["destination"], "keep": keep}
