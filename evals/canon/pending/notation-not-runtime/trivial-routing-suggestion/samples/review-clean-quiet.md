## Review: `trivial-routing-suggestion`

Looks good. Small, focused, and it fixes a real annoyance: agents denied on opus had no idea which model to fall back to.

### `routing.py`

- `_trivial_reason` is a sensible extraction. The two copies of the reason string had to be kept in sync by hand.
- When `suggested_model` is `None` the message is unchanged, so no existing deployment behaves differently.
- The guard against a gated suggestion is right, and the error names `expensive_models`, which is what an operator will search their config for.
- `suggested_model=""` falls back to the generic reason. That's probably what you want, but a note in the docstring would help.

### Registry

The `suggested_model` property in `params_schema` is correct and optional. Should the policy picker in `web/` show help text for it? That can be a follow-up.

### Behaviour

I walked through the four paths: a fresh trivial verdict names the suggestion, a cached trivial verdict names it without calling the classifier, the complex path is untouched, and no suggestion keeps the old text. All look right.

### Other

- CONTRIBUTING wants an e2e happy path for user-facing features. This is config-only, so I'd skip it, but say so in the PR.
- Add an example to `examples/server_config_deny_trivial_opus.yaml`.
- The changelog line reads well.

Approve.
