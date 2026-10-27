# Sample Outputs

These files demonstrate every output format `aa_auto_sdr` produces. They are
generated from a fixed test fixture (`tests/fixtures/sample_rs.json`) — no real
Adobe Analytics data is committed here.

## Regenerate

```bash
uv run python scripts/build_sample_outputs.py
```

The script is deterministic: re-running produces byte-identical files. CI
asserts the committed tree matches the script's current output via
`tests/test_sample_outputs.py`.

## Files

### Generation outputs (one report suite, one timestamp)

| File | Format | Notes |
|---|---|---|
| `demo_prod.xlsx` | Excel | One sheet per component type. *Best-effort sample only — xlsxwriter embeds creation time in zip metadata, so the file is not byte-deterministic across runs and is excluded from the up-to-date assertion test.* |
| `demo_prod.json` | JSON | Full SdrDocument as JSON, with a top-level `coverage` object. |
| `demo_prod.html` | HTML | Single self-contained file with inline CSS. |
| `demo_prod.md` | Markdown | GFM-flavored. |
| `demo_prod.<component>.csv` | CSV | One file per component type plus `summary` and `coverage` (eight files). `quality_issues` is added only when a quality audit runs. |
| `demo_prod._manifest.json` | CSV manifest | Written last. Lists each CSV file with its SHA-256, row count, and byte size. |

### Diff outputs

Two synthetic snapshots (`synthetic_snapshot_a.json` and `_b.json`) differ by
one renamed dimension and one removed metric. The diff is rendered three ways:

| File | Renderer |
|---|---|
| `diff_console.txt` | Console (ANSI escapes stripped for repo display) |
| `diff_report.json` | JSON renderer (sorted keys, jq-friendly, with a top-level `coverage` object) |
| `diff_report.md` | Markdown renderer (GFM tables, PR-comment-friendly) |
