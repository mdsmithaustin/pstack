import sys
from pathlib import Path

from sync_job_loader import ConfigError, load_job


def main(folder="jobs"):
    for path in sorted(Path(folder).glob("*.json")):
        try:
            job = load_job(path)
        except ConfigError as error:
            print(f"skipped {path.name}: {error}")
            continue
        print(f"{path.stem}: sync {job['source']} -> {job['destination']} (keep {job['keep']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
