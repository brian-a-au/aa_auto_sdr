# Configuration

How to authenticate `aa_auto_sdr` against your Adobe Analytics 2.0 API. See [`QUICKSTART.md`](QUICKSTART.md) for the step-by-step onboarding walkthrough; this page is the deeper reference.

## Adobe Developer Console setup

`aa_auto_sdr` uses **OAuth Server-to-Server**.

### 1. Create a project

1. Visit https://developer.adobe.com/console
2. Create a new project (or open an existing one)
3. Click **Add API** → **Adobe Analytics**
4. Choose **OAuth Server-to-Server** as the auth method

The console gives you four values to capture: **Org ID**, **Client ID**, **Client Secret**, and a list of **Scopes** the integration is granted.

### 2. Required scopes

#### Known-working baseline (validated against a live Adobe Analytics 2.0 org)

The `SCOPES` value must include these **three** scopes. They've been validated against a live Adobe Analytics 2.0 org for the read surface this tool exercises (`/reportsuites`, `/dimensions`, `/metrics`, `/segments`, `/calculatedmetrics`, `/virtualreportsuites`, `/classifications/datasets`).

```
openid
AdobeID
additional_info.projectedProductContext
```

#### Recommended (broader endpoint coverage)

Add either or both if your org's IMS rules require them for the endpoints this tool calls — they're commonly included in Adobe OAuth Server-to-Server integrations, but neither is empirically required for the current read surface:

```
read_organizations
additional_info.job_function
```

#### How to tell if you need the recommended scopes

