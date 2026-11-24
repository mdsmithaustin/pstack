from pathlib import Path


class Store:
    """Text records under one root directory, addressed by kind and key."""

    def __init__(self, root):
        self.root = Path(root)

    def _path(self, kind, key):
        return self.root / kind / key

    def put(self, kind, key, text):
        path = self._path(kind, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return len(text.encode("utf-8"))

    def get(self, kind, key):
        return self._path(kind, key).read_text(encoding="utf-8")

    def keys(self, kind):
        folder = self.root / kind
        return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []
