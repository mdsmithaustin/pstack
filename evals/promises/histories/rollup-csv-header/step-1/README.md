# rollup

Turns an orders CSV into a flat export, two rows per write.

    python3 -m rollup data/orders.csv out.csv

Add `--header` to write `id,customer,total` before the rows.

Set `ROLLUP_BUSY_AFTER=<n>` and the sink raises `SinkBusy` once, after it has accepted `n` rows. Without it the export runs clean.

Tests: `python3 -m unittest discover -s tests`
