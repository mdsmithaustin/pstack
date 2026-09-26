# Grading guide: tag filter on the session list (positive)

## Flaw location

- `omnigent/server/routes/sessions/routes_core.py:list_sessions` (the new `tag` query parameter) and `routes_core.py:_parse_tag_filter`
- `omnigent/stores/conversation_store/__init__.py:ConversationStore.list_conversations` and `omnigent/stores/conversation_store/sqlalchemy_store.py:SqlAlchemyConversationStore.list_conversations` (the new `tag_key` / `tag_value` arguments)
- `sdks/python-client/omnigent_client/_sessions.py:SessionsNamespace.list` (the new `tag` keyword)
- `omnigent/server/API.md` "List Sessions" (the new `tag` paragraph)

## The flaw

The branch filters sessions by their key/value labels but calls them tags. Omnigent already has one name for this concept. It is the label: the `conversation_labels` table and `SqlConversationLabel`, `labels` on `POST /v1/sessions` and `PATCH /v1/sessions/{id}`, `labels` on every `SessionListItem`, `Session.labels` in the client, `set_labels` and `delete_label` in the store, and the `pinned` filter, which is itself a label join. No code in the repo uses "tag" for it. The PR's own docs admit that "tags are stored as conversation labels" and that tags are "the key/value pairs set through `labels`". The public API would then write labels and read tags. This breaks the rule of one name per concept: when a request's word differs from the code's word, keep the code's word, or rename every occurrence first. Do not add the new word next to the old one.

The correct fix is to name the filter after labels everywhere: `?label=team:infra` (or `label_key` / `label_value`), `list_conversations(label_key=..., label_value=...)`, `SessionsNamespace.list(label=...)`, `_parse_label_filter`, and API.md text about a label filter. Keep no `tag` alias. Renaming labels to tags across the codebase would also be consistent, but it is not a plausible request for this PR. A review that suggests it still gets FOUND if it says to use a single word.

## Grades

- FOUND: names the tag filter (the parameter, argument, or client keyword), says the codebase already calls this concept a label, so tag is a second name, and asks for it to be called label throughout (or otherwise for one word, with no synonym).
- PARTIAL: notices that tag and label are the same thing but gives no fix, or gives a fix that keeps both words. Examples: document that tags are labels, accept `label` as an alias beside `tag`, or rename only the store arguments.
- MISSED: never raises the naming. This includes reviews that discuss the tag filter only for parsing, security, performance, or tests.

## Comments that count neither way

- Supporting several filters (`?tag=a:1&tag=b:2`) or OR semantics.
- A key that contains `:` cannot be matched with a value, because `partition(":")` splits on the first colon.
- No `max_length` on the query parameter. No index on `(workspace_id, key, value)` for `conversation_labels`.
- `_parse_tag_filter` is a module-level helper, so it could live in `_sessions/helpers.py`.
- Test nits: an asc-order assertion, or duplicated seeding between the route test and the store test.
- The 400 for pin keys: whether the bare `omnigent.pinned` also needs rejecting, or whether other reserved keys (`omni_project`, `omnigent.side_chat`) should be refused.
- Whether the resume picker's client-side wrapper-label filter should switch to the server filter.
