# Output Formats

`aa_auto_sdr` supports five base formats and four aliases for SDR generation, plus four formats for diff output. Browse [`sample_outputs/`](../sample_outputs/) for committed examples of each.

## Base formats (generation)

| Format | Extension | File layout | Use case |
|--------|-----------|-------------|----------|
| `excel` | `.xlsx` | Single workbook with one sheet per component type | Human review; default format |
| `excel-template` | `.xlsx` | Auto-selected when `--template PATH` is passed. Opens an existing Adobe BRD/SDR `.xlsx`, fills component data into anchored sheets, preserves styles and formulas. | Customer-facing SDRs that must match the official template's look. |
| `csv` | `.csv` | Multi-file: one CSV per tabular component type plus a summary (7 files: dimensions, metrics, segments, calculated_metrics, virtual_report_suites, classifications, summary). Report-suite metadata is rolled into `summary.csv`. | Spreadsheet integration; tabular tooling |
| `json` | `.json` | Single self-contained JSON file with the full SdrDocument | Automation; jq pipelines; downstream tooling |
| `html` | `.html` | Single self-contained HTML file with inline CSS, no JavaScript | Sharing as a static report; PR/email attachments |
| `markdown` | `.md` | Single GFM-flavored Markdown file with one H2 per component type | PR comments; wiki-friendly; readable in GitHub |
| `notion` | `.notion` (nominal) | Publishes a Notion page; tracks RSID → page-id in `.notion_pages.json`. Requires `[notion]` extra plus `NOTION_TOKEN` / `NOTION_PARENT_PAGE_ID`. | Notion-based wikis; collaborative docs |

### Default

`excel` is the default if `--format` is omitted:

```bash
uv run aa_auto_sdr <RSID>                    # produces <RSID>.xlsx
uv run aa_auto_sdr <RSID> --format json      # produces <RSID>.json
```

## Template-fill mode (`excel-template`)

> **Hands-on guide:** [`docs/TEMPLATE_WORKFLOW.md`](TEMPLATE_WORKFLOW.md) — first run, batch, organization override, snapshot/git composition, coverage map, troubleshooting. This section is the reference summary; the guide is the cookbook.

`aa_auto_sdr <RSID> --template aa_en_BRD_SDR_template.xlsx` swaps the Excel writer from "from scratch" to "fill an existing workbook":

```bash
uv run aa_auto_sdr <RSID> --template ~/templates/aa_en_BRD_SDR_template.xlsx
uv run aa_auto_sdr <RSID> --template ~/templates/aa_en_BRD_SDR_template.xlsx --template-organization "Acme Corp"
```

The fill writer preserves every cell, style, formula, and defined name not explicitly written. Coverage is API-bounded (~50–70% of template columns); admin-only fields the AA 2.0 API doesn't expose (eVar Allocation, Expiration, Merchandising; List Prop Delimiter; Event Type; etc.) are left blank.

Aliases (`all`, `reports`) keep producing `excel`; the `--template` swap rewrites the resolved format list after alias resolution, so `--format all --template foo.xlsx` produces 5 files including a template-filled `.xlsx`. The bare format key `excel-template` is not user-invokable directly (it would error with USAGE because no `--template` path is set).

## Notion format

`--format notion` publishes the SDR directly to a Notion page. Requires `NOTION_TOKEN` and `NOTION_PARENT_PAGE_ID` environment variables and the `notion` optional extra (`uv pip install 'aa-auto-sdr[notion]'`).

Each run creates or updates a single page per RSID under the configured parent. Page IDs are tracked in `.notion_pages.json` in the output directory (or CWD) so re-runs update in place rather than accumulating duplicates. `--notion-force-new` skips the registry and always creates a fresh page; the new ID replaces the old entry.

