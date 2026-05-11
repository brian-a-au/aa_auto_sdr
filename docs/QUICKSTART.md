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

```text
# Option A: env vars
export ORG_ID="YOUR_ORG_ID@AdobeOrg"
export CLIENT_ID="YOUR_CLIENT_ID"
export SECRET="YOUR_CLIENT_SECRET"
export SCOPES="openid,AdobeID,additional_info.projectedProductContext"
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

```text
uv run aa_auto_sdr <RSID> --output-dir /tmp/sdr
```

Replace `<RSID>` with any value from the list. Default output is Excel; other formats: `--format json`, `--format markdown`, `--format all`.

## 5. Capture a snapshot (and keep capturing on every run)

```text
uv run aa_auto_sdr <RSID> --profile prod --auto-snapshot --output-dir /tmp/sdr
```

`--auto-snapshot` is the recommended default: every generate run lands a snapshot under `~/.aa/orgs/prod/snapshots/<RSID>/<ISO-timestamp>.json`. JSON, sorted keys, git-diff-friendly. Pair with `--auto-prune --keep-last 10` to bound the store.

## 6. Diff against the previous capture

After a later run produces a second snapshot:

```text
uv run aa_auto_sdr --compare-with-prev <RSID> --profile prod
```

`--compare-with-prev` is sugar for `--diff <RSID>@previous <RSID>@latest`. Outputs a structured banner with added / removed / modified components and per-field deltas. The token order treats `latest` as the "after" side — what's *added* in the rendered output is what's new since the previous snapshot.

## 7. Tab completion (optional)

```bash
aa_auto_sdr --completion zsh > ~/.zsh/completions/_aa_auto_sdr   # zsh
aa_auto_sdr --completion bash > ~/.bash_completion.d/aa_auto_sdr # bash
aa_auto_sdr --completion fish > ~/.config/fish/completions/aa_auto_sdr.fish
```

Re-source your shell config or open a new terminal.

## Next

See [`docs/CLI_REFERENCE.md`](CLI_REFERENCE.md) for the full flag table and exit codes.
