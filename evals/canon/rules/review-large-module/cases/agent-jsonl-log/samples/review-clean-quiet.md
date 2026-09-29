## Review: `feat/logging-jsonl`

Read through `hermes_logging_json.py`, the `setup_logging` change, and the tests. This is in good shape.

### Correctness

- The handler is registered after the text handlers and before the `_logging_initialized` early return, so a second `setup_logging` call is still a no-op. `_add_rotating_handler` dedupes by path.
- `record.getMessage()` is formatted on the listener thread, the same as `RedactingFormatter`. Mutable args could in theory change between enqueue and format, but that's already true of `agent.log`.
- `redact_sensitive_text` runs under the record's home override when the router is active, so a profile's own `redact_secrets` policy applies. Good.
- `exc` uses `formatException`, so chained exceptions come through intact.

### Suggestions

- `nit`: `ensure_ascii=False` is right for readability, but say in the docs that the file is UTF-8 so shippers don't guess.
- `nit`: add `pid` to each object. With the gateway and the dashboard both writing, it's the quickest way to tell processes apart.
- `nit`: `_read_logging_section` is read twice per `setup_logging` call. The effective-config cache makes that cheap, so it's fine.
- `nit`: the example in the PR body uses `hermes gateway`; `hermes logs` could learn about the new file later.

### Tests

The new tests pass here, and the ones that write `agent.jsonl` fail on main, so they pin the feature. Approve.
