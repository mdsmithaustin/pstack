Yes, one thing is worth worrying about before you bump it. `POST /postings` isn't safe to retry, and a third retry makes that worse.

**Duplicate postings.** `LedgerClient.request` retries every method on 500, 502, 503, 504 and connection errors. `post` sends no idempotency key. If ledgerd commits a posting and then fails on the way back, for example a 500 or 502 after the write, the client resends it. That could write a second journal entry for the same invoice. This is an inference from the code, since I can't see ledgerd's behaviour. A flapping ledgerd makes that case more likely. `reverse` is also a POST and has the same exposure.

Retries at 2 may already have produced duplicates this week. I'd check ledgerd for repeated entries on the same invoice before changing anything. Going to 3 raises the odds on every failed call.

The proper fix is a client-generated idempotency key on `post`, reused across attempts, if ledgerd supports one. Otherwise, restrict retries on POST to failures where the request provably never reached the server, or stop retrying POST entirely. Keep retrying GET on `balance`.

**Deadline.** The worst case for one `post` with 3 retries is 4 attempts at 4 s plus 0.5, 1 and 2 s of backoff, so about 19.5 s. That fits the gateway's 30 s limit (it's 13.5 s at 2 retries). It leaves little room if the handler does any other ledgerd calls or slow work. The sleeps are synchronous, so the worker is held the whole time.

**Load.** During flapping, each failing call becomes 4 requests instead of 3. That's about 33% more traffic to a service that's already struggling.

**Effectiveness.** The extra retry only adds 2 s of backoff. If outages last longer than a few seconds, you'll still see the 500s. Read timeouts also aren't retried, because `requests.ReadTimeout` isn't a `ConnectionError`, so some failures won't benefit at all. This part is a guess about your failure mix.

**Rollout.** The config is read once at startup, so the change only takes effect after a restart or redeploy.

If you add the idempotency key first, the bump is fine. Without it, I'd leave `retries` at 2 and fix the root cause in ledgerd's flapping.