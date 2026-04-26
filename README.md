# aa_auto_sdr

Adobe Analytics SDR Generator — a CLI that generates Solution Design Reference documentation from an Adobe Analytics report suite. Sister project to [`cja_auto_sdr`](https://github.com/brian-a-au/cja_auto_sdr); shares UX conventions, does **not** share code.

> **Status:** v0.2 — single-RSID generation in five formats (Excel, CSV, JSON, HTML, Markdown). Accepts either an RSID or a report-suite name. OAuth Server-to-Server auth.

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

v0.3 = discovery (`--list-reportsuites`) + inspect commands (`--list-metrics`, etc.) + stdout piping. v0.5 = `--batch`. v0.7 = snapshot + `--diff`. v0.9 = release-gate hardening. v1.0.0 = PyPI publish.
