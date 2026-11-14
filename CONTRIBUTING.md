# Contributing to aa_auto_sdr

Thanks for your interest. This project has a narrow scope on purpose. It
generates Solution Design Reference (SDR) documents from an Adobe Analytics
report suite, and it tracks how those documents change over time.

Please open an issue to discuss a new feature before you write code for it.
Small fixes and documentation corrections can go straight to a pull request.

By taking part, you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md). Report security issues privately as
described in [SECURITY.md](SECURITY.md). Do not put a vulnerability, Adobe
credentials, or customer report suite data in a public issue or pull request.

## Set up

The project uses [`uv`](https://github.com/astral-sh/uv) and needs Python 3.11
or newer.

```bash
git clone https://github.com/brian-a-au/aa_auto_sdr.git
cd aa_auto_sdr
uv sync
```

You do not need Adobe credentials to run the test suite. The tests block
network access, so they never call a live Adobe Analytics org.

## Check your change

Run these before you open a pull request. CI runs the same checks.

```bash
uv run pytest tests/ -x -q
uv run ruff check src/ tests/ scripts/
uv run ruff format --check src/ tests/ scripts/
```

CI runs the tests on Python 3.11 through 3.15 on Linux. It also runs them on
macOS and Windows with the oldest and newest of those versions. Do not use syntax or standard library features newer than Python 3.11.

## Rules every change must follow

Meta tests under `tests/meta/` enforce several of these rules. The suite fails
if a change breaks one of them.

- The tool only reads from Adobe Analytics. It never creates, updates, or
  deletes anything in a customer's Adobe environment.
- The tool uses the Adobe Analytics 2.0 API only. Do not call or fall back to
  the legacy 1.4 API.
- Only `src/aa_auto_sdr/api/client.py` imports the `aanalytics2` SDK. The rest
  of the code uses the project's own data models.
- `sdr/builder.py` takes data in and returns a document. It does no file or
  network I/O.
- Output writers follow the single `Writer` protocol and register themselves.
  See `output/registry.py`.
- Heavy packages, e.g., `pandas`, load only when a command needs them. This
  keeps `--version` and `--help` fast.

The CLI flags, environment variables, profile layout, format names, and exit
codes match the sister project
[`cja_auto_sdr`](https://github.com/brian-a-au/cja_auto_sdr). If you change one
of these, explain why in the pull request. If you add a flag, a command, or an
exit code, also update [AGENTS.md](AGENTS.md) and
[docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md).

## Documentation

`CHANGELOG.md` records when a change shipped. The other docs describe what the
tool does today. Do not write "added in version X" in user docs.

## Releases

The maintainer handles releases. The full steps are in
[RELEASING.md](RELEASING.md). Changes to docs or CI alone ship without a
version bump.
