# Quickstart

Generate your first Solution Design Reference (SDR) in 90 seconds.

## Prerequisites

- Python 3.14+
- [`uv`](https://docs.astral.sh/uv/) (`brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- An Adobe Analytics OAuth Server-to-Server credential set (Org ID, Client ID, Secret, Scopes). See `docs/CONFIGURATION.md` or [Adobe Developer Console](https://developer.adobe.com/console).

## 1. Install

```bash
git clone https://github.com/brian-a-au/aa_auto_sdr
cd aa_auto_sdr
uv sync --all-extras
```

## 2. Set credentials

Pick one — environment variables (fastest) or a profile (recommended for daily use).

```bash
# Option A: env vars
export ORG_ID="...@AdobeOrg"
export CLIENT_ID="..."
export SECRET="..."
export SCOPES="openid, AdobeID, additional_info.projectedProductContext"
```

```bash
# Option B: named profile (writes ~/.aa/orgs/prod/config.json)
uv run aa_auto_sdr --profile-add prod
```

## 3. Verify

```bash
uv run aa_auto_sdr --show-config
uv run aa_auto_sdr --list-reportsuites
```

If the list shows your report suites, credentials are wired correctly.

## 4. Generate one SDR

```bash
uv run aa_auto_sdr <RSID> --output-dir /tmp/sdr
```

Replace `<RSID>` with any value from the list. Default output is Excel; other formats: `--format json`, `--format markdown`, `--format all`.

## 5. Capture a snapshot

```bash
uv run aa_auto_sdr <RSID> --profile prod --snapshot --output-dir /tmp/sdr
```

The snapshot lands at `~/.aa/orgs/prod/snapshots/<RSID>/<ISO-timestamp>.json` — JSON, sorted keys, git-diff-friendly.

## 6. Generate a second snapshot a day later

(After the report suite changes — new dimension, renamed metric, etc.)

```bash
uv run aa_auto_sdr <RSID> --profile prod --snapshot --output-dir /tmp/sdr
```

## 7. Diff the two

```bash
uv run aa_auto_sdr --diff <RSID>@latest <RSID>@previous --profile prod
```

Outputs a structured banner with added / removed / modified components and per-field deltas.

## 8. Tab completion (optional)

```bash
aa_auto_sdr --completion zsh > ~/.zsh/completions/_aa_auto_sdr   # zsh
aa_auto_sdr --completion bash > ~/.bash_completion.d/aa_auto_sdr # bash
aa_auto_sdr --completion fish > ~/.config/fish/completions/aa_auto_sdr.fish
```

Re-source your shell config or open a new terminal.

## Next

See [`docs/CLI_REFERENCE.md`](CLI_REFERENCE.md) for the full flag table and exit codes.
