## Review: `routing-suggested-model`

Looks good. Small, focused, and it solves a real annoyance: agents denied on opus had no idea which model to fall back to.

### `routing.py`

- `_trivial_reason` is a good extraction. The two copies of the reason string had already been kept in sync by hand once.
- The default message is unchanged when `suggested_model` is `None`, so existing deployments see no difference.
- The guard against a gated suggestion is right. I'd make the message say which list it collided with, but it already says `expensive_models`, so that's fine.
- `suggested_model=""` falls back to the generic reason. That's probably what you want, but a one-line note in the docstring would help.

### Registry

The new `suggested_model` property in `params_schema` is correct and not required. Should we also surface it in the policy picker's help text in `web/`? That can be a follow-up.

### Tests

The scenarios in `suggested_model.feature` read nicely, and the step definitions are tidy. Using `AsyncMock` for the classifier and asserting `assert_not_awaited` on the cached path is exactly the check I'd want. Five scenarios cover fresh, cached, generic, complex, and the config error.

One nit: `send` builds the client with `type("_Client", (), {...})()`. A small named stub class would read better.

### Other

- CONTRIBUTING wants an e2e happy path for user-facing features. This is config-only, so I'd skip it, but note that in the PR.
- Add an example to `examples/server_config_deny_trivial_opus.yaml`.

Approve with nits.
