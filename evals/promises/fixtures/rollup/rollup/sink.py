class SinkBusy(Exception):
    pass


class Sink:
    def __init__(self, path, busy_after=None):
        self._out = open(path, "w", newline="")
        self._busy_after = busy_after
        self._accepted = 0

    def append(self, batch):
        if self._busy_after is not None and self._accepted >= self._busy_after:
            self._busy_after = None
            raise SinkBusy("sink is busy")
        for row in batch:
            self._out.write(row)
        self._out.flush()
        self._accepted += len(batch)

    def close(self):
        self._out.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
