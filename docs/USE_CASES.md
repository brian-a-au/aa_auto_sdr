# Use Cases & Best Practices

Scenario playbooks and recommended practices for `aa_auto_sdr`. Each scenario explains *why* you'd reach for the tool and the *workflow* to get there. For the command index see [`QUICK_REFERENCE.md`](QUICK_REFERENCE.md); for per-flag detail see [`CLI_REFERENCE.md`](CLI_REFERENCE.md).

> Commands omit the `uv run` prefix for brevity (macOS/Linux: prepend `uv run`; Windows: activate the venv first).

## Table of contents

- [Use cases](#use-cases)
  - [Implementation audit](#implementation-audit)
  - [Implementation verification](#implementation-verification)
  - [Data quality assurance](#data-quality-assurance)
  - [Team onboarding](#team-onboarding)
  - [Change management](#change-management)
  - [Multi-environment comparison](#multi-environment-comparison)
  - [Compliance documentation](#compliance-documentation)
  - [Migration & consolidation planning](#migration--consolidation-planning)
  - [Discovery & inspection](#discovery--inspection)
  - [Drift detection in CI/CD](#drift-detection-in-cicd)
  - [Automated audit trail](#automated-audit-trail)
  - [Multi-organization management](#multi-organization-management)
  - [Quick comparison against previous state](#quick-comparison-against-previous-state)
  - [Org-wide inventory rollup](#org-wide-inventory-rollup)
  - [Continuous monitoring](#continuous-monitoring)
  - [Stakeholder deliverables via template-fill](#stakeholder-deliverables-via-template-fill)
  - [Publishing to Notion](#publishing-to-notion)
- [Best practices](#best-practices)
- [Target audiences](#target-audiences)
- [See also](#see-also)

---

## Use cases

### Implementation audit

Understand the breadth and depth of a report suite at a glance: total dimensions (eVars, props, events), metrics, segments, calculated metrics, virtual report suites, and classification datasets, plus configuration completeness.

**Best for:** quarterly reviews, taking stock of an inherited implementation.

```bash
aa_auto_sdr demo.prod --output-dir ./audits/$(date +%Y%m%d)
```

### Implementation verification

Confirm an implementation matches the plan: capture a baseline snapshot, then capture again after the work and diff the two to surface drift, missing components, or renamed fields. Diffs always run snapshot-against-snapshot — there is no live-against-snapshot mode — so capture state at each checkpoint.

**Best for:** post-implementation validation, sign-off against a planning document.

```bash
# Capture a baseline before the work
aa_auto_sdr demo.prod --auto-snapshot --profile prod

# After the implementation work, capture again and diff the two most recent snapshots
aa_auto_sdr demo.prod --auto-snapshot --profile prod
aa_auto_sdr demo.prod --compare-with-prev --profile prod
```

### Data quality assurance

Maintain a clean implementation with the severity-tagged quality engine: audit naming patterns, flag stale components, and track issues over time. Findings are severity-tagged (`CRITICAL` → `INFO`) and can be exported or promoted to a gate.

**Best for:** ongoing maintenance, standardization initiatives.

```bash
# Naming + stale audits added to the SDR
aa_auto_sdr demo.prod --audit-naming --flag-stale

# Standalone machine-readable quality report
aa_auto_sdr demo.prod --audit-naming --quality-report json --output-dir ./quality

# Fail when any issue is at or above HIGH (exit 17)
aa_auto_sdr demo.prod --fail-on-quality HIGH
```

### Team onboarding

Give new team members a complete component reference: what's collected, how it's named, and how virtual report suites and classifications are configured. Markdown and HTML formats are the most readable for sharing.

**Best for:** training, knowledge transfer, documentation handoff.

```bash
aa_auto_sdr demo.prod --format reports          # excel + markdown
aa_auto_sdr demo.prod --format html --output-dir ./onboarding
```

### Change management

Document configuration before and after a change using snapshots and diffs. Diffs run on the normalized model, not on rendered files, so reformatting never creates false noise. Identity is by component ID — a name change reads as a *modification*, not an add plus a remove.

**Best for:** release management, change-control processes.

```bash
# Capture a baseline before the change
aa_auto_sdr demo.prod --auto-snapshot --profile prod

# After the change, capture again and diff the two most recent snapshots
aa_auto_sdr demo.prod --auto-snapshot --profile prod
aa_auto_sdr demo.prod --compare-with-prev --profile prod

# Produce a Markdown diff for stakeholders
aa_auto_sdr --diff demo.prod@previous demo.prod@latest --profile prod \
  --format markdown --output ./reports/change.md
```

### Multi-environment comparison

Compare two report suites directly to keep environments aligned — for example a production suite against a staging or development suite.

**Best for:** environment management, pre-deployment parity checks.

```bash
# Diff two snapshots with friendly labels
aa_auto_sdr --diff prod.json staging.json --diff-labels A=Production B=Staging

# Show only the differences
aa_auto_sdr --diff prod.json staging.json --changes-only

# Focus on one component type
aa_auto_sdr --diff prod.json staging.json --show-only metrics
```

### Compliance documentation

Generate an audit-ready, timestamped artifact of every component in a report suite, and keep a versioned history. Each SDR records the capturing tool version and capture time; snapshots can be committed to git for a tamper-evident trail.

**Best for:** SOC 2, ISO, and internal audit requirements.

```bash
# Audit-ready outputs in every format
aa_auto_sdr demo.prod --format all --output-dir ./compliance/$(date +%Y%m%d)

# Versioned snapshot committed to git
aa_auto_sdr demo.prod --auto-snapshot --git-commit --profile prod
```

### Migration & consolidation planning

Prepare for report-suite migrations or consolidations by documenting current state, then validating that only intended changes occurred. Snapshot diffing gives a clean before/after for sign-off without re-calling the API.

**Best for:** platform migrations, report-suite consolidation, major reconfigurations.

```bash
# Before: capture the baseline
aa_auto_sdr demo.prod --auto-snapshot --profile prod

# After the migration: capture again, then diff the two snapshots (no API calls)
aa_auto_sdr demo.prod --auto-snapshot --profile prod
aa_auto_sdr --diff demo.prod@previous demo.prod@latest --profile prod --format markdown \
  --output ./migration/signoff.md
```

### Discovery & inspection

Explore what exists before building a full SDR: list report suites and virtual report suites, describe a single suite's metadata and counts, or browse one component type at a time.

**Best for:** pre-SDR exploration, quick component checks, CI validation, onboarding.

```bash
# What report suites can these credentials see?
aa_auto_sdr --list-reportsuites

# Metadata + per-component counts for one suite
aa_auto_sdr --describe-reportsuite demo.prod

# Quick counts only (lighter than describe)
aa_auto_sdr --stats demo.prod

# Browse and filter one component type
aa_auto_sdr --list-metrics demo.prod --filter revenue --sort name
aa_auto_sdr --list-dimensions demo.prod --format csv --output dims.csv
```

### Drift detection in CI/CD

Catch unexpected configuration changes in a pipeline. The diff action returns exit `3` when `--warn-threshold` is exceeded; the quality gate returns exit `17` when `--fail-on-quality` is breached. The `pr-comment` renderer produces compact GitHub-ready output, and when `$GITHUB_STEP_SUMMARY` is set every `--diff` run also appends a render to the job summary automatically.

**Best for:** DevOps, continuous integration, deployment gates.

```bash
# Drift check that fails the build when changes are large
aa_auto_sdr --diff prod.json staging.json --warn-threshold 10 --quiet-diff
echo "Exit code: $?"   # 0 = within threshold, 3 = warn-threshold exceeded

# PR-comment output to a file, then post it
aa_auto_sdr --diff prod.json staging.json --format pr-comment --output pr-comment.md
gh pr comment --body-file pr-comment.md

# Quality gate in CI
aa_auto_sdr demo.prod --fail-on-quality HIGH
```

**GitHub Actions — drift check with PR comment:**

```yaml
name: SDR Drift Check
on:
  pull_request:
    branches: [main]

jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync

      - name: Diff against committed baseline
        run: |
          uv run aa_auto_sdr --diff baseline.json git:HEAD:snapshots/demo.prod.json \
            --warn-threshold 10 --format pr-comment --output pr-comment.md
        continue-on-error: true

      - name: Comment on PR
        if: github.event_name == 'pull_request'
        run: gh pr comment --body-file pr-comment.md
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### Automated audit trail

Maintain a history of changes without manual bookkeeping. Auto-snapshot on every run, apply a retention policy to bound storage, and optionally commit each snapshot to a git repo for a versioned trail.

**Best for:** compliance, historical tracking, zero-friction auditing.

```bash
# Auto-snapshot with retention (keep the last 30 per RSID)
aa_auto_sdr demo.prod --auto-snapshot --auto-prune --keep-last 30 --profile prod

# Git-versioned trail (auto-inits the snapshot dir as a repo on first use)
aa_auto_sdr demo.prod --auto-snapshot --git-commit --profile prod
aa_auto_sdr demo.prod --auto-snapshot --git-commit --git-push --profile prod
```

**Scheduled trail (cron):**

```bash
# Weekly capture, Monday 09:00, with retention
0 9 * * 1 cd /path/to/project && uv run aa_auto_sdr demo.prod \
  --auto-snapshot --auto-prune --keep-last 52 --git-commit --profile prod
```

### Multi-organization management

Manage SDRs across several Adobe organizations without swapping config files. Each org gets a named profile under `~/.aa/orgs/`; snapshots are profile-scoped so they never collide.

**Best for:** agencies, consultants, enterprises with regional orgs or multiple brands.

```bash
# One-time setup
aa_auto_sdr --profile-add client-a
aa_auto_sdr --profile-add client-b

# Generate per organization
aa_auto_sdr "Production" --profile client-a --format excel
aa_auto_sdr "Main RS"    --profile client-b --format excel

# Verify connectivity before a run
aa_auto_sdr --profile-test client-a

# Set a default profile for the session
export AA_PROFILE=client-a
aa_auto_sdr --list-reportsuites
```

**Batch across organizations:**

```bash
#!/bin/bash
for profile in client-a client-b client-c; do
  echo "=== $profile ==="
  uv run aa_auto_sdr --list-reportsuites --profile "$profile" --format json --output - \
    | jq -r '.[].rsid' \
    | xargs -I {} uv run aa_auto_sdr {} --profile "$profile" \
        --output-dir "./reports/$profile/$(date +%Y%m%d)"
done
```

### Quick comparison against previous state

For a one-command answer to "what changed since last time," use `--compare-with-prev` (sugar for `@previous` vs `@latest`). For a rollup across many snapshots, use `--trending-window`. Both read existing snapshots and make no API calls.

```bash
# Compare current state to the most recent snapshot
aa_auto_sdr demo.prod --compare-with-prev --profile prod

# Rollup drift across the last 30 days of snapshots
aa_auto_sdr demo.prod --trending-window 30d --profile prod
```

### Org-wide inventory rollup

Get an organization-wide overview of component volume without building a full SDR for each suite. The rollup reports totals plus min / max / avg per component type, with a per-RSID detail block.

**Best for:** landscape audits, capacity overviews, governance reporting.

```bash
# Every visible report suite
aa_auto_sdr --inventory-summary

# A selected set, as CSV for a spreadsheet
aa_auto_sdr rs1 rs2 rs3 --inventory-summary --format csv

# Machine-readable for a dashboard
aa_auto_sdr --inventory-summary --format json
```

### Continuous monitoring

Watch a report suite for changes on a repeating interval. Each cycle fetches, snapshots, and diffs, emitting one NDJSON event on stdout (`baseline`, `change`, or `error`). Pair with `--agent-mode` and `jq` to react in real time, or with `--format notion` to publish on every change.

**Best for:** real-time drift alerting, always-on documentation.

```bash
# Emit NDJSON events; react with jq
aa_auto_sdr demo.prod --watch --interval 1h --agent-mode --profile prod | jq -c .

# Only emit a change event when 5+ components change
aa_auto_sdr rs1 rs2 --watch --interval 6h --watch-threshold 5 --profile prod

# Publish to Notion whenever the suite changes
aa_auto_sdr demo.prod --watch --interval 1h --format notion --profile prod
```

### Stakeholder deliverables via template-fill

Produce a customer-facing SDR that matches Adobe's official BRD/SDR workbook. Point `--template` at the template and the tool fills component data into the styled sheets while preserving formulas, styles, and untouched cells.

**Best for:** consultant deliverables, customer-facing documentation that must match the official look.

```bash
aa_auto_sdr demo.prod --template ~/aa_en_BRD_SDR_template.xlsx
aa_auto_sdr demo.prod --template ~/aa_en_BRD_SDR_template.xlsx --template-organization "Acme Corp"
```

See [`TEMPLATE_WORKFLOW.md`](TEMPLATE_WORKFLOW.md) for the full first-run, batch, and troubleshooting walkthrough.

### Publishing to Notion

Publish an SDR directly to a Notion page for collaborative, wiki-style documentation, and optionally upsert a row into an SDR Registry database for a queryable index across report suites.

**Best for:** teams that live in Notion, shared component catalogs.

```bash
# One-time setup: install the extra and set credentials (see NOTION_SETUP.md)
uv pip install 'aa-auto-sdr[notion]'
export NOTION_TOKEN=secret_...
export NOTION_PARENT_PAGE_ID=<page-id>

# Publish a detail page (re-runs update in place)
aa_auto_sdr demo.prod --format notion

# Also upsert a registry row per RSID
export NOTION_REGISTRY_DATABASE_ID=<database-id>
aa_auto_sdr --batch rs1 rs2 --format notion
```

See [`NOTION_SETUP.md`](NOTION_SETUP.md) for the step-by-step integration and registry setup.

## Best practices

### Scheduling

Run generation or snapshots regularly to keep documentation current and build history.

**Linux/macOS (cron):**

```bash
crontab -e

# Weekly audit, Monday 09:00
0 9 * * 1 cd /path/to/project && uv run aa_auto_sdr demo.prod --auto-snapshot --profile prod

# Daily batch, 02:00 (escape % in crontab)
0 2 * * * cd /path/to/project && uv run aa_auto_sdr \
  rs1 rs2 --output-dir /reports/$(date +\%Y\%m\%d)
```

**Windows (Task Scheduler):**

```powershell
$action = New-ScheduledTaskAction -Execute "uv" `
  -Argument "run aa_auto_sdr demo.prod --auto-snapshot --profile prod" `
  -WorkingDirectory "C:\path\to\aa_auto_sdr"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9am
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "AA SDR Weekly"
```

### Automation scripts

Wrap common runs in small, reusable scripts.

```bash
#!/bin/bash
# generate_production.sh
cd "$(dirname "$0")/.."
uv run aa_auto_sdr demo.prod --output-dir ./reports/production --quiet
```

Process a list of report suites from a file:

```bash
# rsids.txt holds one RSID per line
uv run aa_auto_sdr $(cat rsids.txt) --output-dir ./reports/$(date +%Y%m%d)
```

### Data quality management

Triage quality findings by severity:

1. **CRITICAL** — fix before relying on the report.
2. **HIGH** — schedule a fix within the current sprint.
3. **MEDIUM** — backlog; fix opportunistically.
4. **LOW / INFO** — address during routine documentation updates.

Track quality over time by writing timestamped reports and gating CI:

```bash
aa_auto_sdr demo.prod --audit-naming --quality-report json \
  --output-dir ./quality/week_$(date +%V)
aa_auto_sdr demo.prod --fail-on-quality HIGH
```

### Version control

Commit dependency state; never commit credentials or generated artifacts.

```bash
# Commit
git add pyproject.toml uv.lock

# .gitignore (config.json and .env are already ignored in this repo)
# config.json
# .env
# .venv/
# logs/
# *.xlsx
```

For a versioned snapshot history, let the tool manage a git repo in the snapshot directory with `--git-commit` rather than committing snapshots into your project repo.

### Security

- Never commit `config.json` or `.env`.
- Use a dedicated service-account integration for automated runs.
- Rotate the client secret periodically.
- The tool is read-only against Adobe Analytics, so a leaked credential cannot mutate your environment — but it can still read it, so treat secrets accordingly.

### Performance

- **Parallelize batches** with `--workers N` (1..16); add `--fail-fast` to stop on the first failure.
- **Sample** large batches with `--sample N` (use `--sample-seed` for reproducibility, `--sample-stratified` to balance by code prefix).
- **Scope** generation with `--metrics-only` / `--dimensions-only` to skip API calls for excluded types.
- **Preview** with `--dry-run` before a heavy run.
- **Tune retries** for flaky orgs with `--max-retries` / `--retry-base-delay` / `--retry-max-delay`.

| Scenario | Suggested `--workers` |
|----------|----------------------|
| Shared org with tight rate limits | 2 |
| Typical batch | 4 |
| Dedicated infrastructure | 8+ (cap 16) |

### CI/CD integration

```yaml
name: Generate SDR
on:
  schedule:
    - cron: '0 9 * * 1'   # Weekly Monday 09:00
  workflow_dispatch:

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync

      - name: Generate SDR
        run: uv run aa_auto_sdr ${{ secrets.RSID }} --output-dir ./artifacts
        env:
          ORG_ID: ${{ secrets.ORG_ID }}
          CLIENT_ID: ${{ secrets.CLIENT_ID }}
          SECRET: ${{ secrets.SECRET }}
          SCOPES: ${{ secrets.SCOPES }}

      - uses: actions/upload-artifact@v4
        with:
          name: sdr-reports
          path: ./artifacts/
```

### Output organization

Keep runs navigable by organizing output by date and environment.

```bash
# By date
aa_auto_sdr demo.prod --output-dir ./reports/$(date +%Y%m%d)

# By environment then date
aa_auto_sdr demo.prod --output-dir ./reports/production/$(date +%Y%m%d)
```

```
reports/
├── production/
│   ├── 20260601/
│   └── 20260608/
├── staging/
└── quality/
    ├── week_22/
    └── week_23/
```

## Target audiences

| Audience | Key use case | Recommended workflow |
|----------|--------------|----------------------|
| Adobe Analytics implementers | Document report-suite state | Generate on demand; `--format reports` for sharing |
| Analytics teams | Change tracking over time | Weekly `--auto-snapshot`; `--compare-with-prev` |
| Data Governance | Audit trails and inventory | `--auto-snapshot --git-commit`; periodic `--inventory-summary` |
| DevOps engineers | Drift gates in pipelines | `--diff … --warn-threshold` (exit 3) and `--fail-on-quality` (exit 17) |
| Consultants | Multi-client delivery | One profile per org; `--template` for customer-facing SDRs |
| Enterprise | Compliance documentation | `--format all` with timestamped, git-versioned snapshots |

## See also

- [Quick Reference](QUICK_REFERENCE.md) — single-page command cheat sheet
- [CLI Reference](CLI_REFERENCE.md) — every flag with examples
- [Configuration](CONFIGURATION.md) — credentials, scopes, profiles, multi-org setup
- [Snapshot & Diff](SNAPSHOT_DIFF.md) — snapshot format, resolver tokens, diff semantics, trending, watch
- [Output Formats](OUTPUT_FORMATS.md) — formats, aliases, file layouts
- [Template-Fill Workflow](TEMPLATE_WORKFLOW.md) — fill Adobe's BRD/SDR template
- [Notion Setup](NOTION_SETUP.md) — Notion publishing and the SDR Registry
- [`AGENTS.md`](../AGENTS.md) — agent-mode contract for unattended and CI runs
