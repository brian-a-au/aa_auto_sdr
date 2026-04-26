# Configuration

How to authenticate `aa_auto_sdr` against your Adobe Analytics 2.0 API. See [`QUICKSTART.md`](QUICKSTART.md) for the 90-second onboarding flow; this page is the deeper reference.

## Adobe Developer Console setup

`aa_auto_sdr` uses **OAuth Server-to-Server**. JWT auth was deprecated 2025-01-01 — do not use it.

### 1. Create a project

1. Visit https://developer.adobe.com/console
2. Create a new project (or open an existing one)
3. Click **Add API** → **Adobe Analytics**
4. Choose **OAuth Server-to-Server** as the auth method

The console gives you four values to capture: **Org ID**, **Client ID**, **Client Secret**, and a list of **Scopes** the integration is granted.

### 2. Required scopes

The `SCOPES` value must include **all** of the following:

```
openid
AdobeID
read_organizations
additional_info.projectedProductContext
additional_info.job_function
```

The `additional_info.job_function` scope is **load-bearing**. Without it, `/dimensions`, `/metrics`, and other read endpoints return empty responses or 403 errors even though authentication appears to succeed. This is one of the most common silent-failure modes when first setting up the tool.

### 3. Add to a Product Profile

In the **Adobe Admin Console** (https://adminconsole.adobe.com/):

1. Open your Adobe Analytics product
2. Open the **Product Profile** that contains the report suites you want to access
3. Add the integration (the one you just created in Developer Console) to the profile

Without this step, `Login().getCompanyId()` returns no companies and `Analytics()` calls return empty data. `aa_auto_sdr --show-config` cannot detect this — the first generation attempt is what surfaces the problem.

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
| `SCOPES` | yes | space-separated list (see above) |
| `SANDBOX` | no | optional for sandbox environments |
| `AA_PROFILE` | no | shorthand to set `--profile` |
| `LOG_LEVEL` | no | honored by the CLI's logging |

Per-platform setup:

```bash
# macOS / Linux (current shell)
export ORG_ID="...@AdobeOrg"
export CLIENT_ID="..."
export SECRET="..."
export SCOPES="openid AdobeID read_organizations additional_info.projectedProductContext additional_info.job_function"

# Windows cmd
setx ORG_ID "...@AdobeOrg"
setx CLIENT_ID "..."
# ...

# PowerShell
$Env:ORG_ID = "...@AdobeOrg"
$Env:CLIENT_ID = "..."
# ...
```

See the [upstream SDK env-var auth guide](https://github.com/pitchmuc/adobe-analytics-api-2.0/blob/master/docs/authenticating_without_config_json.md) for more on env-based setup, especially in CI / server environments.

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
  "scopes": "openid AdobeID read_organizations additional_info.projectedProductContext additional_info.job_function",
  "sandbox": null
}
```

### Option 4 — `.env` file

If `python-dotenv` is installed (it's an optional extra), the tool also reads `.env` from the working directory:

```env
ORG_ID=...@AdobeOrg
CLIENT_ID=...
SECRET=...
SCOPES=openid AdobeID read_organizations additional_info.projectedProductContext additional_info.job_function
```

Same fields, same gitignore.

## Multi-org / sandbox setups

Each Adobe organization needs its own profile (or its own credential set). The named-profile workflow is built for this:

```bash
uv run aa_auto_sdr --profile-add client-a
uv run aa_auto_sdr --profile-add client-b
uv run aa_auto_sdr --list-reportsuites --profile client-a
uv run aa_auto_sdr --list-reportsuites --profile client-b
```

Profiles are isolated under `~/.aa/orgs/<name>/`. Snapshot files are also profile-scoped: `~/.aa/orgs/<name>/snapshots/<RSID>/<ts>.json`.

## Diagnostics

```bash
uv run aa_auto_sdr --show-config
```

Prints which credential source resolved, the truncated client_id (no secret exposure), and the sandbox value.

## Common failure modes

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `error: Profile 'X' not found at ~/.aa/orgs/X/config.json` | `--profile X` referenced a non-existent profile | Run `aa_auto_sdr --profile-add X` or fix the path |
| `auth error: ...` (exit 11) | Bad client_id/secret or wrong scopes | Verify in Developer Console; confirm `additional_info.job_function` is in SCOPES |
| `--list-reportsuites` returns empty even though auth succeeded | Integration not on a Product Profile in Admin Console | Add the integration to a Product Profile |
| `403 Forbidden` on `/dimensions` or `/metrics` | Missing `additional_info.job_function` scope | Update SCOPES to include it |
| `error: report suite 'X' not found` (exit 13) | Typo or wrong org for the credentials | `aa_auto_sdr --list-reportsuites` to see what's actually visible |

For full per-code remediation, run `aa_auto_sdr --explain-exit-code <CODE>`.

## See also

- [`QUICKSTART.md`](QUICKSTART.md) — the 5-step onboarding flow
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md) — every flag with examples
- [Adobe I/O Console](https://developer.adobe.com/console) — credential setup
- [`aanalytics2` SDK getting-started](https://github.com/pitchmuc/adobe-analytics-api-2.0/blob/master/docs/getting_started.md) — underlying SDK auth flow
