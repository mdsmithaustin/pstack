omnigent stores these as session labels (`SqlConversationLabel`, the `labels` field in the API), so I named the filter for labels rather than adding a second word for them.

- `GET /v1/sessions?label=team=infra` keeps sessions that carry every `key=value` pair given. A pair without `=` returns 400.
- `list_conversations(labels=...)` joins on the label table the way `pinned` does.
- `client.sessions.list(labels={"team": "infra"})` sends the pairs.
