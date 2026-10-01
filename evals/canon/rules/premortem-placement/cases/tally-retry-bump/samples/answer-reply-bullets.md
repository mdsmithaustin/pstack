Three things, in order of how much I would care.

- **Double postings.** The retry in `ledger_client.py` does not distinguish methods. `POST /postings` is not idempotent as written, so any retry after ledgerd has processed the request but before you saw the response creates a second posting. The bump does not introduce this, but a flapping ledgerd is when it actually happens. An idempotency key per invoice fixes it properly; short of that, do not retry `POST` more than you do today.
- **Deadline.** Four attempts at 4 s plus 0.5 + 1 + 2 s of backoff is about 19.5 s worst case, under the 30 s gateway deadline. Fine, and one more bump would still fit, but not two.
- **Load.** More retries against a service that is already struggling means more requests to it while it struggles. With backoff and a small fleet this is probably noise, but it is the kind of thing that turns a flap into an outage if many callers do it at once.

If you can add the idempotency key, bump away. If not, I would hold `POST` at 2 and fix the flapping on the ledgerd side instead.
