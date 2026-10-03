import os

from . import csv_source, json_source

LOADERS = {
    ".json": json_source.load,
    ".csv": csv_source.load,
}


def load(path):
    suffix = os.path.splitext(path)[1].lower()
    try:
        loader = LOADERS[suffix]
    except KeyError:
        raise ValueError(f"no loader for {suffix or 'files without a suffix'}") from None
    return loader(path)
