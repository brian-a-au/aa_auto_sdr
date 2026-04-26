# aa_auto_sdr

Adobe Analytics SDR Generator — a CLI that generates Solution Design Reference documentation from an Adobe Analytics report suite. Sister project to [`cja_auto_sdr`](https://github.com/brian-a-au/cja_auto_sdr); shares UX conventions, does **not** share code.

> **Status:** v0.7 — single + batch SDR generation, snapshot save (`--snapshot`), and `--diff` between any two snapshots (path / `@latest` / `@previous` / git ref). Five output formats; discovery + inspect; `--output -` piping. OAuth Server-to-Server auth.

## Requirements

- Python 3.14+
- `uv`
- An Adobe Analytics OAuth Server-to-Server credential set (Org ID, Client ID, Secret, Scopes)

## Install

```bash
uv sync --all-extras
```

## Authenticate

Pick one. Resolution precedence: `--profile` > env vars > `.env` > `./config.json`.

### Profile (recommended for daily use)

```bash
uv run aa_auto_sdr --profile-add prod
```

Stored at `~/.aa/orgs/prod/config.json`.

```bash
uv run aa_auto_sdr <RSID> --profile prod
```

### Environment variables

```bash
export ORG_ID=...@AdobeOrg
export CLIENT_ID=...
export SECRET=...
export SCOPES=...
uv run aa_auto_sdr <RSID>
```

### `.env` file

`uv add python-dotenv` and copy `.env.example` to `.env`.

### `config.json`

A `config.json` in the working directory with the same fields as the profile.

## Generate an SDR

```bash
uv run aa_auto_sdr <RSID>                     # default Excel
uv run aa_auto_sdr <RSID> --format json
uv run aa_auto_sdr <RSID> --output-dir /tmp/sdr
```

All five formats are supported (`excel`, `csv`, `json`, `html`, `markdown`) plus aliases `all`, `reports` (excel + markdown), `data` (csv + json), `ci` (json + markdown).

The positional argument accepts either an RSID or a report-suite name:

```bash
uv run aa_auto_sdr "Adobe Store"           # name lookup (case-insensitive exact match)
uv run aa_auto_sdr dgeo1xxpnwcidadobestore # RSID
```

A name matching multiple report suites produces an SDR for each match (mirrors `cja_auto_sdr` convention). Output filenames are always keyed off the canonical RSID, never the input name.

## Generate SDRs for multiple report suites (`--batch`)

```bash
uv run aa_auto_sdr --batch RSID1 RSID2 RSID3
uv run aa_auto_sdr --batch "Adobe Store" "Demo Production" --format json --output-dir /tmp/sdr
```

Sequential generation across N report suites. Continue-on-error: a failure on one
RSID doesn't stop the rest. After the run, a summary banner prints counts,
success rate, total bytes/duration, and per-RSID ✓/✗ lists with timing. Names
that match multiple report suites fan out within the batch; duplicate
identifiers are deduplicated after resolution. Exit codes: `0` (all ok), `14`
(partial), or the last failure's code (all failed). `--output -` is rejected
for batch — use `--output-dir`.

## Snapshot and diff (v0.7)

Persist a normalized snapshot of the SDR alongside generation:

```bash
uv run aa_auto_sdr <RSID> --snapshot --profile prod
uv run aa_auto_sdr --batch RS1 RS2 --snapshot --profile prod
```

Snapshots land under `~/.aa/orgs/<profile>/snapshots/<RSID>/<ISO-timestamp>.json`.
JSON, sorted keys, atomic write — git-diff-friendly out of the box.

Compare any two snapshots:

```bash
# Path-based
uv run aa_auto_sdr --diff snap-a.json snap-b.json

# Profile-scoped aliases
uv run aa_auto_sdr --diff demo.prod@latest demo.prod@previous --profile prod
uv run aa_auto_sdr --diff demo.prod@2026-04-20T10-00-00+00-00 demo.prod@latest --profile prod

# Git ref (snapshot file at a specific commit)
uv run aa_auto_sdr --diff git:HEAD~1:snapshots/demo.prod.json git:HEAD:snapshots/demo.prod.json

# Output formats
uv run aa_auto_sdr --diff a.json b.json                          # console (default)
uv run aa_auto_sdr --diff a.json b.json --format json --output - # pipe to jq
uv run aa_auto_sdr --diff a.json b.json --format markdown --output diff.md
```

Identity is by component ID (a name change is a *modification*, not add+remove). Diffs run on the normalized model, not on rendered files — renaming a column in Excel does not create a false diff. Whitespace, `None`/empty-string, and tag ordering are normalized away (false-positive prevention adopted from `cja_auto_sdr`'s diff comparator).

Exit codes: `0` (diff succeeded), `15` (bad `--format`/`--output` combo), `16` (snapshot resolve/schema/git failure).

## Discover and inspect

Without generating a full SDR, you can list and inspect resources:

```bash
uv run aa_auto_sdr --list-reportsuites                  # all RSes visible to the org
uv run aa_auto_sdr --list-virtual-reportsuites          # all virtual report suites
uv run aa_auto_sdr --describe-reportsuite "Adobe Store" # metadata + counts
uv run aa_auto_sdr --list-metrics dgeo1xxpnwcidadobestore
uv run aa_auto_sdr --list-dimensions dgeo1xxpnwcidadobestore --filter "page" --sort name --limit 10
uv run aa_auto_sdr --list-segments "Adobe Store" --format json --output -    # pipe to jq
```

All list/inspect commands accept `--filter`, `--exclude`, `--sort FIELD`, `--limit N`, and `--format json|csv`. Default is a fixed-width table on stdout.

## Pipe SDR JSON to other tools

```bash
uv run aa_auto_sdr <RSID> --format json --output -
```

Outputs the full SDR as JSON to stdout. Pair with `jq` or any JSON consumer. Only `--format json` is valid with `--output -`; other formats reject.

## Verify

```bash
uv run aa_auto_sdr -V
uv run aa_auto_sdr --show-config
```

## Develop

```bash
uv run pytest                # all tests
uv run pytest -m unit        # unit only
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

## Roadmap

v0.9 = release-gate hardening (CI matrix, `core/exit_codes.py`, `--explain-exit-code`, `--completion`, version-sync). v1.0.0 = PyPI publish.
