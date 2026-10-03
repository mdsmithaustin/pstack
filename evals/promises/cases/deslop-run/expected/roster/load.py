import csv


def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if row["name"]]
