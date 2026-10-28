# Output Formats

`aa_auto_sdr` supports five core generation formats (excel, csv, json, html, markdown) plus the specialized `excel-template` and `notion` outputs, four aliases, and four diff-output formats. [`sample_outputs/`](../sample_outputs/) contains representative examples of the core generation formats and the console, JSON, and Markdown diff renderers; it does not include a template-filled workbook, Notion output, or the `pr-comment` diff renderer.

## Base formats (generation)

| Format | Extension | File layout | Use case |
|--------|-----------|-------------|----------|
| `excel` | `.xlsx` | Single workbook: `Summary`, `Coverage`, and `Quality` sheets, one sheet per component type, then a `References` sheet | Human review; default format |
| `excel-template` | `.xlsx` | Auto-selected when `--template PATH` is passed. Opens an existing Adobe BRD/SDR `.xlsx`, fills component data into anchored sheets, preserves styles and formulas. | Customer-facing SDRs that must match the official template's look. |
| `csv` | `.csv` | Multi-file: one CSV per tabular component type plus `summary`, `coverage`, and `references` (9 files: dimensions, metrics, segments, calculated_metrics, virtual_report_suites, classifications, summary, coverage, references), plus `quality_issues` when a quality audit ran, and a `<stem>._manifest.json` completion manifest written last ([CSV bundle publication](#csv-bundle-publication-and-manifest)). Report-suite metadata and the quality verdict are rolled into `summary.csv`. | Spreadsheet integration; tabular tooling |
| `json` | `.json` | Single self-contained JSON file with the full SdrDocument, including `fetch_status`, `quality`, `collected_components` (the families this capture requested), a derived `coverage` object ([below](#sdr-json-coverage-object)), and the derived `references` block ([below](#references-appendix)) | Automation; jq pipelines; downstream tooling |
| `html` | `.html` | Single self-contained HTML file with inline CSS, no JavaScript. Coverage and Quality sections follow the header. | Sharing as a static report; PR/email attachments |
| `markdown` | `.md` | Single GFM-flavored Markdown file: Coverage and Quality sections, the summary, one H2 per component type, then a References section | PR comments; wiki-friendly; readable in GitHub |
| `notion` | `.notion` (nominal) | Publishes a Notion page; tracks RSID → page-id in `.notion_pages.json`. Requires `[notion]` extra plus `NOTION_TOKEN` / `NOTION_PARENT_PAGE_ID`. | Notion-based wikis; collaborative docs |

## Coverage and quality in reports

Every local report format (Excel, CSV, Markdown, HTML) states, for each of the
six component families, what the capture actually holds. A reader can tell an
empty family apart from one that was never fetched without opening the logs.

| State | CSV `state` value | Meaning |
|-------|-------------------|---------|
| Collected | `collected` | Requested, fetched without problems, has rows. |
| Collected — no components | `collected_empty` | Requested and fetched without problems; the report suite has none. |
| Not collected in this capture | `excluded` | Left out of the capture scope (for example by a component filter). Zero rows here say nothing about the report suite. |
| Fetch degraded — no data | `degraded` | Requested, but the fetch failed and was degraded to an empty section. |
| Partial fetch (expansion level: …) | `partial` | Requested, but only part of the data came back. The expansion level is shown in its own column. |
| Scope unknown — may not have been collected | `unknown_scope` | The input does not record its capture scope (only legacy inputs). The family may or may not have been requested, so zero rows are never shown as "Collected — no components". |

The quality status is reported the same way: either "No quality audit ran." or
the audit's verdict, policy threshold, issue total, and counts by severity.
A `fail` verdict can be traced to the findings that caused it.

Where each format puts this:

- **Excel**: a `Coverage` sheet directly after `Summary` (columns `Family`,
  `State`, `Count`, `Expansion Level`), then a `Quality` sheet. When an audit
  ran, the `Quality` sheet starts with a summary block (`Verdict`,
  `Policy threshold`, `Total issues`, one row per severity), then
  a blank row, then one row per issue (`severity`, `category`, `type`,
  `item_id`, `item_name`, `issue`, `details`, `rule_id`, `component_ids`,
  `occurrences`, `exception`). `component_ids` is joined with `, ` and shows
  at most 50 IDs, then `… (+N more)`.
  `exception` reads `excepted (<reason>)` for a finding covered by a policy
  exception and is empty otherwise. `Total issues` and the severity rows count
  non-excepted findings only. An `Excepted` row follows the severity rows only
  when some finding is excepted. When no audit ran, it holds a single row saying
  so.
- **CSV**: `<stem>.coverage.csv` is always written (columns `family`, `state`,
  `count`, `expansion_level`). `<stem>.quality_issues.csv` is written only
  when an audit ran, with the same issue columns as the Excel sheet.
  `<stem>.summary.csv` gains `Quality verdict` (`not run`, `pass`, `fail`, or
  `n/a` when the audit ran without `--fail-on-quality`),
  `Quality policy threshold`, and `Quality issues` rows.
- **Markdown and HTML**: a Coverage table and a one-line Quality status right
  after the report-suite header. When the audit found anything, a findings
  table follows the status line (`Severity`, `Rule ID`, `Item`, `Issue`,
  `Component IDs`, `Occurrences`, `Exception`), and the status line adds
  "plus N excepted" when policy exceptions apply. An empty component section prints its
  family's state (for example "Not collected in this capture") instead of a
  bare "none". A section that has rows but is partial, degraded, or of
  unknown scope shows the state above its table.
- **JSON**: carries `fetch_status`, `quality`, and `collected_components`,
  plus the derived top-level `coverage` object described below.
  Each `quality.issues` entry keeps `component_ids` as a list and carries
  `rule_id`, `occurrences`, `excepted`, and `exception_reason`;
  `quality.summary.excepted` counts excepted findings. See
  [CLI_REFERENCE.md](CLI_REFERENCE.md#rule-ids) for the rule IDs.

### SDR JSON `coverage` object

SDR JSON (file output, `--output -`, and `--render-from` JSON) has a
top-level `coverage` object with the same per-family states and quality
status the other formats show. Its shape matches the SDR JSON `coverage`
block in `cja_auto_sdr`; the state values are aa's.

```json
"coverage": {
  "families": [
    {"family": "dimensions", "state": "collected", "count": 4, "detail": "Collected"},
    {"family": "classifications", "state": "partial", "count": 1,
     "detail": "Partial fetch (expansion level: rsid_only)"}
  ],
  "quality": {
    "state": "ran",
    "detail": "Quality gate FAIL at threshold HIGH: 2 issues (CRITICAL 0, HIGH 1, MEDIUM 0, LOW 1, INFO 0).",
    "issue_count": 2,
    "severity_counts": {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 0, "LOW": 1, "INFO": 0},
    "gate": {"threshold": "HIGH", "verdict": "fail"}
  }
}
```

- `families` lists all six families in report order (dimensions, metrics,
  segments, calculated_metrics, virtual_report_suites, classifications).
  `state` is one of the values in the table above. `detail` is the
  human-readable state, including the expansion level for `partial`.
- `quality.state` is `ran` or `not_run`. `failed` is reserved for parity with
  `cja_auto_sdr` and is never written today, because an audit that raises
  fails the whole run instead of producing a document. When no audit ran,
  `issue_count` and `gate` are `null` and `severity_counts` is `{}`.
- `quality.gate` is `null` unless a `--fail-on-quality` threshold applied, as
  in `cja_auto_sdr`. With a threshold it is `{threshold, verdict}`, and
  `verdict` is `pass` or `fail`. These lowercase values are aa's existing
  `quality.summary.verdict` values; `cja_auto_sdr` uses `PASS`, `FAIL`, and
  `NOT_EVALUATED` instead.
- `coverage` is derived output. Snapshot envelopes never carry it, and
  `--render-from` ignores it in its input and derives it again.

### CSV bundle publication and manifest

The CSV writer renders every file of a run into a dot-prefixed staging
directory (`.<stem>.csv-*`) next to the target. It then moves the files into place
together and writes `<stem>._manifest.json` last. File names and locations
do not change: the files stay flat in the output directory as
`<stem>.<section>.csv`.

```json
{
  "complete": true,
  "files": [
    {"bytes": 334, "name": "demo_prod.summary.csv", "rows": 16,
     "sha256": "ca1508ae…", "sheet": "Summary"}
  ],
  "generated_at": "2026-04-26T12:00:00+00:00",
  "manifest_version": "1.0"
}
```

- `files` lists every CSV file the run wrote, in write order: summary,
  coverage, the six component files, references, then quality_issues when an
  audit ran.
  `sha256` and `bytes` describe the file as written (UTF-8 with BOM). `rows`
  counts data rows, not the header row. `sheet` is the section title.
- If any section fails to render, nothing is published. The files from the
  previous run, including its manifest, are left untouched.
- The old manifest is removed before the files are replaced, and the new one
  is written last, so a manifest always describes a complete set from one
  run. Replacing several files is not atomic as a set: a failure while moving
  files leaves no manifest, which tells a consumer the set is incomplete.
- Files that are not part of the new run are never deleted. A
  `<stem>.quality_issues.csv` from an earlier audited run stays on disk but is
  not listed in the new manifest.
- The manifest is named after the stem (the RSID for normal runs). A batch
  that writes several report suites into one `--output-dir` gets one manifest
  per report suite, and parallel workers never write the same file. The
  shape matches the `_manifest.json` in `cja_auto_sdr`. The stem prefix is
  aa's own, because aa writes CSV files flat instead of into a per-run
  directory.
- Use one writer per output stem. Two separate processes that write the same
  RSID into the same directory at the same time can interleave their files.
  A single batch run is safe, because each report suite has its own stem.
- The staging directory is removed when the write finishes or fails. If the
  process is killed (for example by SIGKILL or a power loss), a
  `.<stem>.csv-*` directory can be left behind. It is not cleaned up
  automatically and is safe to delete.

## Definition summaries and references

Segment and calculated-metric definitions are nested JSON trees. Every
report format adds a one-line readable summary of each definition and the
IDs it references. The full definition JSON stays in its `definition`
column or field; the summary is a reading aid, not a replacement.

### New columns and fields

| Family | Field | Contents |
|--------|-------|----------|
| Calculated metrics | `formula_summary` | The formula as arithmetic, for example `metrics/orders / metrics/visits[segment s_222]` |
| Segments | `definition_summary` | The rule as text, for example `Visit where variables/visitnumber > 1 AND metrics/pageviews exists` |
| Both | `metric_references` | Sorted metric and calculated-metric IDs the definition names |
| Both | `segment_references` | Sorted segment IDs the definition names |

In Excel, CSV, Markdown, and HTML the three columns come after the existing
columns, and the reference lists are joined with `, `. In JSON they are added
to each segment and calculated-metric object, and the reference fields are
lists. In Markdown, summary cells are inline code so characters such as
`*`, `_`, and `\` show as written. The field names match `cja_auto_sdr`,
but the values differ: `cja_auto_sdr` lists short names (for example
`revenue`), while `aa_auto_sdr` keeps full component IDs (for example
`metrics/revenue`).

Reference IDs are collected from the whole definition, including parts the
summarizer does not understand: `name` on `metric` and `event` nodes, and
`segment_id` on `segment` nodes.

### What the summary understands

The summary covers a conservative part of the Adobe Analytics 2.0
definition grammar. Anything else is shown raw as `[unparsed: <func>]`,
for example `[unparsed: col-sum]` or `[unparsed: sequence]`, so a summary never
describes more than it can read. A known node that is missing a required
key, or has a value of the wrong type, is shown the same way. A malformed
definition never stops a report.

Calculated metrics (`definition.formula`):

| Node (`func`) | Summary |
|---------------|---------|
| `metric` | The metric ID from `name` |
| `number` | The literal from `val`. A plain JSON number used as an operand shows the same way |
| `add`, `subtract`, `multiply`, `divide` | `a + b`, `a - b`, `a * b`, `a / b` from `col1` and `col2`, in that order |
| `negate` | `-a` from `col` |
| `abs`, `round`, `ceil`, `floor` | `ABS(a)`, `ROUND(a)`, `CEIL(a)`, `FLOOR(a)` from `col` |
| `segment` | `a[segment <segment_id>]`: the metric in `metric` filtered by a segment |
| `eq`, `ne`, `gt`, `lt`, `ge`, `le` | `a = b`, `a != b`, `a > b`, `a < b`, `a >= b`, `a <= b` from `col1` and `col2` |
| `if` | `IF(<cond>, <then>, <else>)`, for example `IF(metrics/occurrences <= 7, metrics/occurrences, 0)` |

`*` and `/` bind tighter than `+` and `-`, and comparisons bind looser than
both. Parentheses are added where
precedence needs them, and around a right operand of the same precedence
unless the chain is the same associative operator. So `a - (b - c)` and
`a / (b * c)` keep their meaning, while `a + b + c` stays flat.

Segments (`definition.container`):

| Node (`func`) | Summary |
|---------------|---------|
| `container` with `context` `hits`, `visits`, `visitors` | `Hit where …`, `Visit where …`, `Visitor where …`; a nested container is wrapped in parentheses |
| `and`, `or` (`preds`) | `a AND b`, `a OR b`, in order. A child of the other operator is wrapped in parentheses |
| `not` (`pred`) | `NOT (…)` |
| `without` (`pred`) | `EXCLUDE (…)` |
| `streq`, `not-streq` | `<subject> = 'x'`, `<subject> != 'x'` (string in `str`) |
| `contains`, `not-contains`, `starts-with`, `not-starts-with`, `ends-with`, `not-ends-with` | `contains 'x'`, `does not contain`, `starts with`, `does not start with`, `ends with`, `does not end with` |
| `eq`, `ne`, `gt`, `lt`, `ge`, `le` | `=`, `!=`, `>`, `<`, `>=`, `<=` (number in `num`) |
| `exists`, `not-exists` | `<subject> exists`, `<subject> does not exist` |
| `event-exists`, `not-event-exists` | `<metric> exists`, `<metric> does not exist` (from `evt`) |
| `streq-in`, `not-streq-in` | `<subject> in ('a', 'b')`, `<subject> not in ('a', 'b')` (strings in `list`). At most 20 values are shown, then `… +N more` |
| `segment` | `segment <segment_id>` |

The subject is the `name` of an `attr` or `event` node in `val`, or
`total(<metric>)` for a `total` node, which compares a metric's total
within the container (for example `Visit where total(metrics/pageviews) > 10`). Strings
are quoted with `'`. A `'` or `\` inside a string is escaped with `\`, and
line breaks, tabs, and other control characters are written as escapes
(`\n`, `\t`, `\x01`), so a summary is always one line. A quoted value
longer than 200 characters is cut there and ends with `…`. A number with no
fractional part is written without a decimal point (`3.0` shows as `3`).

One shape is inferred from Adobe's documentation and not yet checked
against a live capture: a `segment` node with `segment_id` used as a
predicate inside a segment. If real definitions use a different shape,
those nodes show as `[unparsed: …]` rather than a wrong summary.

### Limits

- Summaries stop descending after 64 levels; the deeper part shows
  `[unparsed: depth limit]`.
- A definition with more than 1,000 nodes is summarized as
  `[unparsed: definition exceeds 1000 nodes]`.
- Reference collection visits at most 50,000 nodes, 256 levels deep, and
  never visits the same object twice.

### References appendix

For each calculated metric, segment, and virtual report suite, the appendix
lists what it references and what references it. A virtual report suite
references the segments in its `segment_list`. References are resolved
against the capture: a metric ID resolves to a captured calculated metric or
metric, and a segment ID to a captured segment. If a metric ID has no exact
match, it is also tried against the calculated metrics with the `metrics/`
prefix removed or added, because a formula may name a nested calculated
metric either way. The output keeps the ID as the definition wrote it. An ID that is not in the
capture is labeled `unresolved`. This only means the target was not in this
capture. It may live outside the report suite, belong to a family that was
not collected, or be one the API did not return; the tool cannot tell which.

Only direct references are listed. A reference cycle (segment A uses B and B
uses A) shows up as two rows and is never followed.

| Format | Where | Shape |
|--------|-------|-------|
| Excel | `References` sheet after `Classifications` | One row per reference: `Family`, `ID`, `Name`, `Relation` (`references` or `referenced by`), `Kind` (`metric` or `segment`, on `references` rows), `Target Family`, `Target ID`, `Target Name`, `Status` (`resolved` or `unresolved`). An empty sheet keeps its header row. |
| CSV | `<stem>.references.csv`, always written | The same rows with raw keys: `family`, `id`, `name`, `relation` (`references` or `referenced_by`), `kind`, `target_family`, `target_id`, `target_name`, `status` |
| Markdown, HTML | `References` section after the component sections | The Excel table, or "No references found." |
| JSON | Top-level `references` object | `calculated_metrics`, `segments`, `virtual_report_suites`: one object per component with `id`, `name`, `references` (each `kind`, `id`, `family`, `name`, `status`; `family` and `name` are null when unresolved), and `referenced_by` (each `family`, `id`, `name`) |

The JSON written to a file and to stdout (`--output -`, `--agent-mode`)
carries the derived fields and the `references` block. Snapshots do not:
they hold only captured data, so these fields never show up in a diff.
`--render-from` accepts JSON that contains them and ignores them.

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

Each template sheet holds at most 50 rows past its last existing row. Rows past that soft cap are written to an `Overflow` sheet appended after the template's own sheets. Components meant for a template sheet that was skipped (missing, renamed, or unanchored) go there too. The sheet is created only when either happens. Each `Overflow` row keeps the template sheet it belongs in, the reason it is in `Overflow` (`clipped` or the skip reason), its component type and ID, and the values the template sheet would have received, so every row can be recovered from the template sheet plus `Overflow`.

Every filled workbook also gets a `Template Coverage` sheet, appended after the template's sheets. It reports rows matched, appended, and sent to overflow; template sheets skipped because they are missing or their anchors do not match; template columns the writer cannot fill; and each component family's coverage state (collected, excluded, degraded, partial, or unknown scope), using the same states as the other report formats. Overflow is reported in the workbook and in the logs (`template_sheet_clipped`, `template_overflow_sheet_written`); it does not change the exit code. See [`TEMPLATE_WORKFLOW.md`](TEMPLATE_WORKFLOW.md#overflow-and-template-coverage-sheets) for the sheet layouts.

Aliases (`all`, `reports`) keep producing `excel`; the `--template` swap rewrites the resolved format list after alias resolution, so `--format all --template foo.xlsx` produces all five generation formats including a template-filled `.xlsx` (CSV is a multi-file set, so the on-disk file count is higher than five). The bare format key `excel-template` is normally reached via `--template` rather than passed directly — there is no CLI guard against `--format excel-template` on its own, but the template-fill writer needs a template path and fails at write time without one, so always pass `--template`.

## Notion format

`--format notion` publishes the SDR directly to a Notion page. Requires `NOTION_TOKEN` and `NOTION_PARENT_PAGE_ID` environment variables and the `notion` optional extra (`uv pip install 'aa-auto-sdr[notion]'`).

Each run creates or updates a single page per RSID under the configured parent. Page IDs are tracked in `.notion_pages.json` in the output directory (or CWD) so re-runs update in place rather than accumulating duplicates. `--notion-force-new` skips the registry and always creates a fresh page; the new ID replaces the old entry.

The `notion` format is opt-in only — it is **not** included in the `all`, `reports`, `data`, or `ci` aliases. The companion mode `--push-to-notion FILE` publishes an existing SDR JSON or snapshot envelope to Notion without re-calling the Adobe Analytics API; see [`CLI_REFERENCE.md`](CLI_REFERENCE.md#notion-integration).

**Dry-run note:** `--dry-run --format notion` prints the `.notion_pages.json` path as the "would-write" artifact (instead of a phantom `<rsid>.notion` file). The actual side effect is a create-or-update against the Notion API plus an atomic write to `.notion_pages.json`.

**Parallel batch:** `--batch --format notion --workers N>1` is supported. A process-level lock serializes all `.notion_pages.json` writes so concurrent workers do not race. Note Notion's ~3 req/s API rate limit; the client retries HTTP 429 responses automatically.

**Watch:** `--watch --format notion` is supported. Notion publishes on the baseline cycle, on cycles where `total_changes >= --watch-threshold`, and on any cycle with a report-suite setting change. Zero-change cycles and fetch-error cycles never publish. If Notion raises during a cycle, a `notion_watch_publish_failed` WARNING fires and the loop continues.

### Registry database (opt-in)

Setting `NOTION_REGISTRY_DATABASE_ID` (or `--notion-registry-database`) enables a queryable database index alongside the detail pages: one row per RSID, with a `Page` url linking to the detail page. Leaving the variable unset keeps behavior identical to the page-only flow.

To stand up the registry database, run `aa_auto_sdr --notion-create-database --yes`
(see `docs/NOTION_SETUP.md`). It creates the database with the full schema in one
command.

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
- `--quality-report` cannot be combined with `--output -` (exit 15). The quality report is a file artifact, so use normal file-output mode and `--output-dir` instead.

## Rendering a saved capture (`--render-from`)

`--render-from TOKEN` rebuilds the document from saved SDR JSON (the `--format json` output) or a snapshot (path, `<RSID>@<ts>`, `<RSID>@latest`, `<RSID>@previous`, or `git:<ref>:<path>`) and runs the same writers, with no API calls. Every rule on this page applies: `--format` and its aliases, `--output-dir`, `--output -` for JSON only, and `--template` for template fill. `--format notion` is rejected; use `--push-to-notion` to publish a saved capture.

Component content is identical to what generation wrote for the same capture. The capture's `captured_at`, `tool_version`, coverage states, and quality status are kept. An input that does not record its scope keeps `unknown_scope` coverage. The render step is added on top:

- **JSON**: two extra top-level keys, `rendered_at` (ISO-8601 with offset) and `rendered_by_tool_version`. A live capture's JSON never has them.
- **Excel, CSV, Markdown, HTML**: the summary gains `Rendered at` and `Rendered by tool version` rows, and the Markdown and HTML headers add one line, "Rendered at … by tool version … from a capture taken at … by tool version …".

```bash
uv run aa_auto_sdr --render-from ./reports/<RSID>.json --format all --output-dir /tmp/sdr
uv run aa_auto_sdr --render-from <RSID>@latest --profile prod --format json --output -
```

See [`CLI_REFERENCE.md`](CLI_REFERENCE.md#offline-render) for accepted flags and exit codes.

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

User-requested local file outputs are staged beside their destination and
published with `os.replace` only after serialization succeeds. A handled write
or replacement failure therefore preserves an existing destination and removes
the incomplete staging file.

Atomicity applies per destination file, not to the command as a whole. If a
multi-format run publishes JSON and then fails while writing Markdown, the JSON
update remains in place while the prior Markdown file is preserved. Standard
output remains a direct stream, and the append-only `$GITHUB_STEP_SUMMARY` sink
keeps its append semantics.

## Machine-readable error envelope

When an error occurs on a pipe-path invocation (`--output -` for generation, `--format json|markdown --output -` for diff), the tool writes a one-line JSON error envelope to **stderr** while keeping stdout silent:

```json
{"error":{"code":11,"type":"AuthError","message":"...","hint":"Verify credentials in Adobe Developer Console."}}
```

This means downstream `jq` / scripts see empty input on stdout (rather than corrupted JSON or human-readable error text), and stderr carries machine-parseable failure context.

## Sample outputs

[`sample_outputs/`](../sample_outputs/) in this repo contains a representative set:

- `demo_prod.xlsx` / `.json` / `.html` / `.md` — one file per generation format
- `demo_prod.<component>.csv` — nine CSV files (six component files plus `summary`, `coverage`, and `references`), and `demo_prod._manifest.json`, which lists them
- `synthetic_snapshot_a.json` / `synthetic_snapshot_b.json` — two snapshots that differ by one renamed dimension and one removed metric
- `diff_console.txt` / `diff_report.json` / `diff_report.md` — three of the four diff renderer outputs from those snapshots (the `pr-comment` renderer is not sampled)

The samples are generated by `scripts/build_sample_outputs.py` from `tests/fixtures/sample_rs.json`. CI asserts the committed tree matches the script's current output (so any drift is caught).

## See also

- [`CLI_REFERENCE.md`](CLI_REFERENCE.md) — full flag reference including `--format`, `--output`, `--output-dir`
- [`SNAPSHOT_DIFF.md`](SNAPSHOT_DIFF.md) — diff semantics and snapshot file format
- [`sample_outputs/`](../sample_outputs/) — browse representative outputs
