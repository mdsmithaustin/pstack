from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Run:
    day: date
    time: str
    km: float
    name: str


def parse_line(line):
    day, time, km, name = line.split(maxsplit=3)
    return Run(date.fromisoformat(day), time, float(km), name.strip())


def read_runs(path):
    runs = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#"):
                runs.append(parse_line(line))
    return runs
