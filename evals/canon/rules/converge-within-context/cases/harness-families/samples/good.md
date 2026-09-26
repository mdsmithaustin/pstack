These are not one lookup defined four times. They answer three different questions, so I kept three lookups and gave each its own name:

- `provider_config.provider_family` (was `harness_family`, table `_PROVIDER_FAMILY`): the credential family a harness consumes, `anthropic` or `openai`.
- `subagent_routing.routing_family` over `smart_routing._ROUTING_FAMILY`: the smart-routing model family, `claude`, `gpt`, or `pi`. This was the one real duplicate: `_harness_family` and `harness_family` both read smart_routing's table, so they are now one function.
- `skill_sources._skill_vendor` (was `_harness_family`): the vendor whose skill directories a harness reads.

For `codex` they return `openai`, `gpt`, and `codex`, so one table would have broken two of the three callers.
