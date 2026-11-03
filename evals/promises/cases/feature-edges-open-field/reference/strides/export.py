from pathlib import Path

from strides.config import EXPORT_PREFIX, MUTANT, ConfigError


def write_export(out, export, rows):
    if MUTANT == "open-scheme-out" and not export.startswith(EXPORT_PREFIX):
        raise ConfigError(f"export must start with {EXPORT_PREFIX}")
    folder = Path(out) / export.partition("://")[2]
    folder.mkdir(parents=True, exist_ok=True)
    for name, km in rows:
        (folder / f"{name}.txt").write_text(f"{name}: {km:.1f} km\n", encoding="utf-8")
