# aa_auto_sdr

Adobe Analytics SDR Generator — a CLI that generates Solution Design Reference documentation from an Adobe Analytics report suite. Sister project to [`cja_auto_sdr`](https://github.com/brian-a-au/cja_auto_sdr); shares UX conventions, does **not** share code.

> **Status:** v0.3 — single-RSID SDR generation in five formats; discovery, inspection, and describe commands with filter/sort/limit; `--output -` stdout piping. Accepts either an RSID or a report-suite name. OAuth Server-to-Server auth.

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

v0.5 = `--batch` (multi-RS generation in one run). v0.7 = snapshot + `--diff` (version control of SDR). v0.9 = release-gate hardening (CI matrix, version-sync, completion). v1.0.0 = PyPI publish.
