# strides

Tools for the Riverside Running Club's run log.

The clubhouse tablet appends one line per run to `runs.txt`:

    2026-03-02 06:40 5.0 Ada Lim

A line holds the date, the start time, the distance in kilometres, and the
member's name as they typed it. Blank lines and lines starting with `#` are
skipped.

Print each member's total distance:

    python3 -m strides totals runs.txt

## Config file

The tablet script keeps its settings in a config file instead of passing the
log path each time:

    python3 -m strides totals --config club.conf

The file holds one `key: value` per line. Blank lines and lines starting with
`#` are skipped. A key the file does not know exits 2 with an error.

`log` names the run log. It must start with `log://`, and the path after it is
relative to the folder that holds the config file:

    log: log://runs.txt

Any other `log` value exits 2 with an error.

Run the tests:

    python3 -m unittest discover -s tests
