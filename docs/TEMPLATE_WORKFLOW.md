# Template-Fill Workflow

`aa_auto_sdr` can write your Adobe Analytics SDR straight into Adobe's official BRD/SDR `.xlsx` template — styles, banners, cross-sheet formulas, and dropdowns preserved. This guide is the cookbook. For the formal contract, see [`docs/CLI_REFERENCE.md`](CLI_REFERENCE.md) (`--template`, `--template-organization`) and [`docs/OUTPUT_FORMATS.md`](OUTPUT_FORMATS.md) (`excel-template` format key).

## TL;DR

```bash
# 1. Download Adobe's template once
curl -fsSL -o ~/aa_en_BRD_SDR_template.xlsx \
  https://cdn.experienceleague.adobe.com/assets/Adobe-Enterprise-Docs/analytics-learn.en/main/help/implementation/implementation-basics/assets/aa_en_BRD_SDR_template.xlsx

# 2. Fill it for an RSID
uv run aa_auto_sdr <RSID> --template ~/aa_en_BRD_SDR_template.xlsx --output-dir /tmp/sdr/
```

Output: `/tmp/sdr/<RSID>.xlsx` — a filled copy of Adobe's template, ready to share with stakeholders.

## When to use this vs. plain `--format excel`

| | `--format excel` (default) | `--template <path>` |
|---|---|---|
| Output style | Plain workbook, one sheet per component type | Adobe's styled BRD/SDR template, filled |
| Formulas | None | `=Glossary!C2` cross-sheet refs preserved |
| Customer-shareable | Functional, not branded | Branded — matches what stakeholders expect |
| Setup | None | One-time template download |
| Coverage | 100% of API fields | ~50–70% (admin-only columns left blank — see [§coverage](#what-fills-vs-what-stays-blank)) |

Use `--template` when you need to hand the result to someone who'll review it in Excel. Use `--format excel` when you need the data flat for analysis.

## Get the template

Adobe maintains the canonical template on Experience League. The repo does **not** bundle it.

- **Direct download:** [`aa_en_BRD_SDR_template.xlsx`](https://cdn.experienceleague.adobe.com/assets/Adobe-Enterprise-Docs/analytics-learn.en/main/help/implementation/implementation-basics/assets/aa_en_BRD_SDR_template.xlsx)
- **Background reading:** [Experience League — Creating and maintaining an SDR](https://experienceleague.adobe.com/en/docs/analytics-learn/tutorials/implementation/implementation-basics/creating-and-maintaining-an-sdr)

Customizations are fine — if you've added rows, renamed sheets, or extended columns, point `--template` at your modified copy. The writer anchors by sheet name (`eVars`, `props`, `custom events (metrics)`, `metrics-segments`, `Glossary`) and by section title at cell `B4`. Additive column changes are safe; sheet renames break anchor resolution and surface as `template_sheet_skipped` warnings.

## Your first run

```bash
uv run aa_auto_sdr dgeo1xxpnwcidluma \
  --template ~/aa_en_BRD_SDR_template.xlsx \
  --output-dir /tmp/sdr/
```

What happens:
1. The CLI validates `--template` (must exist, be a file, end in `.xlsx`).
2. The Excel writer is auto-switched from "from scratch" mode to template-fill mode. Format aliases like `--format all` still resolve normally — any `excel` slot in the resolved set becomes `excel-template`.
3. The writer loads your template, walks each data sheet, matches API components by ID against the template's pre-seeded rows, fills in place, and appends any API-only IDs past the last pre-styled row.
4. `Glossary!C2` is written with the report-suite name; every other sheet's `=Glossary!C2` formula recalculates to that value when you open the file in Excel.
5. Output lands at `<output-dir>/<RSID>.xlsx`.

Open the result in Excel (not openpyxl, not a web viewer) to confirm styles render — only Excel itself resolves cross-sheet formulas and renders conditional formatting.

## Customize the organization banner

Default: `Glossary!C2` = the report-suite's name. Override with `--template-organization`:

```bash
uv run aa_auto_sdr <RSID> \
  --template ~/aa_en_BRD_SDR_template.xlsx \
  --template-organization "Acme Corp" \
  --output-dir /tmp/sdr/
```

Now `Glossary!C2` reads `Acme Corp`, and every other sheet's banner formula picks that up on next open. Useful when the RSID name is internal-only (`dgeo1xxpnwcid…`) but the recipient should see the customer's marketing name.

`--template-organization` requires `--template` (USAGE 2 otherwise).

## Batch across multiple RSIDs

```bash
uv run aa_auto_sdr --batch RS1 RS2 RS3 \
  --template ~/aa_en_BRD_SDR_template.xlsx \
  --workers 3 \
  --output-dir /tmp/sdr-batch/
```

Each RSID gets a freshly-loaded copy of the template (no shared state across workers — verified live, see PR #45). Output: `RS1.xlsx`, `RS2.xlsx`, `RS3.xlsx`, each with the per-RSID name written to `Glossary!C2`.

Parallel `--workers N` is safe — the writer loads + saves per-call, so workers don't cross-contaminate.

## Compose with snapshots and git

`--template` is purely an output-layer concern, so it composes cleanly with the snapshot / git-integration layer:

```bash
# Generate filled .xlsx + persist the SDR snapshot + commit it
uv run aa_auto_sdr <RSID> \
  --template ~/aa_en_BRD_SDR_template.xlsx \
  --snapshot \
  --git-commit \
  --output-dir /tmp/sdr/
```

Only the snapshot JSON gets committed — the filled `.xlsx` lands at `--output-dir` and stays out of the snapshot dir. If you want the `.xlsx` itself version-controlled, invoke `git` separately on `--output-dir`.

Diff between two snapshots after a fill run is still meaningful: snapshots are computed off the normalized SDR document, not off rendered output. The `.xlsx` is downstream of the diff.

## What fills vs. what stays blank

The writer fills the columns the AA 2.0 API can answer:

| Sheet | Filled by writer | Left blank (API gap) |
|---|---|---|
| `Glossary` | `C2` (org / report-suite name) | — |
| `eVars` | Analytics Variable, Variable Name, Variable Description | Value Format, Example Value, eVar Allocation, eVar Expiration, eVar Merchandising, Data Element/Source, XDM Field/Context Data, Implementation Scope, Implementation Status |
| `props` | Analytics Variable, Variable Name, Variable Description | Value Format, Example Value, List Prop Delimiter, Data Element/Source, XDM Field/Context Data, Implementation Scope, Implementation Status |
| `custom events (metrics)` | Event, Event Name, Event Description | Event Type, Unique Event Recording, Data Element/Source, XDM Field/Context Data, Implementation Scope, Implementation Status |
| `metrics-segments` | Type (Calculated Metric / Segment), Name, Description, Format (calc metrics only) | — |

The blanks are columns the AA 2.0 API doesn't expose — implementation/admin metadata that lives in the Admin Console UI but has no read endpoint. This is the same coverage gap the competitor `paolobietolini/aa-sdr-generator` documents.

The `B` column ("ID") on every data sheet is **never written** — that's customer numbering for cross-reference to the BRD half, not API data.

## What rows fill, what rows stay

Per-sheet fill strategy (see [v1.16.0 design spec §3.6](../docs/superpowers/specs/2026-05-11-aa-auto-sdr-v1.16.0-design.md) for the formal contract):

- **`eVars`, `props`, `custom events (metrics)`:** match-by-id with always-overwrite. The writer normalizes `variables/evar1` → `evar1` and `metrics/event1` → `event1` before matching, then case-insensitively matches against the template's existing rows. Matched rows are filled in place. Unmatched template-skeleton rows (e.g. `eVar37` when the RSID has only 12 eVars) are **untouched** — their pre-seeded Adobe example content survives. API IDs that don't appear in the template at all are **appended past `max_row`** (default styling, see "Style notes" below).

- **`metrics-segments`:** always-append. Calc-metric and segment IDs are opaque GUIDs the template doesn't pre-seed, so there's nothing to match against. Each calc metric and segment becomes a new row past the last pre-styled entry.

Adobe's template ships with example calc metrics and segments (Average Time Spent, Conversion Rate, Customer / New Visitors / Repeat Visitors, etc.). These **survive untouched** — the writer's non-empty rule never blank-overwrites a styled cell.

### Style notes

- **Matched-row fills:** keep the template's existing cell style (openpyxl preserves style on `cell.value = …` to an already-styled cell). Borders, fonts, alignment, conditional formatting — all untouched.
- **Appended rows:** use openpyxl's default style (no border, no font customization). Acceptable for v1; a future release may copy the style of the last pre-styled row downward.
- **Soft cap:** the writer appends up to 50 rows past `max_row`. Beyond that, additional API entries are dropped with a `template_sheet_clipped` WARNING. In practice this only trips for tenants with hundreds of segments — very rare.

## Troubleshooting

**Symptom: `eVars`, `props`, `custom events (metrics)` sheets are entirely unchanged.**

Most likely cause: your RSID has no user-configured eVars/props/events enabled. The AA 2.0 `/dimensions` endpoint returns enabled dimensions only — if your tenant's `standardComponent: true` is the only flavor returned, the writer has nothing to match. Verify with:

```bash
uv run aa_auto_sdr --list-dimensions <RSID> --format json --output - | \
  jq '[.[] | .id | split("/")[-1] | select(startswith("evar") or startswith("prop"))] | length'
```

If the count is `0`, the API isn't returning user-configured slots for this RSID — there's nothing for the writer to fill. Demo / sandbox RSIDs are typically empty in this regard; production RSIDs with implemented eVars will return them.

**Symptom: `template_sheet_skipped sheet=<name> reason=missing_or_unanchored` in the logs.**

The named sheet either doesn't exist in your template (renamed?), or its `B4` cell doesn't match the expected section title. Check the template hasn't been edited away from the canonical layout. Anchors required:

| Sheet name (case-sensitive) | `B4` value (case-insensitive) |
|---|---|
| `eVars` | `eVars` |
| `props` | `Props` |
| `custom events (metrics)` | `Custom Events (Metrics)` |
| `metrics-segments` | `Metrics - Segments` |
| `Glossary` | — (no anchor; single-cell `C2` write) |

**Symptom: `template_sheet_skipped sheet=<name> reason=no_id_column` in the logs.**

The header row was found (one of rows 5–10 with `"ID"` at column B) but the expected ID-column header (`Analytics Variable` for eVars/props; `Event` for events) is missing. Restore the column or open an issue if Adobe has changed the template canonical layout.

**Symptom: USAGE (2) "Template not found / not a file / must be a .xlsx file".**

Path validation. Confirm the file exists, is a file (not a directory), and has the `.xlsx` extension. The validator runs pre-dispatch — no auth or API work happens before this check.

**Symptom: USAGE (2) "--template requires --format excel (or an alias that includes excel)".**

You passed `--template` with `--format json` (or another non-excel format). The template-fill writer only applies to Excel output. Drop `--format` (default is `excel`) or pass an alias like `--format reports` / `--format all`.

**Symptom: USAGE (2) "--template requires an SDR-generating action (single or --batch)".**

You combined `--template` with `--diff`, `--watch`, `--list-*`, `--describe-reportsuite`, `--trending-window`, `--compare-with-prev`, or `--inventory-summary`. Template-fill is for fresh SDR generation only. `--agent-mode` is also naturally incompatible (it forces `--format json`).

**Symptom: dropdowns in the `Implementation Status` / etc. columns don't work.**

Pre-existing Adobe template behavior. The template's dropdowns reference an external workbook (`[1]Config!$A$3:$A$6`) that isn't shipped. openpyxl preserves the broken references as-is; we don't fix them. This affects the raw template too, not just our output.

## Log signals

Five events fire during a template-fill run. All have structured extras for log-stream parsing.

| Event | Level | When | Extras |
|---|---|---|---|
| `template_load` | INFO | After `load_workbook` succeeds, before any fill | `path`, `sheets` |
| `template_sheet_filled` | INFO | After each data sheet finishes its fill loop | `sheet`, `rows_matched`, `rows_appended` |
| `template_sheet_skipped` | WARNING | Expected sheet missing or anchor check failed | `sheet`, `reason` (`missing_or_unanchored` / `no_id_column`) |
| `template_overflow` | WARNING | One or more rows appended past `max_row` (default-styled) | `sheet`, `overflow_rows` |
| `template_sheet_clipped` | WARNING | Soft cap dropped rows the API supplied | `sheet`, `rows_dropped`, `soft_cap` |

Health checklist for a "did this work?" assertion in CI / agents:

- Exactly one `template_load` per writer invocation.
- One `template_sheet_filled` per resolved data sheet (4 expected for a complete template).
- Zero `template_sheet_skipped` records — any skip means a template-structure problem.
- `template_overflow` is informational; not a failure. Indicates "this RSID has API IDs the template didn't pre-seed" — normal for tenants with custom calc metrics or segments.
- `template_sheet_clipped` should be zero in practice; investigate if it fires.

## How it works (one-screen)

1. `openpyxl.load_workbook(path)` opens the template, preserving formulas (`data_only=False`).
2. For each data sheet, [`output/_template_anchors.py`](../src/aa_auto_sdr/output/_template_anchors.py)'s `resolve_sheet` confirms the sheet exists, the section title at `B4` matches (case-insensitive), and scans rows 5–10 for the `ID` header marker. Returns a `header_text → 1-indexed column number` map.
3. The writer normalizes API IDs (`variables/<stem>` → `<stem>`, `metrics/<stem>` → `<stem>`) and builds a `wanted = {lower_id: component}` dict.
4. The writer walks pre-existing data rows, matches by lowercased ID, fills in place via `_write_row` (which honors the non-empty rule — never writes `None` or empty over a styled cell).
5. Remaining unmatched components are appended past `max_row`, soft-capped at +50 rows.
6. `wb.save(target)` writes the result. Styles, formulas, defined names, and untouched cells all survive.

Only one module imports `openpyxl` ([`output/writers/excel_template.py`](../src/aa_auto_sdr/output/writers/excel_template.py)), and the import is method-scoped so the fast-path entry stays cheap.

## Related docs

- [CLI Reference — `--template` / `--template-organization`](CLI_REFERENCE.md) — formal flag contract, USAGE matrix
- [Output Formats — `excel-template`](OUTPUT_FORMATS.md) — format key + alias routing
- [Logging Style Guide](LOGGING_STYLE.md) — canonical event vocabulary, including the 5 template events
- [`AGENTS.md`](../AGENTS.md) — unattended-run contract (template-fill section)
- [`CHANGELOG.md`](../CHANGELOG.md) — v1.16.0 entry with dropped-flag rationale
- [v1.16.0 design spec](superpowers/specs/2026-05-11-aa-auto-sdr-v1.16.0-design.md) — full design + spike findings (gitignored; local only)
