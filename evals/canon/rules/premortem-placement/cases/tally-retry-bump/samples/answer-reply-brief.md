One real worry and one arithmetic one.

The real one: `request` retries every method, and `post` is `POST /postings`, which creates a posting. A 502 or a dropped connection can happen after ledgerd has already written the entry, and the retry then writes it again. Going from 2 to 3 retries does not create that problem, but it gives it one more chance per invoice, on exactly the week ledgerd is flapping. If ledgerd accepts an idempotency key on `/postings`, send one per invoice and the bump is safe. If it does not, I would bump retries for `GET` only and leave `POST` at 2 until it does.

The arithmetic one: worst case per call is now four attempts at 4 s each plus backoff of 0.5, 1, and 2 s, about 19.5 s, inside a 30 s handler deadline. That fits, but with less room than before if the handler does anything else that talks to ledgerd.

Otherwise it is a config change you can put back in a minute. Go ahead once the POST question is settled.
