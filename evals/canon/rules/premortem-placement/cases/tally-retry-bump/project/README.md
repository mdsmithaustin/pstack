# tally-api

Billing Platform's invoice and account-config service. It posts journal entries to ledgerd through `src/tally/ledger_client.py`, configured by `config/client.yaml`.

Invoice finalisation calls `LedgerClient.post` once per invoice, inside the request handler, with a 30 s handler deadline set by the gateway.
