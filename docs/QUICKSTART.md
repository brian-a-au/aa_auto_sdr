# Extended Quick Start Guide

A step-by-step walkthrough to generate your first Solution Design Reference (SDR) document from an Adobe Analytics report suite.

This guide assumes you're starting from scratch and walks through every step with explanations. By the end, you'll have a professionally formatted Excel workbook cataloging an entire report suite's configuration — dimensions, metrics, segments, calculated metrics, virtual report suites, and classification datasets.

**Time required:** 15–20 minutes (mostly Adobe Developer Console setup)

> **In a hurry?** The fast path is four commands: `uv sync`, set credentials, `uv run aa_auto_sdr --list-reportsuites`, then `uv run aa_auto_sdr <RSID>`. The sections below explain each one. For the condensed flag reference, see [`CLI_REFERENCE.md`](CLI_REFERENCE.md).

---

## Table of Contents

1. [Prerequisites Checklist](#prerequisites-checklist)
2. [Step 1: Set Up Adobe Developer Console](#step-1-set-up-adobe-developer-console)
3. [Step 2: Install the Tool](#step-2-install-the-tool)
4. [Step 3: Configure Authentication](#step-3-configure-authentication)
5. [Step 4: Verify Your Setup](#step-4-verify-your-setup)
6. [Step 5: Generate Your First SDR](#step-5-generate-your-first-sdr)
7. [Step 6: Understand the Output](#step-6-understand-the-output)
8. [Step 7: Capture a Snapshot and Track Changes](#step-7-capture-a-snapshot-and-track-changes)
9. [Next Steps](#next-steps)
10. [Common First-Run Issues](#common-first-run-issues)
11. [Getting Help](#getting-help)

---

## Prerequisites Checklist

Before starting, ensure you have:

- [ ] **Adobe Analytics Access** — Access to an Adobe Analytics company with at least one report suite (RSID) you can see
- [ ] **Adobe Developer Console Access** — Permission to create API integrations
- [ ] **Admin Console Access (or an admin who can help)** — The integration must be added to an Adobe Analytics **Product Profile** before any report suites become visible (see [Step 1.5](#15-add-the-integration-to-a-product-profile))
- [ ] **uv package manager** (recommended) — Install from [astral.sh/uv](https://docs.astral.sh/uv/) (see [Step 2.1](#21-install-uv-package-manager) below). `uv` automatically manages Python for you — no separate Python install needed.
- [ ] **Terminal/Command Line** — Basic familiarity with running commands ([terminal basics guide](https://developer.mozilla.org/en-US/docs/Learn/Tools_and_testing/Understanding_client-side_tools/Command_line))
- [ ] **20 minutes** — Most time is spent on Adobe Developer Console setup

> **Read-only by design.** `aa_auto_sdr` only ever reads from Adobe Analytics. It never creates, updates, or deletes anything in your environment — no segments, no calculated metrics, no classifications. The only local writes are SDR output files, snapshots, and profiles in your home directory.

> **Can't install uv?** You can use pip instead — you'll need Python 3.14+ installed manually ([download Python](https://www.python.org/downloads/)). `uv` is strongly recommended because it manages the Python version for you.

---

## Step 1: Set Up Adobe Developer Console

The tool connects to Adobe Analytics through Adobe's official **2.0 API**. You need to create an API integration to get authentication credentials. `aa_auto_sdr` uses **OAuth Server-to-Server** — this is the only supported auth method.

### 1.1 Access the Developer Console

1. Go to [Adobe Developer Console](https://developer.adobe.com/console/)
2. Sign in with your Adobe ID (the one with Adobe Analytics access)
3. Ensure you're in the correct organization (check the top-right dropdown)

### 1.2 Create a New Project

1. Click **"Create new project"** (or use an existing project)
2. Give your project a descriptive name: `AA SDR Generator`
3. Click **"Save"**

### 1.3 Add the Adobe Analytics API

1. In your project, click **"Add API"**
2. Search for **"Adobe Analytics"**
3. Select **"Adobe Analytics"**
4. Click **"Next"**

### 1.4 Configure Authentication

Choose **OAuth Server-to-Server** (the only supported method):

1. Select **"OAuth Server-to-Server"**
2. Click **"Next"**
3. Select a product profile that has access to your report suites
4. Click **"Save configured API"**

After setup, the console shows you the scopes the integration is granted. The `SCOPES` value must include these **three** scopes, validated against a live Adobe Analytics 2.0 org for the read surface this tool exercises:

```
openid
AdobeID
additional_info.projectedProductContext
```

> **Recommended (broader coverage):** `read_organizations` and `additional_info.job_function` are commonly included and may be required by your org's IMS rules, but neither is empirically required for the current read surface. Add them if `--list-reportsuites` returns empty or `/dimensions` / `/metrics` return 403. See [`CONFIGURATION.md`](CONFIGURATION.md#2-required-scopes) for the full scope reference.

### 1.5 Add the Integration to a Product Profile

> **⚠ Required — do not skip this step.** Adding the API in Developer Console is not enough on its own. The **service account** behind your integration must be added to an Adobe Analytics **Product Profile** in the Admin Console — the profile that contains the report suites you want to document. Without this, authentication can succeed while **no report suites are visible at all**.

1. Open the **Adobe Admin Console** ([adminconsole.adobe.com](https://adminconsole.adobe.com/))
2. Open your **Adobe Analytics** product
3. Open the **Product Profile** that contains the report suites you want to access
4. Add the integration (the one you just created in Developer Console) to that profile

> **Why this matters:** Your own user permissions do **not** carry over to API calls. The integration's service account is a separate identity that must be granted access explicitly. In the underlying SDK flow, `Login().getCompanyId()` returns no companies and report-suite calls come back empty until this is done. `--show-config` cannot detect the gap — the first `--list-reportsuites` run is what surfaces it.

### 1.6 Collect Your Credentials

You need these four values:

| Field | Where to Find It | Example |
|-------|------------------|---------|
| **Organization ID** | Top-right of console, or project overview | `D0F83C645C5E1CC60A495CB3@AdobeOrg` |
| **Client ID** | OAuth Server-to-Server → Credentials | `cm12345abcdef...` |
| **Client Secret** | Click "Retrieve client secret" | `p8e-ABC123...` |
| **Scopes** | OAuth Server-to-Server → Scopes | `openid,AdobeID,additional_info.projectedProductContext` |

> **Important:** Keep these credentials secure. Never commit them to version control. The config and `.env` files this tool reads are already in `.gitignore`.

---

## Step 2: Install the Tool

### 2.1 Install uv Package Manager

[`uv`](https://docs.astral.sh/uv/) is a modern Python package manager that's faster and more reliable than pip. ([What's a package manager?](https://realpython.com/what-is-pip/) — pip concepts apply to uv.)

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Restart your terminal, then verify:
```bash
$ uv --version
uv 0.x.x
```

### 2.2 Clone the Repository

Choose where you want to install the tool (your home directory, a projects folder, etc.):

```bash
# Navigate to your preferred location
cd ~/projects  # or any directory you prefer

# Clone the repository
git clone https://github.com/brian-a-au/aa_auto_sdr.git

# Enter the project directory
cd aa_auto_sdr
```

**Alternative: Download ZIP**

If you don't have [git](https://guides.github.com/introduction/git-handbook/) or prefer a download:
1. Download the ZIP from the repository
2. Extract it to your preferred location
3. Open a terminal and navigate to the extracted folder:
   ```bash
   cd ~/Downloads/aa_auto_sdr-main  # adjust path as needed
   ```

### 2.3 Install Dependencies

From inside the `aa_auto_sdr` directory, run:

```bash
uv sync
```

This command:
- Downloads the required Python version automatically (Python 3.14+, if not already present)
- Creates a [virtual environment](https://realpython.com/python-virtual-environments-a-primer/) in `.venv/` (isolates project dependencies)
- Installs all required packages, including the `aanalytics2` Adobe Analytics SDK
- Installs the `aa_auto_sdr` command

> **Optional extras:** `uv sync --all-extras` additionally installs `python-dotenv` (so the tool reads a `.env` file) and the Notion publishing integration. Use it if you plan to use either feature.

### 2.4 Verify Installation

`uv run` automatically uses the project's virtual environment — no activation needed:

```bash
$ uv run aa_auto_sdr -V
aa_auto_sdr 1.21.1
```

> **Important:** All commands in this guide assume you're in the `aa_auto_sdr` directory. If you see "command not found", make sure you're in the right directory and have run `uv sync`.

### Running Commands

You have two equivalent options:

| Method | Command | Notes |
|--------|---------|-------|
| **uv run** (recommended) | `uv run aa_auto_sdr ...` | No venv activation needed; works immediately on macOS/Linux |
| **Activated venv** | `aa_auto_sdr ...` | After activating: `source .venv/bin/activate` (Unix) or `.venv\Scripts\activate` (Windows) |

This guide uses `uv run` for all examples. Both console entry points work: `aa_auto_sdr` and `aa-auto-sdr`.

**Alternative: Manual activation**

If you prefer traditional virtual environment activation:

```bash
# macOS/Linux
source .venv/bin/activate
aa_auto_sdr -V  # same as --version

# Windows PowerShell
.venv\Scripts\activate
aa_auto_sdr -V  # same as --version
```

> **Windows Users:** If `uv run` doesn't work, activate the venv and use `aa_auto_sdr` directly. See [Common First-Run Issues](#windows-uv-run-command-doesnt-work) for troubleshooting.

---

## Step 3: Configure Authentication

You have four ways to supply credentials. Resolution precedence (highest wins): **profile → environment variables → `.env` file → `config.json`**. Run `aa_auto_sdr --show-config` at any time to see which source resolved.

### Option A: Named Profile (Recommended for Daily Use)

A profile stores one org's credentials in your home directory, separate from the project:

```bash
# Create a profile interactively (prompts for ORG_ID / CLIENT_ID / SECRET / SCOPES)
uv run aa_auto_sdr --profile-add prod

# Use it on any command
uv run aa_auto_sdr --profile prod --list-reportsuites
```

This writes `~/.aa/orgs/prod/config.json`. Profiles are the recommended path because snapshots are also profile-scoped (see [Step 7](#step-7-capture-a-snapshot-and-track-changes)).

### Option B: Environment Variables (Recommended for CI/CD)

For automated pipelines or shared environments:

```bash
# macOS / Linux
export ORG_ID="YOUR_ORG_ID@AdobeOrg"
export CLIENT_ID="YOUR_CLIENT_ID"
export SECRET="YOUR_CLIENT_SECRET"
export SCOPES="openid,AdobeID,additional_info.projectedProductContext"
```

```powershell
# Windows PowerShell
$Env:ORG_ID = "YOUR_ORG_ID@AdobeOrg"
$Env:CLIENT_ID = "YOUR_CLIENT_ID"
$Env:SECRET = "YOUR_CLIENT_SECRET"
$Env:SCOPES = "openid,AdobeID,additional_info.projectedProductContext"
```

### Option C: `.env` File

If `python-dotenv` is installed (via `uv sync --all-extras`), the tool reads a `.env` file in the working directory:

```env
ORG_ID=YOUR_ORG_ID@AdobeOrg
CLIENT_ID=YOUR_CLIENT_ID
SECRET=YOUR_CLIENT_SECRET
SCOPES=openid,AdobeID,additional_info.projectedProductContext
```

`.env` is in `.gitignore` — it won't be committed.

### Option D: `config.json` in the Working Directory

```bash
# Generate a template
uv run aa_auto_sdr --sample-config > config.json
# Then edit config.json with your four values
```

```json
{
  "org_id": "YOUR_ORG_ID@AdobeOrg",
  "client_id": "YOUR_CLIENT_ID",
  "secret": "YOUR_CLIENT_SECRET",
  "scopes": "openid,AdobeID,additional_info.projectedProductContext"
}
```

`config.json` is in `.gitignore` — it won't be committed.

### Managing Multiple Organizations

If you work across multiple Adobe Organizations (agencies, consultants, enterprises with regional orgs), use **profiles** instead of swapping config files:

```bash
# Create a profile per organization
uv run aa_auto_sdr --profile-add client-a
uv run aa_auto_sdr --profile-add client-b

# Switch between them easily
uv run aa_auto_sdr --profile client-a --list-reportsuites
uv run aa_auto_sdr --profile client-b --list-reportsuites
```

Each profile is isolated under `~/.aa/orgs/<name>/`. For the full credential reference, see [`CONFIGURATION.md`](CONFIGURATION.md).

---

## Step 4: Verify Your Setup

Before generating reports, confirm everything is wired correctly.

### 4.1 Validate Configuration

First, check that your credential **shape** is valid (this does **not** contact Adobe):

```bash
uv run aa_auto_sdr --validate-config
```

Exit `0` means the resolved credentials have the right shape. Exit `10` means a field is missing or the `org_id` is malformed. To see which source resolved without exposing secrets:

```bash
uv run aa_auto_sdr --show-config     # which source won
uv run aa_auto_sdr --config-status   # the full resolution chain, verbose
```

### 4.2 Test the Live Connection

List your accessible report suites to confirm the API connection works end-to-end:

```bash
uv run aa_auto_sdr --list-reportsuites
```

**Successful output** (a fixed-width table of the report suites visible to your credentials):

```
RSID                          NAME
----------------------------  ----------------------------------------
demo.prod                     Demo Production
demo.staging                  Demo Staging
dgeo1xxpnwcidadobestore       Adobe Store
```

**What this tells you:**
- Your credentials are valid
- The API connection works
- The integration is on a Product Profile (otherwise this list is empty)
- You have the RSIDs needed for the next step

> **Empty list despite successful auth?** This almost always means the integration isn't on a Product Profile yet — go back to [Step 1.5](#15-add-the-integration-to-a-product-profile). Less commonly, your org requires the `read_organizations` scope.

> **Tip:** For scripting, use `--format json` or `--output -` to get machine-readable output:
> ```bash
> uv run aa_auto_sdr --list-reportsuites --format json
> uv run aa_auto_sdr --list-reportsuites --output - | jq '.[].rsid'
> ```

### 4.3 Explore Before You Generate (Optional)

You can inspect a report suite without building a full SDR:

```bash
# Virtual report suites visible to your credentials
uv run aa_auto_sdr --list-virtual-reportsuites

# Metadata + per-component counts for one report suite
uv run aa_auto_sdr --describe-reportsuite demo.prod

# Browse one component type at a time (with optional filtering)
uv run aa_auto_sdr --list-metrics demo.prod --filter revenue
uv run aa_auto_sdr --list-dimensions demo.prod --sort name --limit 10
uv run aa_auto_sdr --list-segments demo.prod
uv run aa_auto_sdr --list-calculated-metrics demo.prod
uv run aa_auto_sdr --list-classification-datasets demo.prod
```

See [CLI Reference → Discovery and inspection](CLI_REFERENCE.md#discovery-and-inspection) for the full set.

### 4.4 Quick Stats (Optional)

For just the component counts — lighter than `--describe-reportsuite`:

```bash
uv run aa_auto_sdr --stats demo.prod
```

This prints `RSID  NAME  DIM  MET  SEG  CALC  VRS  CLS` with no file output — useful for confirming access and gauging report-suite size. With no RSID, it lists every visible report suite.

### 4.5 Dry Run (Optional)

Test the full pre-flight — credential resolution, auth, and RSID resolution — without the heavy component fetch or any file writes:

```bash
uv run aa_auto_sdr demo.prod --dry-run
```

It authenticates, resolves the name/RSID to a canonical RSID, and prints what *would* be written. Remove `--dry-run` to generate for real.

---

## Step 5: Generate Your First SDR

### 5.1 Direct Command (Recommended)

Replace `demo.prod` with one of your own RSIDs from Step 4.2. The positional argument accepts an RSID **or** a report-suite name (case-insensitive exact match):

**macOS/Linux:**
```bash
uv run aa_auto_sdr demo.prod
```

```bash
# By name instead of RSID
uv run aa_auto_sdr "Adobe Store"
```

**Windows (PowerShell):**
```powershell
aa_auto_sdr demo.prod
```

The default format is **Excel**. The output filename keys off the canonical RSID (e.g. `demo.prod.xlsx`).

### 5.2 Pick a Format (Optional)

```bash
uv run aa_auto_sdr demo.prod --format json       # single JSON file
uv run aa_auto_sdr demo.prod --format markdown    # GitHub-friendly Markdown
uv run aa_auto_sdr demo.prod --format all          # excel + csv + json + html + markdown
```

See [`OUTPUT_FORMATS.md`](OUTPUT_FORMATS.md) for every format and the `all` / `reports` / `data` / `ci` aliases.

### 5.3 Scope to One Component Type (Optional)

To slim the SDR by skipping API calls for excluded components:

```bash
uv run aa_auto_sdr demo.prod --metrics-only       # metrics only
uv run aa_auto_sdr demo.prod --dimensions-only    # dimensions only
```

> These cannot be combined with `--snapshot` / `--auto-snapshot` — a filtered snapshot would produce misleading diffs.

### 5.4 Choose Where Output Lands

```bash
uv run aa_auto_sdr demo.prod --output-dir /tmp/sdr   # default is the current directory
uv run aa_auto_sdr demo.prod --open                  # open the file when done (best-effort)
```

### 5.5 Generate Several at Once

Pass two or more identifiers and the tool automatically switches to batch mode — RSIDs and names can be mixed freely:

```bash
uv run aa_auto_sdr demo.prod demo.staging "Adobe Store" --output-dir /tmp/sdr
```

After a batch run, a summary banner prints counts, success rate, total bytes/duration, and a per-RSID ✓/✗ row. A failure on one RSID does not stop the rest.

### 5.6 Locate Your Output

The generated file lands in your output directory (the current directory by default):

```bash
# macOS/Linux
ls -la *.xlsx

# Windows PowerShell
Get-ChildItem *.xlsx
```

Every non-fast-path run also writes a per-run log under `./logs/` (e.g. `logs/SDR_Generation_demo.prod_<UTC_TS>.log`). `logs/` is git-ignored — treat it as ephemeral.

---

## Step 6: Understand the Output

Open the generated Excel file. It contains **7 sheets** — a summary plus one sheet per component type. Every sheet has a frozen header row and an autofilter.

### Sheet 1: Summary

High-level information in a `Field` / `Value` layout:

| Field | Description |
|-------|-------------|
| RSID | The report suite identifier |
| Name | The report suite display name |
| Timezone | The report suite timezone |
| Captured at | When this SDR was generated (ISO-8601) |
| Tool version | The `aa_auto_sdr` version that produced it |
| Dimensions / Metrics / Segments / Calculated Metrics / Virtual Report Suites / Classifications | Component counts |

### Sheet 2: Dimensions

Every dimension (eVar, prop, event, and so on):

| Column | Description |
|--------|-------------|
| id | Unique dimension identifier |
| name | Display name |
| type | Dimension type |
| category | Grouping category |
| parent | Parent component |
| pathable | Whether the dimension supports pathing |
| description | Documentation text (when available) |
| tags | Associated tags |

### Sheet 3: Metrics

Every metric (numeric counter or rate):

| Column | Description |
|--------|-------------|
| id | Unique metric identifier |
| name | Display name |
| type | Metric type |
| category | Grouping category |
| precision | Decimal places |
| segmentable | Whether the metric can be segmented |
| description | Documentation text (when available) |
| tags | Associated tags |
| data_group | Data group (when available) |

### Sheet 4: Segments

Every segment definition:

| Column | Description |
|--------|-------------|
| id | Unique segment identifier |
| name | Display name |
| description | Documentation text |
| rsid | Owning report suite |
| owner_id | Owner identifier |
| definition | The segment rule definition |
| compatibility | Compatibility metadata |
| tags | Associated tags |
| created / modified | Timestamps |

### Sheet 5: Calculated Metrics

Every calculated metric:

| Column | Description |
|--------|-------------|
| id | Unique identifier |
| name | Display name |
| description | Documentation text |
| rsid | Owning report suite |
| owner_id | Owner identifier |
| polarity | Whether higher or lower is "good" |
| precision | Decimal places |
| type | Metric type |
| definition | The formula definition (the API field is `definition`, not `formula`) |
| tags / categories | Associated tags and categories |

### Sheet 6: Virtual Report Suites

Every virtual report suite — a filtered view of a parent report suite:

| Column | Description |
|--------|-------------|
| id | Unique identifier |
| name | Display name |
| parent_rsid | The report suite it filters |
| timezone | Timezone |
| description | Documentation text |
| segment_list | Segments applied to the view |
| curated_components | Curated component list |
| modified | Last modification timestamp |

### Sheet 7: Classifications

Classification datasets compatible with the report suite:

| Column | Description |
|--------|-------------|
| id | Unique identifier |
| name | Display name |
| rsid | Owning report suite |

> **Note on classifications:** Adobe Analytics 2.0 has no endpoint that lists classifications attached to a given dimension (that was a 1.4-only capability). This sheet reflects what the 2.0 API actually exposes — datasets compatible with the report suite — rather than a per-dimension classification view.

---

## Step 7: Capture a Snapshot and Track Changes

Snapshots are the "version control for SDR" feature. A snapshot is a normalized JSON capture of the report suite's state at one point in time. Diffs run on the normalized model, not on rendered files, so reformatting never creates false noise.

### 7.1 Capture on Every Run

```bash
uv run aa_auto_sdr demo.prod --profile prod --auto-snapshot --output-dir /tmp/sdr
```

`--auto-snapshot` is the recommended default: every generate run lands a snapshot under `~/.aa/orgs/prod/snapshots/<RSID>/<ISO-timestamp>.json` (sorted keys, git-diff-friendly). It requires `--profile`. Pair it with retention to bound the store:

```bash
uv run aa_auto_sdr demo.prod --profile prod --auto-snapshot --auto-prune --keep-last 10
```

### 7.2 Diff Against the Previous Capture

After a later run produces a second snapshot:

```bash
uv run aa_auto_sdr demo.prod --compare-with-prev --profile prod
```

`--compare-with-prev` is sugar for `--diff <RSID>@previous <RSID>@latest`. It prints added / removed / modified components with per-field deltas. The token order treats `latest` as the "after" side, so what shows as *added* is what's new since the previous snapshot.

You can also diff any two snapshots explicitly — by file path, by `<RSID>@<timestamp>`, or by git ref:

```bash
uv run aa_auto_sdr --diff a.json b.json
uv run aa_auto_sdr --diff demo.prod@previous demo.prod@latest --profile prod
uv run aa_auto_sdr --diff git:HEAD~1:snap.json git:HEAD:snap.json
```

See [`SNAPSHOT_DIFF.md`](SNAPSHOT_DIFF.md) for the snapshot format, the diff resolver, and every diff modifier (`--summary`, `--side-by-side`, `--warn-threshold`, and more).

---

## Next Steps

Now that you've generated your first SDR, here are common next steps.

### Generate All Formats

```bash
uv run aa_auto_sdr demo.prod --format all      # excel + csv + json + html + markdown
uv run aa_auto_sdr demo.prod --format reports  # excel + markdown (human-facing)
uv run aa_auto_sdr demo.prod --format ci       # json + markdown (CI-friendly)
```

### Batch Across Many Report Suites

```bash
# Explicit batch with parallel workers
uv run aa_auto_sdr --batch demo.prod demo.staging "Adobe Store" --workers 4 --output-dir /tmp/sdr
```

See [CLI Reference → Batch tuning](CLI_REFERENCE.md#batch-tuning) for `--fail-fast` and sampling (`--sample`, `--sample-seed`, `--sample-stratified`).

### Watch a Report Suite for Changes

Continuously monitor and emit a structured NDJSON event whenever components change:

```bash
# Check every hour
uv run aa_auto_sdr demo.prod --watch --interval 1h --profile prod

# Only emit when at least 3 components change
uv run aa_auto_sdr demo.prod --watch --interval 6h --watch-threshold 3 --profile prod
```

Each cycle emits an `aa-watch-event/v1` line on stdout (`baseline`, `change`, or `error`). Press Ctrl-C to stop cleanly. See [CLI Reference → Watch and scheduled](CLI_REFERENCE.md#watch-and-scheduled).

### Roll Up Inventory Across Report Suites

```bash
uv run aa_auto_sdr --inventory-summary                       # all visible report suites
uv run aa_auto_sdr demo.prod demo.staging --inventory-summary --format csv
```

This aggregates component counts (totals, min, max, average per type) plus a per-RSID detail block.

### Track Drift Over a Window

```bash
uv run aa_auto_sdr demo.prod --trending-window 30d --profile prod
```

A rollup across the snapshots already captured in the window — no API contact needed.

### Add a Quality Audit / CI Gate

```bash
# Add naming-pattern and stale-component audits to the SDR
uv run aa_auto_sdr demo.prod --audit-naming --flag-stale

# Emit a machine-readable quality report and fail CI on HIGH+ issues
uv run aa_auto_sdr demo.prod --quality-report json --fail-on-quality HIGH
```

`--fail-on-quality` exits `17` when an issue at or above the threshold exists (the SDR still emits). See [CLI Reference → Quality severity engine](CLI_REFERENCE.md#quality-severity-engine).

### Fill the Official Adobe Template

```bash
uv run aa_auto_sdr demo.prod --template ~/templates/aa_en_BRD_SDR_template.xlsx
```

Fills an existing Adobe BRD/SDR workbook in place, preserving styles and formulas. See [`TEMPLATE_WORKFLOW.md`](TEMPLATE_WORKFLOW.md).

### Publish to Notion

```bash
uv pip install 'aa-auto-sdr[notion]'
export NOTION_TOKEN=secret_...
export NOTION_PARENT_PAGE_ID=<page-id>
uv run aa_auto_sdr demo.prod --format notion
```

See [`NOTION_SETUP.md`](NOTION_SETUP.md) for the full setup, including the optional queryable registry database.

### Enable Tab Completion

```bash
aa_auto_sdr --completion zsh  > ~/.zsh/completions/_aa_auto_sdr
aa_auto_sdr --completion bash > ~/.bash_completion.d/aa_auto_sdr
aa_auto_sdr --completion fish > ~/.config/fish/completions/aa_auto_sdr.fish
```

Re-source your shell config or open a new terminal.

### Quick Reference

Keep [`CLI_REFERENCE.md`](CLI_REFERENCE.md) handy for the full flag inventory and exit codes. For unattended and agent-driven runs, see [`AGENTS.md`](../AGENTS.md).

---

## Common First-Run Issues

### "Profile not found"

```
error: Profile 'prod' not found at ~/.aa/orgs/prod/config.json
```

**Solution:** Create the profile with `uv run aa_auto_sdr --profile-add prod`, or check the name you passed to `--profile`.

### "Authentication failed" (exit 11)

```
auth error: ...
```

**Solutions:**
1. Double-check your `client_id` and `secret` — no extra spaces or quotes
2. Verify the integration is active in Adobe Developer Console
3. Confirm `SCOPES` includes the three required scopes (see [Step 1.4](#14-configure-authentication))
4. Run `uv run aa_auto_sdr --profile-test <name>` to test OAuth live (PASS/FAIL)

### `--list-reportsuites` returns empty (but auth succeeded)

This is the most common first-run surprise.

**Solution:** The integration's service account isn't on a Product Profile yet. Go back to [Step 1.5](#15-add-the-integration-to-a-product-profile) and add it to the Adobe Analytics Product Profile that contains your report suites. If it's already on a profile, try adding the `read_organizations` scope.

### "Report suite not found" (exit 13)

```
error: report suite 'demo.prod' not found
```

**Solutions:**
1. Run `uv run aa_auto_sdr --list-reportsuites` to see what's actually visible
2. Check for a typo, and confirm you're using the credentials for the right org
3. If you passed a name, confirm the case-insensitive exact match resolves

### `403 Forbidden` on `/dimensions` or `/metrics`

**Solution:** Your org's IMS rules may require the `additional_info.job_function` scope for these endpoints. Add it to `SCOPES` and re-test.

### "Permission denied" writing output

```
error: Permission denied writing to ./demo.prod.xlsx
```

**Solutions:**
1. Check the directory's write permissions
2. Close the Excel file if it's already open
3. Point somewhere else: `--output-dir ~/Desktop`

### Windows: "uv run" command doesn't work

**Symptoms (Windows):** `uv run aa_auto_sdr --version` fails, hangs, or shows errors.

**Solution:** Activate the virtual environment and use the command directly:

```text
.venv\Scripts\activate
aa_auto_sdr --version
aa_auto_sdr --list-reportsuites
aa_auto_sdr demo.prod
```

### Windows: NumPy ImportError

**Symptoms (Windows):**
```
ImportError: Unable to import required dependencies:
numpy: Importing the numpy C-extensions failed.
```

**Cause:** Common on Windows with Microsoft Store Python or incompatible binary wheels.

**Solution:**
1. Ensure Python is from [python.org](https://www.python.org/downloads/), not the Microsoft Store
2. Reinstall NumPy with binary wheels:
   ```text
   .venv\Scripts\activate
   pip uninstall numpy
   pip install --only-binary :all: numpy
   ```

### Rate Limiting

```
Warning: rate limited by API, retrying...
```

**This is normal.** The tool automatically retries transient failures (429 / 5xx, connection timeout) with exponential backoff. Large report suites or big batches may trigger rate limits. Tune with `--max-retries`, `--retry-base-delay`, and `--retry-max-delay` if needed.

---

## Getting Help

If you're still stuck:

1. **Check the log file** — every non-fast-path run writes one under `./logs/` (e.g. `logs/SDR_Generation_<RSID>_<UTC_TS>.log`) with the full trail.
2. **Turn up verbosity** — add `--log-level DEBUG` (and `--log-format json` for structured logs).
3. **Look up an exit code** — `aa_auto_sdr --exit-codes` for the table, `aa_auto_sdr --explain-exit-code <CODE>` for per-code remediation.
4. **Review the documentation:**
   - [`CONFIGURATION.md`](CONFIGURATION.md) — credentials, scopes, Product Profile, multi-org
   - [`CLI_REFERENCE.md`](CLI_REFERENCE.md) — every flag with examples
   - [`OUTPUT_FORMATS.md`](OUTPUT_FORMATS.md) — formats and aliases
   - [`SNAPSHOT_DIFF.md`](SNAPSHOT_DIFF.md) — snapshots and diffing
   - [`LOGGING.md`](LOGGING.md) — log output, events, redaction
5. **Report issues:** [GitHub Issues](https://github.com/brian-a-au/aa_auto_sdr/issues)

---

## Summary

You've successfully:

1. Created Adobe Analytics API credentials and added the integration to a Product Profile
2. Installed and configured the tool
3. Verified your setup against the live API
4. Generated your first SDR document
5. Learned to read the output workbook
6. Captured a snapshot and diffed against a previous capture

Your SDR document is now ready to share with your team, include in documentation, or use for data governance audits — and your snapshots give you a running history of how the report suite changes over time.
