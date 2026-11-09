import json
import os


class Store:
    def __init__(self, root):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def write(self, record):
        path = os.path.join(self.root, "deliveries.jsonl")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"id": record.id, "fields": record.fields}) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return path
