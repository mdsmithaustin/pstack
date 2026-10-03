# ==============================
# sink: file-backed output
# ==============================
class SinkBusy(Exception):
    pass


class Sink:
    def __init__(self, path, busy_after=None):
        # open the output file
        self._out = open(path, "w", newline="")
        self._busy_after = busy_after
        # count the accepted rows
        self._accepted = 0

    def append(self, batch):
        # raise once when the busy threshold is reached
        if self._busy_after is not None and self._accepted >= self._busy_after:
            self._busy_after = None
            raise SinkBusy("sink is busy")
        # write each row
        for row in batch:
            self._out.write(row)
        # flush to disk
        self._out.flush()
        self._accepted += len(batch)

    def close(self):
        # close the file
        self._out.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
