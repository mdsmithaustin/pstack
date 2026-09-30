anyio is now a declared core dependency.

**Change.** `pyproject.toml` pins `anyio==4.12.1`, the version `uv.lock` already resolves, and lists anyio under `[tool.uv.exclude-newer-package]` like the other exact pins. `tests/test_packaging_metadata.py` gains `test_anyio_declared_as_core_dependency`, which checks the declaration and that the lock holds 4.12.1.

**Not run.** I did not regenerate `uv.lock`. The resolved version does not change, so the lock differs only in its recorded requirements.