| Symptom | Likely missing scope |
|---------|----------------------|
| `--list-reportsuites` returns empty despite successful auth | `read_organizations` (or your integration isn't on a Product Profile — see step 3) |
| `--list-metrics`, `--list-dimensions` return 403 or empty | `additional_info.job_function` |

If you hit either symptom with the minimum 3-scope config, add the corresponding recommended scope and re-test.

### 3. Add to a Product Profile

In the **Adobe Admin Console** (https://adminconsole.adobe.com/):

1. Open your Adobe Analytics product
2. Open the **Product Profile** that contains the report suites you want to access
3. Add the integration (the one you just created in Developer Console) to the profile

Without this step, authentication can succeed while no Analytics companies or report suites are visible. In the underlying SDK flow, `Login().getCompanyId()` may return no companies and subsequent `Analytics()` calls may return empty data. `aa_auto_sdr --show-config` cannot detect this — the first generation attempt is what surfaces the problem.

## Analytics company context: RSID vs Global Company ID

This CLI is RSID-first from the user's perspective, but Adobe Analytics 2.0 API calls are made in the context of an Analytics **global company ID**.

Your **RSID** identifies the report suite to document. It is **not** the same as the Analytics company identifier used for API routing and request context.

Under the hood, Adobe Analytics 2.0 requests typically require:

- `Authorization: Bearer <access_token>`
- `x-api-key: <client_id>`
- `x-proxy-global-company-id: <globalCompanyId>`

The tool resolves the accessible Analytics company context internally before making RSID-scoped requests. If the integration is not attached to the right Product Profile, authentication can succeed while no Analytics companies or report suites are visible.

## Credential storage

Pick one of four sources. Resolution precedence (highest wins):

1. `--profile <name>` flag (or `AA_PROFILE` env var pointing at a named profile)
2. Environment variables already in the shell
3. `.env` file in the working directory (only if `python-dotenv` is installed via `uv sync --all-extras`)
4. `config.json` in the working directory

Run `aa_auto_sdr --show-config` to see which source resolved for a given invocation.

### Option 1 — Named profile (recommended for daily use)

```bash
uv run aa_auto_sdr --profile-add prod
```

Walks through prompts for ORG_ID / CLIENT_ID / SECRET / SCOPES and writes:

```
~/.aa/orgs/prod/config.json
```

Use with `--profile prod` on subsequent commands. Multi-org users create one profile per org.

### Option 2 — Environment variables

| Variable | Required | Notes |
|----------|----------|-------|
| `ORG_ID` | yes | e.g. `D0F83C645C5E1CC60A495CB3@AdobeOrg` |
| `CLIENT_ID` | yes | from Developer Console |
| `SECRET` | yes | the OAuth client secret |
| `SCOPES` | yes | comma-separated list (see above). The tool normalizes whitespace before requesting tokens, so `"openid, AdobeID, ..."` also works — but no-space is the canonical form |
| `AA_PROFILE` | no | shorthand to set `--profile` |
| `LOG_LEVEL` | no | honored by the CLI's logging |
| `NO_COLOR` | no | when set to a non-empty value, disables ANSI colors in console output (per [no-color.org](https://no-color.org/)) |
| `GITHUB_STEP_SUMMARY` | no | when set (GitHub Actions sets it per job), `--diff` also appends a markdown render to that file |

These last two are behavioral toggles, not credentials. Notion-related environment variables are documented under [Notion Integration](#notion-integration-optional) below.

Per-platform setup:

```text
# macOS / Linux (current shell)
export ORG_ID="YOUR_ORG_ID@AdobeOrg"
export CLIENT_ID="YOUR_CLIENT_ID"
export SECRET="YOUR_CLIENT_SECRET"
export SCOPES="openid,AdobeID,additional_info.projectedProductContext"

# Windows cmd
setx ORG_ID "YOUR_ORG_ID@AdobeOrg"
setx CLIENT_ID "YOUR_CLIENT_ID"
# ...

# PowerShell
$Env:ORG_ID = "YOUR_ORG_ID@AdobeOrg"
$Env:CLIENT_ID = "YOUR_CLIENT_ID"
# ...
```

### Option 3 — `config.json` in working directory

```bash
cp config.json.example config.json
# Edit config.json with the four required fields
```

`config.json` is in `.gitignore` — do not commit it.

```json
{
  "org_id": "...@AdobeOrg",
  "client_id": "...",
  "secret": "...",
  "scopes": "openid,AdobeID,additional_info.projectedProductContext"
}
```

### Option 4 — `.env` file

If `python-dotenv` is installed (it's an optional extra), the tool also reads `.env` from the working directory:

```env
ORG_ID=...@AdobeOrg
CLIENT_ID=...
SECRET=...
SCOPES=openid,AdobeID,additional_info.projectedProductContext
```

Same fields, same gitignore.

## Multi-org setups

Each Adobe organization needs its own profile (or its own credential set). The named-profile workflow is built for this:

```bash
uv run aa_auto_sdr --profile-add client-a
uv run aa_auto_sdr --profile-add client-b
uv run aa_auto_sdr --list-reportsuites --profile client-a
uv run aa_auto_sdr --list-reportsuites --profile client-b
```

Profiles are isolated under `~/.aa/orgs/<name>/`. Snapshot files are also profile-scoped: `~/.aa/orgs/<name>/snapshots/<RSID>/<ts>.json`.

## Logging

Logging is documented in [`LOGGING.md`](LOGGING.md): flags (`--log-level`, `--log-format`, `--quiet`), file naming, redaction, the canonical events the log file emits, and how to read credential resolution from the log. The internal logger-call contract lives in [`LOGGING_STYLE.md`](LOGGING_STYLE.md).

## Diagnostics

| Command | Purpose |
|---|---|
| `aa_auto_sdr --show-config` | Print which credential source resolved (truncated `client_id`, no secret exposure). |
| `aa_auto_sdr --config-status` | Full credential resolution chain — which sources are present, which one won, and why. |
| `aa_auto_sdr --validate-config` | Validate the resolved credential shape locally. Does not contact Adobe. |
| `aa_auto_sdr --sample-config` | Emit a `config.json` template to stdout. |
| `aa_auto_sdr --profile-list` | List profiles under `~/.aa/orgs/`. |
| `aa_auto_sdr --profile-show <NAME>` | Show a profile's fields with secrets masked. |
| `aa_auto_sdr --profile-test <NAME>` | Live test: OAuth + `getCompanyId()`. Prints PASS / FAIL. |
| `aa_auto_sdr --profile-import <NAME> <FILE>` | Import a JSON config as a named profile. Use `--profile-overwrite` to replace. |

## Common failure modes

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `error: Profile 'X' not found at ~/.aa/orgs/X/config.json` | `--profile X` referenced a non-existent profile | Run `aa_auto_sdr --profile-add X` or fix the path |
| `auth error: ...` (exit 11) | Bad client_id/secret or wrong scopes | Verify in Developer Console; check SCOPES per step 2 above |
| `--list-reportsuites` returns empty even though auth succeeded | Integration not on a Product Profile in Admin Console | Add the integration to a Product Profile |
| `403 Forbidden` on `/dimensions` or `/metrics` | Recommended scope `additional_info.job_function` may be required by your org | Add it to SCOPES (see step 2 above) |
| `error: report suite 'X' not found` (exit 13) | Typo or wrong org for the credentials | `aa_auto_sdr --list-reportsuites` to see what's actually visible |

For full per-code remediation, run `aa_auto_sdr --explain-exit-code <CODE>`.

## Notion Integration (Optional)

Required if using `--format notion` or `--push-to-notion`. Install the extra first:

```bash
uv pip install 'aa-auto-sdr[notion]'
```

| Env var | Description |
|---|---|
| `NOTION_TOKEN` | Notion internal integration token (Settings & Members → Integrations) |
| `NOTION_PARENT_PAGE_ID` | The Notion page under which SDR pages are created. The integration must be invited to this page (Share → Add connection). `NOTION_PARENT_PAGE_ID` is also the create target for `--notion-create-database`: the registry database is created as a child of this page (and inherits the integration's access to it). |
| `NOTION_REGISTRY_DATABASE_ID` | Optional. Database ID for the SDR Registry. When set, `--format notion` and `--push-to-notion` runs also upsert one row per RSID into the named Notion database after writing the detail page. Unset = byte-identical page-only behavior. The integration must also be invited to the database. The database should have a single data source; if more than one is found, the tool uses the first and logs a `notion_registry_multi_source` warning. |
| `NOTION_REGISTRY_COMPANY` | Optional. Company name written to the `Company` column of the registry row. When set, the registry row key becomes `(Company, RSID)` instead of RSID alone — required when one registry database holds multiple Adobe Analytics organizations. Precedence: `--notion-company` flag → this env var → the resolved Adobe global company id (generate path only); the push path uses the flag or this env var only. Unset leaves the `Company` property blank and keeps RSID-only keying. |

Credentials are env vars only — they are **not** stored in profile `config.json`. The `.env` file is honored if `python-dotenv` is installed (already the `[env]` extra). A single `.env` file can hold both the Adobe keys and the Notion keys, because the variable names do not overlap. See [`CLI_REFERENCE.md`](CLI_REFERENCE.md#notion-integration) for usage examples.

## See also

- [`QUICKSTART.md`](QUICKSTART.md) — the step-by-step onboarding walkthrough
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md) — every flag with examples
- [`LOGGING.md`](LOGGING.md) — log output, events, redaction
- [Adobe I/O Console](https://developer.adobe.com/console) — credential setup
- [`aanalytics2` SDK getting-started](https://github.com/pitchmuc/adobe-analytics-api-2.0/blob/master/docs/getting_started.md) — underlying SDK auth flow
