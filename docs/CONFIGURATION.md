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

Pick one source. Resolution precedence (highest wins):

1. `--profile <name>` or `--config <path>`. Giving both is an error (exit 2).
2. The `AA_PROFILE` env var, which names a profile
3. Environment variables already in the shell
4. `.env` file in the working directory
5. `config.json` in the working directory

The four fields always come from one source. The tool does not take some fields from one source and the rest from another.

Run `aa_auto_sdr --show-config` to see which source resolved for a given invocation.

### How the lookup treats each source

- **A profile or a `--config` file** must hold all four fields. If the profile is missing, or a field is missing, the run stops with exit 10. It does not fall back to another source.
- **The environment variables, `.env` and `config.json`** are skipped when they hold some of the four fields and not all of them. The tool prints a notice on stderr that names the missing fields, and goes on to the next source. A later major release will stop with an error here.
- **`.env` beats `config.json`.** When both files in the working directory hold a complete credential and the two differ, the tool uses `.env` and prints a notice that says so.
- **A `.env` file that cannot be read**, e.g., because of its permissions or because it is not UTF-8, is skipped with a warning on stderr.
- **Unknown keys** in a JSON credential file are ignored. With `--log-level DEBUG` the log names each one. `sandbox` is accepted and ignored.

A notice or a warning is one line on stderr that starts with `notice:` or `warning:`. It is printed once per run. It never goes to stdout and never changes the exit code.

### File permissions

The tool writes a profile file with mode 0600 and creates new profile folders with mode 0700. A folder that already exists keeps its mode.

When the tool reads a credential file that the group or other users can read, it prints one warning with the fix, e.g., `chmod 600 config.json`. The check follows a symlink to its target. It is skipped on Windows.

### Check the configuration without calling Adobe

`aa_auto_sdr --config-status` reports how the tool finds the credential. It makes no network call. It shows:

- Every source in order, and which one matched.
- A source that was skipped because it is partial, with the missing fields.
- The file path of the source that matched.
- The client ID, masked as the first 4 characters, `****`, and the last 4 characters.
- The secret as `****` when it is set. The tool never prints any character of the secret.
- The scopes.

Add `--format json` to `--config-status` or `--show-config` for JSON on stdout. The JSON has `"schema": "adobe-credentials/v1/config-check"` and reports the secret as `secret_set: true` or `false`. It lists the sources, the problems, the notices and the warnings. The exit code is 0 when a credential was found and 10 when not.

### Test a profile against Adobe

`aa_auto_sdr --profile-test <name>` reports two results, because one can pass while the other fails:

- **Sign-in.** The tool asks Adobe's sign-in service for a token.
- **Company check.** The tool asks Adobe Analytics which companies the credential sees. This runs only when sign-in worked.

A failed result has a code:

| Code | Result | Meaning |
|------|--------|---------|
| `bad_client_id` | sign-in | Adobe does not know the client ID. |
| `bad_secret` | sign-in | Adobe knows the client ID and rejected the secret. |
| `scopes_rejected` | sign-in | Adobe rejected one or more scopes. |
| `sign_in_failed` | sign-in | Sign-in failed for another reason. The message holds Adobe's own text, cut to 200 characters. |
| `no_product_access` | company check | Sign-in worked and the credential sees no Analytics company. Add the credential's technical account to an Analytics product profile in the Admin Console. |
| `unreachable` | either | The tool could not reach Adobe, or the answer did not come from Adobe. |

Add `--format json` for JSON on stdout with `"schema": "adobe-credentials/v1/live-test"`.

The shared rules behind these commands are the Adobe credentials standard, version 1. `known-differences.json` in the repository root lists the rules this tool does not meet yet.

### Option 1 — Named profile (recommended for daily use)

```bash
uv run aa_auto_sdr --profile-add prod
```

Walks through prompts for ORG_ID / CLIENT_ID / SECRET / SCOPES and writes:

```
~/.aa/orgs/prod/config.json
```

Use with `--profile prod` on subsequent commands. Multi-org users create one profile per org.

Every answer must have a value; an empty answer stops the command with exit 10. Press Ctrl+C to cancel; the command exits 130. In both cases no profile is written.

A profile name is one folder under `~/.aa/orgs/`. A name holds letters, digits, dots, underscores and hyphens only. It starts with a letter or a digit, and it is 64 characters or fewer. Every command that reads or writes a profile checks the name first and exits 10 with `error: invalid profile name '<name>'` when the name breaks the rule.

A profile that already exists under a name that breaks the rule, e.g., a name with a space, still works. The tool prints one warning. A name that could point outside `~/.aa/orgs/`, e.g., `../other`, is always refused.

### A credential file at any path

```bash
uv run aa_auto_sdr --list-reportsuites --config /path/to/credential.json
```

`--config <path>` reads the four fields from a JSON file with the same keys as a profile. You cannot give `--config` together with `--profile`.

### Option 2 — Environment variables

| Variable | Required | Notes |
|----------|----------|-------|
| `ORG_ID` | yes | e.g. `D0F83C645C5E1CC60A495CB3@AdobeOrg` |
| `CLIENT_ID` | yes | from Developer Console |
| `SECRET` | yes | the OAuth client secret |
| `SCOPES` | yes | comma-separated list (see above). Write it without spaces after the commas. The tool passes the value to Adobe as written. |
| `AA_PROFILE` | no | names the profile to use when neither `--profile` nor `--config` is given |
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

The tool also reads `.env` from the working directory. It reads the file as a source of its own, and it does not search parent folders:

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

Credentials are env vars only — they are **not** stored in profile `config.json`. The Notion commands also read these variables from a `.env` file. For these variables the file is loaded into the environment, and parent folders are searched. This happens after the Adobe credential lookup, so it does not change which Adobe credential a run uses. A single `.env` file can hold both the Adobe keys and the Notion keys, because the variable names do not overlap. See [`CLI_REFERENCE.md`](CLI_REFERENCE.md#notion-integration) for usage examples.

## See also

- [`QUICKSTART.md`](QUICKSTART.md) — the step-by-step onboarding walkthrough
- [`CLI_REFERENCE.md`](CLI_REFERENCE.md) — every flag with examples
- [`LOGGING.md`](LOGGING.md) — log output, events, redaction
- [Adobe I/O Console](https://developer.adobe.com/console) — credential setup
- [`aanalytics2` SDK getting-started](https://github.com/pitchmuc/adobe-analytics-api-2.0/blob/master/docs/getting_started.md) — underlying SDK auth flow
