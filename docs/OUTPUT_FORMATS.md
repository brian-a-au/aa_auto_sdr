# Output Formats

`aa_auto_sdr` supports five base formats and four aliases for SDR generation, plus three formats for diff output. Browse [`sample_outputs/`](../sample_outputs/) for committed examples of each.

## Base formats (generation)

| Format | Extension | File layout | Use case |
|--------|-----------|-------------|----------|
| `excel` | `.xlsx` | Single workbook with one sheet per component type | Human review; default format |
| `csv` | `.csv` | Multi-file: one CSV per component type (7 files: report_suite, dimensions, metrics, segments, calculated_metrics, virtual_report_suites, classifications, plus a summary) | Spreadsheet integration; tabular tooling |
| `json` | `.json` | Single self-contained JSON file with the full SdrDocument | Automation; jq pipelines; downstream tooling |
| `html` | `.html` | Single self-contained HTML file with inline CSS, no JavaScript | Sharing as a static report; PR/email attachments |
| `markdown` | `.md` | Single GFM-flavored Markdown file with one H2 per component type | PR comments; wiki-friendly; readable in GitHub |

### Default

`excel` is the default if `--format` is omitted:

```bash
uv run aa_auto_sdr <RSID>                    # produces <RSID>.xlsx
uv run aa_auto_sdr <RSID> --format json      # produces <RSID>.json
```

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
