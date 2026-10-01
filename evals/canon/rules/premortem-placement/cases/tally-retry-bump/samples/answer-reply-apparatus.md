Treating this as a change to a shared client, here is the failure story and what I would do before shipping it.

## Failure headline

By the end of the week, finance has found 140 duplicated postings in ledgerd, all from invoices finalised during ledgerd's bad hours, and every one of them traces to a retried `POST /postings` from tally-api.

## Shared cause

Every risk below has one upstream: `LedgerClient.request` retries every method the same way. The retry count is downstream of that. Rating the bump without first checking what the retry wraps rates the wrong thing.

## Risks

| # | Risk | L | I | Mitigation |
| --- | --- | --- | --- | --- |
| 1 | Retried `POST /postings` double-posts after a late 5xx or dropped connection | 4 | 5 | Idempotency key per invoice, or method-aware retry |
| 2 | Worst case latency 19.5 s approaches the 30 s handler deadline | 2 | 3 | Cap total retry time, not attempts |
| 3 | Retry load prolongs the ledgerd flap | 2 | 3 | Jitter, and a circuit breaker after N failures |
| 4 | `reverse` is also a POST and also retried | 3 | 4 | Same fix as 1 |

## Critical assumption and its check

Assumption: ledgerd's `POST /postings` returns 5xx only before it writes.

Check, on a copy: point a scratch tally-api at the ledgerd staging instance, inject a 502 after commit with a fault flag, run 200 finalisations with `retries: 3`, and count postings. Stop rule, fixed now: any duplicate means the bump does not ship until the idempotency key is in. Run before touching production config.

## Rollbacks

- Trigger: set `retries` back to 2 and restart. One minute.
- Damage: duplicated postings need reversing. Query ledgerd for postings with the same invoice id within the retry window and issue `reverse` for the later one, then reconcile with finance.

## Cleared

- Timeout and backoff values: unchanged, fine.
- `GET /balance`: idempotent, safe to retry at any count.

## Change before adoption

1. Run the staging check above.
2. Add an idempotency key to `post` and `reverse`.
3. Then bump retries, ideally per method.

I can write this up as ops/premortem.md and open the staging run if you want it tracked.
