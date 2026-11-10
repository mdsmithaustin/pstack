# relay

Imports JSON or CSV partner feeds into `deliveries.jsonl` in the store directory.
Each JSON line contains a record's `id` and `fields`. Downstream consumers act
on each appended delivery, in order. Repeated lines cause repeated deliveries;
consumers do not deduplicate by record ID. They retain their byte offset, so
already delivered lines must not be removed or replaced.

    python3 -m relay import feeds/sample.json --store out/
    python3 -m relay summarize feeds/sample.json --store out/

The importer loads and parses the feed before writing. Each store write appends,
flushes and syncs one delivery before returning. An interrupted import can leave
a durable prefix. A process can exit after an append reaches disk but before its
caller sees success. There is no saved import progress or replay protection.
The existing retry helper wraps loading and parsing, not journal writes.

Tests: `python3 -m unittest discover -s tests`
