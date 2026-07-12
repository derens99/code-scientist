# Contributing

Thanks for helping improve Code Scientist.

## Development setup

Python dependencies and commands use `uv`:

```bash
uv sync --locked
uv run pytest -q
uvx ruff check src tests
uv build
```

The optional workbench uses Node 22 and npm:

```bash
cd web
npm ci
npm test
npm run typecheck
npm run build
```

## Changes

- Add regression tests for behavior changes and bug fixes.
- Preserve backward compatibility for committed `state.json` artifacts.
- Keep deterministic scaffolding clearly separated from measured evidence.
- Never commit API keys, local `.env` files, private corpora, or generated run directories.
- Keep the workbench loopback-only unless a separate authenticated deployment boundary is added.

Open a focused pull request describing the user impact, validation performed,
and any remaining limitations. Report vulnerabilities through [SECURITY.md](SECURITY.md),
not a public issue.
