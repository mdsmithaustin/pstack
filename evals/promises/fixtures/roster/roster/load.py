import csv


def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
