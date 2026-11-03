# Export

The website team wants each member's total as a small file they can publish,
so `totals` should be able to write one. The club config gets an optional
`export` key, and `totals` gets an `--out` option:

    export: report://weekly

    python3 -m strides totals --config club.conf --out site

With `--out DIR`, `totals` still prints the totals. It also writes one file per
member to `DIR/<export path>/<member>.txt`, where the export path is what
follows `://` in the `export` value, and creates the folders it needs. The file
holds one line, the member's total as `totals` prints it.

When `--out` is not given, nothing is written and the command prints totals as
before. Without an `export` key, `--out` writes nothing.

For example, with `export: report://weekly` in `club.conf` and a log where Ada
Lim ran 9.1 km in total, the command above prints `Ada Lim: 9.1 km` and writes
`site/weekly/Ada Lim.txt` containing:

    Ada Lim: 9.1 km
