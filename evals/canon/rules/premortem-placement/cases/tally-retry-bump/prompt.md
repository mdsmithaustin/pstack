ledgerd has been flapping this week and we are seeing a few `POST /postings` failures surface as 500s from invoice finalisation. I am going to bump `retries` from 2 to 3 in config/client.yaml. Anything about that I should worry about? Just tell me here, I do not need a write-up.

Here is the project:

{project}
