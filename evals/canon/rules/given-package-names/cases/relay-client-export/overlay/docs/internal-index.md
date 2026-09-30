# Internal packages

Packages that Nous engineers publish for internal use go to the `nous-internal` index. Their distribution names start with `nous-`.

| Distribution | Import as | Used for |
| --- | --- | --- |
| `nous-relay-client` | `relay_client` | span export and relay tooling |

Machines with no network edit `pyproject.toml` by hand and run `uv sync --frozen`. Wheels for those machines sit in `vendor/index/`.
