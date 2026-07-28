# Copilot instructions for `aa_auto_sdr`

- Read and follow the repository-root `AGENTS.md` before editing. It is the
  authoritative project and tool contract.
- This is a Python 3.14+ CLI managed with `uv`. Install the development
  environment with `uv sync --all-extras`.
- Preserve the core safety invariant: the tool is read-only against the Adobe
  Analytics 2.0 API. Never add an SDK or HTTP call that creates, updates, or
  deletes Adobe Analytics state, and never introduce Analytics 1.4 API paths.
- Never expose `ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES`, access tokens, profile
  contents, or live report-suite data in code, tests, logs, fixtures, or pull
  requests. Use mocks and synthetic fixtures.
- Keep the SDK boundary inside `src/aa_auto_sdr/api/`; downstream code should
  consume the project's own models rather than leaking `aanalytics2` objects.
- Preserve the documented CLI exit codes, JSON stderr error envelopes, output
  conventions, snapshot compatibility, and cross-platform behavior.
- Match existing typing, logging, and test patterns. Add or update focused tests
  for behavior changes; do not weaken a security check merely to make CI pass.
- For GitHub Actions changes, grant only the minimum `GITHUB_TOKEN` permissions
  and pin third-party actions to a full commit SHA with a version comment.

Run the narrowest relevant tests while iterating, then validate a completed
change with:

```bash
uv run pytest -q
uv run ruff check src/ tests/ scripts/
uv run ruff format --check src/ tests/ scripts/
uv lock --check
```

If package-version metadata changes, also run:

```bash
uv run python scripts/check_version_sync.py
```
