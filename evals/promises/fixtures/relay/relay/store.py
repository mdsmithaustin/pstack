import os


class Store:
    def __init__(self, root):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def write(self, record):
        path = os.path.join(self.root, f"{record.id}.txt")
        with open(path, "w", encoding="utf-8") as handle:
            for key in sorted(record.fields):
                handle.write(f"{key}={record.fields[key]}\n")
        return path
