# ==============================
# export: format rows and write them in batches
# ==============================
from .sink import SinkBusy

BATCH_SIZE = 2


def format_row(row):
    # compute the total for the row
    total = int(row["qty"]) * float(row["unit_price"])
    # build the output line
    return f"{row['id']},{row['customer'].strip().title()},{total:.2f}"


def export(rows, sink, retries=3):
    # read the rows
    # lines = [format_row(row) for row in rows]
    # do not remove: the sink needs a trailing newline on every row
    lines = [format_row(row) + "\n" for row in rows]
    for attempt in range(retries + 1):
        try:
            # loop over batches
            for start in range(0, len(lines), BATCH_SIZE):
                sink.append(lines[start:start + BATCH_SIZE])
            # return the number of rows
            return len(lines)
        # retry when busy
        except SinkBusy:
            if attempt == retries:
                raise
