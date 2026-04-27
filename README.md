# Adobe Analytics Solution Design Reference Generator

<img width="2750" height="1536" alt="Gemini_Generated_Image_fmlfuefmlfuefmlf" src="https://github.com/user-attachments/assets/28bea7c7-918b-4402-802b-b4a34f4cd77f" />

A production-ready Python CLI that automates the creation of **Solution Design Reference (SDR)** documentation from your Adobe Analytics implementation. **Read-only** against Adobe Analytics. **API 2.0 only**.

Sister project to [`cja_auto_sdr`](https://github.com/brian-a-au/cja_auto_sdr); shares UX conventions, does **not** share code.

## What It Is

A **Solution Design Reference** is the documentation that bridges your business requirements and your analytics implementation. It catalogs every dimension, metric, segment, calculated metric, virtual report suite, and classification dataset in your Adobe Analytics report suite — the single source of truth for what you collect and how it's configured.

**The Problem:** Manual SDR documentation is time-consuming, error-prone, and quickly outdated. Teams export data, format spreadsheets, and cross-reference configurations only to repeat the entire process when components change.

**The Solution:** This tool connects to the Adobe Analytics 2.0 API, extracts every component of a report suite, and renders the result in five formats (Excel, CSV, JSON, HTML, Markdown). It also persists snapshots of the normalized model and produces structured diffs between any two snapshots — version control of SDR.

### How It Works

1. **Authenticates** via Adobe OAuth Server-to-Server (env vars, named profile, `.env`, or `config.json`).
2. **Fetches** every component from your report suite via the Adobe Analytics 2.0 API. Read-only — no writes ever.
3. **Builds** an `SdrDocument` — the normalized, SDK-agnostic boundary type that all renderers and snapshots consume.
4. **Renders** to your chosen format(s) and optionally **persists a snapshot** under `~/.aa/orgs/<profile>/snapshots/` for later diffing.

### Key Features

| Category | Feature |
|----------|---------|
| **Generation** | Single-RSID generation by ID or name (case-insensitive exact match) |
| | Auto-batch when 2+ identifiers are given on the command line; `--batch` flag still supported |
| | RSIDs and names may be mixed freely in one invocation |
| | `--metrics-only` / `--dimensions-only` slim the SDR; skip API calls for excluded types |
| | `--dry-run` previews would-be output paths without writing (auth still validates) |
| | `--open` opens generated output in OS default app after writing |
| | `--show-timings` prints per-stage timings to stderr at end of run |
| | `--run-summary-json PATH` emits a structured JSON run summary to a file or stdout |
| | Continue-on-error across N report suites with summary banner |
| | Five output formats: Excel, CSV, JSON, HTML, Markdown |
| | Four format aliases: `all`, `reports` (excel + markdown), `data` (csv + json), `ci` (json + markdown) |
| | Multi-match name fan-out: a name matching N suites generates N SDRs |
| **Discovery & Inspection** | `--list-reportsuites`, `--list-virtual-reportsuites` |
| | `--describe-reportsuite <RSID>` — metadata + per-component counts |
| | `--list-{metrics,dimensions,segments,calculated-metrics,classification-datasets} <RSID>` |
| | `--stats [<RSID>...]` — quick component counts per RSID without full SDR build |
| | `--interactive` — pick an RSID interactively; emits to stdout for shell composition |
| | `--filter`, `--exclude`, `--sort`, `--limit` on every list command |
| **Snapshot & Diff** | `--snapshot` opt-in persist alongside generation |
| | `--auto-snapshot` saves a snapshot per RSID on every `<RSID>` / `--batch` run |
| | `--auto-prune` + `--keep-last N` / `--keep-since 30d` retention policy |
| | `--list-snapshots [<RSID>]` action — table or json view |
| | `--prune-snapshots [<RSID>] --dry-run` — apply retention policy with optional preview |
| | `--prune-snapshots` confirms before deleting; `--yes` skips the prompt |
| | `--diff <a> <b>` between any two snapshots |
| | Token grammar: bare path / `<rsid>@<ts>` / `<rsid>@latest` / `<rsid>@previous` / `git:<ref>:<path>` |
| | Four diff renderers: console (ANSI-colored), JSON, Markdown, **`pr-comment`** (compact GFM with collapsible `<details>` for GitHub PRs) |
| | Diff modifiers: `--side-by-side`, `--summary`, `--ignore-fields description,tags` |
| | Diff polish: `--quiet-diff`, `--diff-labels A=… B=…`, `--reverse-diff`, `--changes-only`, `--show-only TYPES`, `--max-issues N` |
| | `--warn-threshold N` exits 3 when total changes ≥ N (CI signal) |
| | `$GITHUB_STEP_SUMMARY` auto-append for `--diff` when env var is set |
| | Identity by component ID, never by name (a name change is *modification*) |
| | Value normalization (whitespace, NaN/None/`""`, order-insensitive `tags`/`categories`) suppresses false-positive diffs |
| **Authentication** | OAuth Server-to-Server (env vars / profile / `.env` / `config.json`) |
| | Named profiles for multi-org users (`~/.aa/orgs/<name>/`) |
| | `--show-config` reports which credential source resolved |
| | `--config-status` / `--validate-config` / `--sample-config` for credential introspection |
| | `--profile-add <name>` interactive credential capture |
| | `--profile-list` / `--profile-show NAME` / `--profile-test NAME` / `--profile-import NAME FILE` |
| | `--profile-import` requires `--profile-overwrite` to replace an existing profile |
| **Output** | `--output -` stdout pipe for json (single-RSID generation) and json/markdown (diff) |
| | Machine-readable JSON error envelope on stderr for pipe-path failures |
| | Atomic file writes (temp + rename) for every output format |
| **Reliability** | **Read-only against Adobe Analytics, forever** — CI-enforced via meta-test scanning `src/aa_auto_sdr/api/` for any write-shape SDK call |
| | **API 2.0 only, no 1.4 paths** — CI-enforced via meta-test |
| | 90% coverage gate on the unit slice |
| | CI matrix on Linux + macOS + Windows |
| | Atomic snapshot writes; sorted-key JSON for git-friendly diffs |
| **Developer UX** | `--exit-codes` lists every code; `--explain-exit-code <CODE>` prints meaning + remediation |
| | `--completion {bash,zsh,fish}` emits a static shell-completion script |
| | Sub-100ms fast-path for `-V`/`--version`/`-h`/`--help`/`--exit-codes`/`--explain-exit-code`/`--completion` |
| | `--help` covers every flag |

### Who It's For

- **Adobe Analytics implementers** documenting report suite state for stakeholders or audits
- **Analytics teams** capturing SDR snapshots in git for change tracking
- **Consultants** managing multiple client implementations across orgs (multi-profile)
- **Data Governance** teams needing a structured artifact of every RS configuration over time
- **DevOps Engineers** automating SDR drift detection in CI/CD pipelines

## Quick Start

> **macOS/Linux:** prefix commands with `uv run` (e.g. `uv run aa_auto_sdr --list-reportsuites`).
> **Windows:** activate the venv first (`.venv\Scripts\activate`), then run commands directly.

### 1. Clone the Repository

```bash
git clone https://github.com/brian-a-au/aa_auto_sdr
cd aa_auto_sdr
```

### 2. Install Dependencies

Install [`uv`](https://docs.astral.sh/uv/) — pick whichever path is convenient:

```bash
# macOS / Linux (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or via pip on any platform
pip install uv
```

Sync the project (creates `.venv/` and installs all dependencies):

```bash
uv sync --all-extras
```

**Windows:** activate the virtual environment so subsequent commands work without the `uv run` prefix:

```powershell
.venv\Scripts\activate
```

### 3. Configure Credentials (Adobe Analytics API 2.0, OAuth Server-to-Server)

The Adobe Analytics 2.0 API uses **OAuth Server-to-Server** authentication. JWT auth is fully deprecated as of 2025-01-01 — do not use it.

#### a. Create an Adobe Developer Console project

1. Visit https://developer.adobe.com/console
2. Create a new project (or open an existing one)
3. Add the **Adobe Analytics API**
4. Choose **OAuth Server-to-Server** as the authentication method
5. The console generates: **Org ID**, **Client ID**, **Client Secret**

#### b. Required scopes

The `SCOPES` value must include these **three** scopes (verified minimum for the read surface this tool exercises):

```
openid
AdobeID
additional_info.projectedProductContext
```

These two scopes are **recommended** for fuller endpoint coverage and broader org configurations:

```
read_organizations
additional_info.job_function
```

If your org's IMS rules require either of the recommended scopes for the endpoints this tool calls, you'll see a 403 on `--list-reportsuites` or empty `/dimensions` / `/metrics` responses despite a successful auth handshake. Add them to your `SCOPES` value if that happens.

#### c. Add the integration to a Product Profile

In the **Adobe Admin Console**, add the integration to an Adobe Analytics **Product Profile**. Without this, `Login().getCompanyId()` returns no companies and `Analytics()` calls return empty data. `aa_auto_sdr --show-config` cannot detect this — the first generation attempt is what surfaces the problem.

#### d. Save credentials

Pick **one** of the four sources (resolution precedence: `--profile` → env vars → `.env` → `config.json`):

**Option 1 — Named profile (recommended for daily use):**

```bash
uv run aa_auto_sdr --profile-add prod
```

Walks through prompts for ORG_ID / CLIENT_ID / SECRET / SCOPES and writes `~/.aa/orgs/prod/config.json`. Use with `--profile prod` on subsequent commands.

**Option 2 — Environment variables:**

```bash
# macOS / Linux
export ORG_ID="...@AdobeOrg"
export CLIENT_ID="..."
export SECRET="..."
export SCOPES="openid, AdobeID, additional_info.projectedProductContext"

# Windows cmd
setx ORG_ID "...@AdobeOrg"
setx CLIENT_ID "..."
# ...

# PowerShell
$Env:ORG_ID = "...@AdobeOrg"
$Env:CLIENT_ID = "..."
# ...
```

(See [the upstream SDK env-var auth guide](https://github.com/pitchmuc/adobe-analytics-api-2.0/blob/master/docs/authenticating_without_config_json.md) for more on env-var-based setup, especially for CI/server environments.)

**Option 3 — `config.json` in repo root:**

```bash
cp config.json.example config.json
# Edit config.json — already gitignored
```

**Option 4 — `.env` file** (requires `python-dotenv`, an optional extra): same fields as env vars, in a `.env` file in the working directory.

### 4. Verify Setup & Run

Confirm credentials and connectivity, then generate your first SDR:

```bash
uv run aa_auto_sdr --show-config        # which credential source resolved
uv run aa_auto_sdr --list-reportsuites  # confirms auth + scope; lists visible RSes
uv run aa_auto_sdr <RSID>               # default Excel; <RSID> from the list above
```

**Troubleshooting:**

- If `--show-config` succeeds but `--list-reportsuites` returns empty → the integration isn't on a Product Profile (step c).
- If `--list-reportsuites` returns a 403 or `/dimensions` / `/metrics` come back empty despite a successful auth → try adding the recommended scopes (`read_organizations`, `additional_info.job_function`) per step b.
- For full code-by-code remediation: `uv run aa_auto_sdr --explain-exit-code <CODE>`.

### 5. Review Output

Default format produces `<RSID>.xlsx` in the working directory. Use `--format` for alternates:

```bash
uv run aa_auto_sdr <RSID> --format json    # single JSON file
uv run aa_auto_sdr <RSID> --format all     # all five formats at once
uv run aa_auto_sdr <RSID> --output-dir /tmp/sdr  # custom directory
```

Browse [`sample_outputs/`](sample_outputs/) in this repo to see what each format looks like before running anything.

## Common Use Cases

> Commands below omit the `uv run` prefix for brevity (macOS/Linux: prepend `uv run`; Windows: activate venv first).

| Task | Command |
|------|---------|
| **Getting Started** | |
| List visible report suites | `aa_auto_sdr --list-reportsuites` |
| Show resolved credentials source | `aa_auto_sdr --show-config` |
| Print help | `aa_auto_sdr --help` |
| **SDR Generation** | |
| Single RS by RSID | `aa_auto_sdr dgeo1xxpnwcidadobestore` |
| Single RS by name | `aa_auto_sdr "Adobe Store"` |
| Custom output directory | `aa_auto_sdr <RSID> --output-dir /tmp/sdr` |
| Auto-batch — multiple positional identifiers | `aa_auto_sdr rs1 rs2 rs3` |
| Auto-batch with mixed RSIDs and names | `aa_auto_sdr dgeo1xxpnwcidadobestore "Adobe Store" demo.prod` |
| Batch via explicit flag | `aa_auto_sdr --batch RS1 RS2 RS3` |
| Use a named profile | `aa_auto_sdr <RSID> --profile prod` |
| **Output Formats** | |
| Excel (default) | `aa_auto_sdr <RSID>` |
| JSON | `aa_auto_sdr <RSID> --format json` |
| All five formats | `aa_auto_sdr <RSID> --format all` |
| Pipe JSON to jq | `aa_auto_sdr <RSID> --format json --output - \| jq '.report_suite'` |
| Aliases (excel + markdown) | `aa_auto_sdr <RSID> --format reports` |
| **Discovery & Inspection** | |
| List metrics for one RS | `aa_auto_sdr --list-metrics <RSID>` |
| Filter + sort + limit | `aa_auto_sdr --list-metrics <RSID> --filter page --sort name --limit 10` |
| Describe (counts only) | `aa_auto_sdr --describe-reportsuite <RSID>` |
| List as JSON for scripting | `aa_auto_sdr --list-reportsuites --format json --output -` |
| **Snapshot** | |
| Capture snapshot alongside generation | `aa_auto_sdr <RSID> --snapshot --profile prod` |
| Capture snapshots for multiple RSes (auto-batch) | `aa_auto_sdr RS1 RS2 --snapshot --profile prod` |
| Auto-snapshot every run | `aa_auto_sdr <RSID> --auto-snapshot --profile prod` |
| **Diff** | |
| Diff two snapshot files | `aa_auto_sdr --diff a.json b.json` |
| Diff `@latest` vs `@previous` | `aa_auto_sdr --diff <RSID>@latest <RSID>@previous --profile prod` |
| Diff at a specific timestamp | `aa_auto_sdr --diff <RSID>@2026-04-26T17-29-01+00-00 <RSID>@latest --profile prod` |
| Diff at a git ref | `aa_auto_sdr --diff git:HEAD~1:snapshots/x.json git:HEAD:snapshots/x.json` |
| Diff to JSON pipe | `aa_auto_sdr --diff a.json b.json --format json --output -` |
| Diff to Markdown file | `aa_auto_sdr --diff a.json b.json --format markdown --output diff.md` |
| **Profile / Config** | |
| Create profile interactively | `aa_auto_sdr --profile-add prod` |
| Verify resolved source | `aa_auto_sdr --show-config` |
| **Fast-path / Help** | |
| Print version | `aa_auto_sdr -V` |
| List exit codes | `aa_auto_sdr --exit-codes` |
| Explain one exit code | `aa_auto_sdr --explain-exit-code 11` |
| Generate completion script | `aa_auto_sdr --completion zsh > ~/.zsh/completions/_aa_auto_sdr` |

## Documentation

| Guide | Description |
|-------|-------------|
| [Quickstart](docs/QUICKSTART.md) | 90-second onboarding from clone to first SDR |
| [CLI Reference](docs/CLI_REFERENCE.md) | Every flag with examples + exit codes + token grammar |
| [Configuration](docs/CONFIGURATION.md) | Credential sources, OAuth scopes, profile management, troubleshooting |
| [Snapshot & Diff](docs/SNAPSHOT_DIFF.md) | Snapshot file format, resolver token grammar, diff semantics, common workflows |
| [Output Formats](docs/OUTPUT_FORMATS.md) | Five formats + four aliases, when to use each, file layouts |
| [Sample Outputs](sample_outputs/) | Browse representative outputs without installing |

## Requirements

- Python 3.14+
- Adobe Developer Console project with **Adobe Analytics API** access (OAuth Server-to-Server)
- Integration added to an Adobe Analytics **Product Profile** in Admin Console
- Network connectivity to Adobe APIs

## Project Structure

High-level layout (representative, not exhaustive):

```
aa_auto_sdr/
├── .github/
│   └── workflows/             # tests, lint, version-sync, release-gate
├── src/
│   └── aa_auto_sdr/           # main package (src layout)
│       ├── __init__.py
│       ├── __main__.py        # fast-path entry (sub-100ms for --version/--help/--exit-codes/--completion)
│       ├── api/               # aanalytics2 wrapper, auth, fetchers, normalized models
│       │   ├── client.py      # only file (besides auth/fetch) that imports aanalytics2
│       │   ├── auth.py
│       │   ├── fetch.py       # per-component fetchers; coerces SDK shapes
│       │   └── models.py      # normalized dataclasses (boundary types)
│       ├── cli/               # argparse + dispatch
│       │   ├── parser.py
│       │   ├── main.py
│       │   ├── list_output.py # table/json/csv rendering for list/inspect
│       │   └── commands/      # one module per command
│       ├── core/              # cross-cutting utilities
│       │   ├── version.py     # canonical __version__
│       │   ├── exceptions.py  # typed exception hierarchy
│       │   ├── exit_codes.py  # central ExitCode enum + ROWS + EXPLANATIONS
│       │   ├── colors.py      # ANSI helpers (auto-disabled for non-TTY / NO_COLOR)
│       │   ├── credentials.py # OAuth credential resolution + precedence
│       │   ├── profiles.py    # ~/.aa/orgs/<name>/ profile CRUD
│       │   ├── constants.py   # BANNER_WIDTH, etc.
│       │   └── json_io.py     # atomic JSON read/write
│       ├── output/            # format writers + diff renderers + error envelope
│       │   ├── protocols.py
│       │   ├── registry.py
│       │   ├── error_envelope.py  # JSON envelope on stderr for pipe-path failures
│       │   ├── _helpers.py
│       │   ├── writers/       # excel.py, csv.py, json.py, html.py, markdown.py
│       │   └── diff_renderers/  # console.py, json.py, markdown.py
│       ├── pipeline/          # run coordination
│       │   ├── single.py      # single-RSID
│       │   ├── batch.py       # multi-RSID, sequential, continue-on-error
│       │   └── models.py      # RunResult, BatchResult, BatchFailure
│       ├── sdr/               # SDR assembly
│       │   ├── builder.py     # pure: AaClient + RSID -> SdrDocument
│       │   └── document.py    # SdrDocument boundary type
│       └── snapshot/          # version control of SDR
│           ├── store.py       # save/load + path convention
│           ├── schema.py      # aa-sdr-snapshot/v1 envelope + validator
│           ├── resolver.py    # token grammar dispatcher
│           ├── git.py         # git show wrapper
│           ├── comparator.py  # diff algorithm + value normalization
│           └── models.py      # DiffReport, ComponentDiff, FieldDelta
├── tests/                     # pytest suite — unit / integration / meta
│   └── meta/                  # CI-enforced architectural invariants
├── scripts/
│   ├── check_version_sync.py  # version drift gate
│   └── build_sample_outputs.py  # deterministic sample generator
├── docs/                      # user-facing markdown (gitignored docs/superpowers/ excluded)
├── sample_outputs/            # representative outputs, generated from fixture
├── pyproject.toml
├── uv.lock
├── README.md                  # this file
├── CHANGELOG.md
├── LICENSE
├── config.json.example
└── .env.example
```

## License

See [LICENSE](LICENSE) for details (MIT).

## Additional Resources

- [Adobe Analytics 2.0 API documentation](https://developer.adobe.com/analytics-apis/docs/2.0/)
- [`aanalytics2` Python wrapper](https://github.com/pitchmuc/adobe-analytics-api-2.0) — the underlying SDK
- [`uv` package manager](https://github.com/astral-sh/uv)
- [Sister project: `cja_auto_sdr`](https://github.com/brian-a-au/cja_auto_sdr) — Customer Journey Analytics equivalent
