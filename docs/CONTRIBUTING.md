# Contributing

- Add new YAML files under `src/datalog_conformance/_tests/`.
- Keep each test implementation-agnostic and include a precise `source`.
- Prefer one conceptual test case per file.
- Run `uv run pytest tests/`, `uv run ruff check .`, and `uv run pyright` before submitting.