The `notion` format is opt-in only — it is **not** included in the `all`, `reports`, `data`, or `ci` aliases. The companion mode `--push-to-notion FILE` publishes an existing SDR JSON or snapshot envelope to Notion without re-calling the Adobe Analytics API; see [`CLI_REFERENCE.md`](CLI_REFERENCE.md#notion-integration).

**Dry-run note:** `--dry-run --format notion` prints the `.notion_pages.json` path as the "would-write" artifact (instead of a phantom `<rsid>.notion` file). The actual side effect is a create-or-update against the Notion API plus an atomic write to `.notion_pages.json`.

**Parallel batch:** `--batch --format notion --workers N>1` is supported. A process-level lock serializes all `.notion_pages.json` writes so concurrent workers do not race. Note Notion's ~3 req/s API rate limit; the client retries HTTP 429 responses automatically.

**Watch:** `--watch --format notion` is supported. Notion publishes on the baseline cycle and on cycles where `total_changes >= --watch-threshold`. Zero-change cycles and fetch-error cycles never publish. If Notion raises during a cycle, a `notion_watch_publish_failed` WARNING fires and the loop continues.

### Registry database (opt-in)

Setting `NOTION_REGISTRY_DATABASE_ID` (or `--notion-registry-database`) enables a queryable database index alongside the detail pages: one row per RSID, with a `Page` url linking to the detail page. Leaving the variable unset keeps behavior identical to the page-only flow.

Run `aa_auto_sdr --notion-print-database-schema` for the canonical property list to create in Notion. Required properties: `Name` (title), `RSID` (rich_text, the idempotency key), `Last Updated` (date), `Tool Version` (rich_text), and one `number` each for `Dimensions`, `Metrics`, `Segments`, `Calculated Metrics`, `Virtual Report Suites`, `Classifications`. Optional properties are created when present: `Page` (url), `Currency`, `Timezone`, `Parent RSID`, `Quality Verdict` (select), `Degraded Components` (multi_select). There is also an optional `Company` (rich_text) property; when the database has a `Company` column and `--notion-company` (or `NOTION_REGISTRY_COMPANY`) is set, the row key becomes `(Company, RSID)` instead of RSID alone — allowing one database to hold multiple Adobe Analytics organizations.

The registry database should be a standard single-data-source database. If the database has more than one data source, the tool uses the first one and logs a `notion_registry_multi_source` warning.

The detail page remains the primary artifact: if the database upsert fails (integration not invited, missing required property, 5xx), a `notion_registry_unavailable` WARN fires and the run continues.

### Registry file shape

`.notion_pages.json` stores a per-RSID object: `{"current": "<page_id>", "superseded": ["<old_id>", ...]}`. The `superseded` list grows each time `--notion-force-new` repoints an RSID to a new page. The previous flat shape (`{rsid: page_id}`) still loads without migration.

### Orphan pruning

`--notion-prune-orphans` reads `.notion_pages.json` and archives (Notion trash, recoverable) every page in the `superseded` list, then removes the tombstones. Preview by default; `--yes` applies. A failed archive attempt leaves the tombstone in place and logs a `notion_page_archive_failed` WARNING — the remaining orphans can be retried on the next run.

Note a narrow gap: if a `--notion-force-new` create call fails after Notion creates the page but before the id is recorded locally, no tombstone is written and the unreferenced page is invisible to `--notion-prune-orphans`. Such pages can be found and deleted manually in Notion.

### Database schema repair

`--notion-repair-database` compares the live registry database against the canonical schema and additively creates any missing properties. It never changes existing property types (type conflicts are printed and left untouched) and never deletes existing properties. Preview by default; `--yes` applies. Use this after adding `Company` support to an existing database: run `--notion-repair-database --yes` to add the `Company` column without touching the rest of the schema.

## Format aliases

Generate multiple formats at once:

| Alias | Resolves to | When to use |
|-------|-------------|-------------|
| `all` | excel + csv + json + html + markdown | Generate everything (e.g. for archival) |
| `reports` | excel + markdown | Human-facing artifacts (Excel for analysts, Markdown for review) |
| `data` | csv + json | Machine-readable artifacts (CSV for spreadsheets, JSON for code) |
| `ci` | json + markdown | CI-friendly outputs (JSON for assertions, Markdown for PR comments) |

```bash
uv run aa_auto_sdr <RSID> --format all       # all five
uv run aa_auto_sdr <RSID> --format reports   # excel + markdown
uv run aa_auto_sdr <RSID> --format ci        # json + markdown
```

## Output destinations

### `--output-dir` (file output, default)

Write all generated files into a directory:

```bash
uv run aa_auto_sdr <RSID> --output-dir /tmp/sdr
# /tmp/sdr/<RSID>.xlsx
```

Default: current working directory.

### `--output -` (stdout pipe, JSON only)

Pipe the generated SDR JSON to stdout for downstream consumers:

```bash
uv run aa_auto_sdr <RSID> --format json --output - | jq '.report_suite'
uv run aa_auto_sdr <RSID> --format json --output - | python -c "..."
```

**Restrictions:**
- Only `--format json` is accepted with `--output -`. Other formats (csv, excel, html, markdown, aliases) are rejected with exit 15 (`format 'X' cannot be piped to stdout; use --output-dir <DIR> instead`).
- `--output -` combined with `--batch` is rejected with exit 15 (multiple SDRs cannot share a single stream — use `--output-dir`).

## Batch generation file layout

`--batch` produces N output files per format, all in the same `--output-dir`:

```bash
uv run aa_auto_sdr --batch RS1 RS2 RS3 --format all --output-dir /tmp/sdr
# /tmp/sdr/RS1.xlsx, /tmp/sdr/RS1.json, /tmp/sdr/RS1.html, ...
# /tmp/sdr/RS2.xlsx, ...
# /tmp/sdr/RS3.xlsx, ...
```

CSV multi-file layout per RS keys off canonical RSID (e.g. `RS1.dimensions.csv`, `RS1.metrics.csv`).

## Diff output formats

The `--diff` action has its own format set:

| Format | Suitable for | Notes |
|--------|--------------|-------|
| `console` (default) | Human review in terminal | ANSI-colored; auto-disabled for non-TTY / `NO_COLOR=1` |
| `json` | Automation; jq pipelines | Sorted keys, stable shape |
| `markdown` | PR comments; review artifacts | GFM tables; pipe characters escaped |
| `pr-comment` | GitHub PR comments | Compact GFM with collapsible `<details>`; 60K-char cap |

```bash
uv run aa_auto_sdr --diff a.json b.json                              # console
uv run aa_auto_sdr --diff a.json b.json --format json --output -     # JSON to stdout
uv run aa_auto_sdr --diff a.json b.json --format markdown -o diff.md # Markdown to file
```

`--format console --output -` is rejected (exit 15) — use `json` or `markdown` for pipes.

See [`SNAPSHOT_DIFF.md`](SNAPSHOT_DIFF.md) for full diff semantics.

## Atomic writes

All file outputs use atomic writes (temp file + `os.replace`). An interrupted run never leaves a half-written file.

## Machine-readable error envelope

When an error occurs on a pipe-path invocation (`--output -` for generation, `--format json|markdown --output -` for diff), the tool writes a one-line JSON error envelope to **stderr** while keeping stdout silent:

```json
{"error":{"code":11,"type":"AuthError","message":"...","hint":"Verify credentials in Adobe Developer Console."}}
```

This means downstream `jq` / scripts see empty input on stdout (rather than corrupted JSON or human-readable error text), and stderr carries machine-parseable failure context.

## Sample outputs

[`sample_outputs/`](../sample_outputs/) in this repo contains a representative set:

- `demo_prod.xlsx` / `.json` / `.html` / `.md` — one file per generation format
- `demo_prod.<component>.csv` — seven CSV files
- `synthetic_snapshot_a.json` / `synthetic_snapshot_b.json` — two snapshots that differ by one renamed dimension and one removed metric
- `diff_console.txt` / `diff_report.json` / `diff_report.md` — the three diff renderer outputs from those snapshots

The samples are generated by `scripts/build_sample_outputs.py` from `tests/fixtures/sample_rs.json`. CI asserts the committed tree matches the script's current output (so any drift is caught).

## See also

- [`CLI_REFERENCE.md`](CLI_REFERENCE.md) — full flag reference including `--format`, `--output`, `--output-dir`
- [`SNAPSHOT_DIFF.md`](SNAPSHOT_DIFF.md) — diff semantics and snapshot file format
- [`sample_outputs/`](../sample_outputs/) — browse representative outputs
