# Snapshot & Diff

The "version control of SDR" capability. Capture a snapshot of a report suite's state at one point in time, then compare to a later (or earlier) capture to see exactly what added, removed, or modified.

## Why snapshots

Adobe Analytics report suites change over time — dimensions get renamed, metrics get retired, segments get tweaked. Without a structured way to capture state, "what did the SDR look like last quarter?" is unanswerable. The snapshot/diff feature solves this:

- **Capture** — `--snapshot` persists the normalized SdrDocument as JSON next to your output files.
- **Compare** — `--diff <a> <b>` produces a structured report of what changed: added components, removed components, per-field deltas on modified components.

Diffs run on the **normalized model**, not on rendered files — renaming a column in Excel does not create a false diff.

## Snapshot file format

Schema: `aa-sdr-snapshot/v4`. Sorted keys, atomic writes, git-diff-friendly out of the box. Loaders read older majors (`v1`, `v2`, `v3`) forward-compat — see `CHANGELOG.md` for the per-version field additions.

```json
{
  "schema": "aa-sdr-snapshot/v4",
  "rsid": "demo.prod",
  "captured_at": "2026-04-26T17:29:01+00:00",
  "tool_version": "X.Y.Z",
  "components": {
    "report_suite": { ... },
    "dimensions": [ ... ],
    "metrics": [ ... ],
    "segments": [ ... ],
    "calculated_metrics": [ ... ],
    "virtual_report_suites": [ ... ],
    "classifications": [ ... ]
  },
  "quality": {
    "fetch_status": { ... },
    "issues": [ ... ],
    "summary": { ... }
  }
}
```

The `schema` field enables migrations. Loaders reject unknown majors (e.g. `aa-sdr-snapshot/v999`) with `SnapshotSchemaError` and naive (timezone-less) timestamps with the same. Older envelopes load with missing fields defaulted (v1 envelopes load as if `fetch_status` reports all components healthy and the `quality` block is empty).

## Storage convention

```
~/.aa/orgs/<profile>/snapshots/<RSID>/<ISO-timestamp>.json
```

Filenames replace ISO-8601 colons with hyphens for cross-FS safety:

```
2026-04-26T17:29:01+00:00  →  2026-04-26T17-29-01+00-00.json
```

The in-payload `captured_at` field keeps the proper colon form. Only the filename is sanitized.

## Capturing snapshots

Add `--snapshot --profile <name>` to any generation command:

```bash
uv run aa_auto_sdr <RSID> --snapshot --profile prod
uv run aa_auto_sdr --batch RS1 RS2 --snapshot --profile prod
```

Snapshots are profile-scoped (the path embeds the profile name), so `--snapshot` requires `--profile`. Without a profile, the command exits 10 with a clear error. To bypass that requirement, run `--profile-add` once to create a profile for your default org.

The snapshot file is appended to `RunResult.outputs`, so the `wrote: <path>` trail and batch banner bytes-count both include it.

## The `--diff` action

```text
aa_auto_sdr --diff <a> <b> [--format console|json|markdown|pr-comment] [--output -|<path>] (--profile <name> | --snapshot-dir <path>)
```

Each token is one of five forms:

| Token form | Example | Resolution |
|----|----|----|
| Filesystem path | `./snap-a.json` or `/abs/path.json` | Read JSON, validate schema, return envelope. |
| `<rsid>@<timestamp>` | `demo.prod@2026-04-26T17-29-01+00-00` | Exact match in the active snapshot dir. |
| `<rsid>@latest` | `demo.prod@latest` | Most-recent file in the active snapshot dir. |
| `<rsid>@previous` | `demo.prod@previous` | Second-most-recent file (errors if only one exists). |
| `git:<ref>:<path>` | `git:HEAD~1:snapshots/demo.prod.json` | `git show <ref>:<path>` from cwd. |

Profile-form tokens (`<rsid>@<spec>`) require `--profile` or `--snapshot-dir`. Path-only and git-only tokens don't. The active snapshot dir is `--snapshot-dir` if set, otherwise `~/.aa/orgs/<profile>/snapshots/`.

### Examples

```bash
# Two file paths
uv run aa_auto_sdr --diff a.json b.json

# Profile-scoped aliases (most common workflow)
uv run aa_auto_sdr --diff demo.prod@latest demo.prod@previous --profile prod

# Specific timestamp
uv run aa_auto_sdr --diff demo.prod@2026-04-20T10-00-00+00-00 demo.prod@latest --profile prod

# Git ref (snapshot file at a specific commit)
uv run aa_auto_sdr --diff git:HEAD~1:snapshots/demo.prod.json git:HEAD:snapshots/demo.prod.json

# Mixed (one path, one alias)
uv run aa_auto_sdr --diff demo.prod@previous /tmp/baseline.json --profile prod

# Output to a file
uv run aa_auto_sdr --diff a.json b.json --format markdown --output diff.md

# Pipe JSON to jq
uv run aa_auto_sdr --diff a.json b.json --format json --output - | jq '.components[]'
```

## Diff semantics

For each component type (`dimensions`, `metrics`, `segments`, `calculated_metrics`, `virtual_report_suites`, `classifications`), the comparator emits:

- **`added`** — components present in target (b) but not source (a)
- **`removed`** — components present in source (a) but not target (b)
- **`modified`** — components present in both with at least one field-level delta
- **`unchanged_count`** — integer; no detail

The `report_suite` header is also diffed (rare — name/timezone/currency change) and reported as a `ReportSuiteDiff` with field deltas.

### Identity by ID, never by name

A name change is a **modification**, not an `add` + `remove`. The comparator looks up components by their `id` field (e.g. `evar1`, `metrics/visits`). Display names are only used for the human-readable label in renderer output.

### Value normalization (false-positive prevention)

Three rules eliminate the most common false-positive diff categories:

1. **String whitespace** — `"hello"` and `"  hello  "` compare equal.
2. **Missing-equivalents** — `None`, `""`, and `float('nan')` are all treated as the same value.
3. **Order-insensitive lists** — `tags` and `categories` are sorted before compare, so `["A", "B"]` vs `["B", "A"]` is not a diff.

Other lists (e.g. `definition` clauses in segments) are compared positionally.

These rules were adopted from the sister project `cja_auto_sdr`'s diff comparator after observing they suppressed the most common false-positive categories in real-world snapshot history.

### RSID mismatch warning

If you diff snapshots of *different* report suites (e.g. `demo.prod` vs `demo.staging`), the report sets `rsid_mismatch=True`. Renderers surface a `⚠ RSID mismatch` banner. The diff still runs — sometimes you genuinely want to compare two RSes — but the warning is loud.

## Renderer formats

Four pure renderers, all take a `DiffReport` and return a string:

### `console` (default)

Banner-style output with ANSI colors (auto-disabled for non-TTY stdout or `NO_COLOR=1`):

```text
============================================================
SDR DIFF
============================================================
Source: demo.prod @ 2026-04-20T10:00:00+00:00 (tool X.Y.Z)
Target: demo.prod @ 2026-04-26T17:29:01+00:00 (tool X.Y.Z)

Dimensions: +2 added, -0 removed, ~1 modified, 124 unchanged
  + evar99 — Mobile Operator
  + evar100 — Region
  ~ evar15 — Page Type
      type: "string" → "enum"
      tags: + "deprecated"

Metrics: +0 added, -1 removed, ~0 modified, 32 unchanged
  - event5 — Custom Event 5

...
```

`--format console --output -` is **rejected** (exit 15) — console is for humans, use json/markdown for pipes.

### `json`

```json
{
  "a_rsid": "demo.prod",
  "b_rsid": "demo.prod",
  "a_captured_at": "2026-04-20T10:00:00+00:00",
  "b_captured_at": "2026-04-26T17:29:01+00:00",
  "components": [
    {
      "component_type": "dimensions",
      "added": [{"id": "evar99", "name": "Mobile Operator"}, ...],
      "removed": [],
      "modified": [{"id": "evar15", "name": "Page Type", "deltas": [...]}],
      "unchanged_count": 124
    },
    ...
  ],
  "rsid_mismatch": false
}
```

Sorted keys, stable shape, jq-friendly. Pipe-safe via `--output -`.

### `markdown`

GitHub-flavored Markdown with tables. PR-comment-friendly; pipe character escaping handled. Empty sections (no changes for a component type) are omitted entirely.

### `pr-comment`

Compact GFM with collapsible `<details>` blocks, optimized for pasting into a GitHub PR comment. Length-capped at 60K chars (GitHub's comment limit is 65,536); when exceeded, truncates at the last `</details>` boundary with a banner line. Pipe-safe via `--output -`.

```bash
uv run aa_auto_sdr --diff RS1@previous RS1@latest --profile prod --format pr-comment | pbcopy
```

## Common workflows

### Capture-now-diff-later

```bash
# Today: capture a baseline
uv run aa_auto_sdr <RSID> --profile prod --snapshot

# Quarterly review: capture a new snapshot, diff against the previous
uv run aa_auto_sdr <RSID> --profile prod --snapshot
uv run aa_auto_sdr --diff <RSID>@latest <RSID>@previous --profile prod
```

### Track snapshots in git for audit

```bash
# Set up a separate repo for snapshot tracking
mkdir sdr-snapshots && cd sdr-snapshots
git init

# Quarterly: copy the latest snapshot in, commit
cp ~/.aa/orgs/prod/snapshots/<RSID>/<ts>.json snapshots/<RSID>.json
git add . && git commit -m "Q1 2026 snapshot"

# Diff between two committed snapshots
uv run aa_auto_sdr --diff git:HEAD~1:snapshots/<RSID>.json git:HEAD:snapshots/<RSID>.json
```

### Detect drift in CI

```bash
# Capture a snapshot, diff against last week's, exit non-zero if anything changed
uv run aa_auto_sdr <RSID> --profile prod --snapshot
uv run aa_auto_sdr --diff <RSID>@latest <RSID>@previous --profile prod --format json --output - \
  | jq -e '.components[] | select(.added or .removed or .modified | length > 0)' \
  && echo "DRIFT DETECTED" || echo "no changes"
```

## Exit codes (diff- and snapshot-relevant subset)

| Code | Meaning |
|----|----|
| 0 | Diff ran successfully (regardless of whether changes exist) |
| 3 | `--warn-threshold` exceeded (diff itself ran successfully) |
| 10 | `--list-snapshots` / `--prune-snapshots` missing both `--profile` and `--snapshot-dir`, or missing policy |
| 15 | Bad `--format`/`--output` combination |
| 16 | Snapshot resolve / schema / git failure |

Full table: `src/aa_auto_sdr/core/exit_codes.py` (consumed by `aa_auto_sdr --exit-codes`). For code-by-code remediation, run `aa_auto_sdr --explain-exit-code 16`.

## Snapshot lifecycle

Beyond the per-run `--snapshot` flag, three first-class actions manage snapshots as a long-lived, profile-scoped store.

### Auto-snapshot on every run

```bash
uv run aa_auto_sdr <RSID> --profile prod --auto-snapshot
uv run aa_auto_sdr --batch RS1 RS2 --profile prod --auto-snapshot
```

Equivalent to passing `--snapshot` every time, but designed to be set as a default. If both `--snapshot` and `--auto-snapshot` are passed, exactly one save happens (no duplicate file).

### Retention policy

```bash
# Keep only the 5 most recent snapshots per RSID
aa_auto_sdr --auto-snapshot --auto-prune --keep-last 5 RS1 --profile prod

# Keep only snapshots newer than 30 days (per RSID)
aa_auto_sdr --auto-snapshot --auto-prune --keep-since 30d RS1 --profile prod

# Or apply retention without doing a generation
aa_auto_sdr --prune-snapshots --keep-last 10 --profile prod
aa_auto_sdr --prune-snapshots RS1 --keep-since 90d --profile prod --dry-run
```

`--keep-since` accepts `<int><h|d|w>` — `12h`, `30d`, `4w`. Mutually exclusive with `--keep-last`.

`--dry-run` (with `--prune-snapshots`) prints what would be deleted without unlinking.

Snapshots whose filenames don't match the expected ISO-8601 stem are **kept**, not deleted, as a fail-closed safety default — a future filename-format change won't silently delete recent snapshots.

### Listing

```bash
aa_auto_sdr --list-snapshots --profile prod
aa_auto_sdr --list-snapshots RS1 --profile prod --format json | jq '.[].captured_at'
```

The JSON output's `captured_at` field is canonical ISO-8601 (with colons), so it round-trips cleanly through `datetime.fromisoformat`. `path` is the filesystem location, useful for diff inputs:

```bash
aa_auto_sdr --diff $(aa_auto_sdr --list-snapshots RS1 --profile prod --format json | jq -r '.[-2:][0].path') $(aa_auto_sdr --list-snapshots RS1 --profile prod --format json | jq -r '.[-1].path') --format pr-comment
```

…or just use the `@latest` / `@previous` shortcuts described in the diff section above.

## Diff modes

Three modifier flags reshape the diff output without changing the comparator:

- `--side-by-side` — render modified-component fields with before/after columns. Affects console mostly; markdown's existing layout already includes Before/After columns.
- `--summary` — collapse output to per-component-type counts; suppress per-item / per-field detail. Useful for high-level CI summaries.
- `--ignore-fields description,tags` — comma-separated field names to skip during compare. Match is exact at every nesting level (e.g., skips `segments[*].definition.description` too). Filtering happens in the comparator, so the resulting `DiffReport` is clean for piped JSON consumers.

```bash
aa_auto_sdr --diff RS1@previous RS1@latest --profile prod --summary
aa_auto_sdr --diff a.json b.json --ignore-fields description,tags
```

The `--format pr-comment` renderer produces compact GFM with collapsible `<details>` blocks, optimized for pasting into a GitHub PR comment. Length-capped at 60K chars (GitHub's comment limit is 65,536); when exceeded, truncates at the last `</details>` boundary with a banner line.

```bash
aa_auto_sdr --diff RS1@previous RS1@latest --profile prod --format pr-comment | pbcopy
```

### Other diff-shaping flags

- `--extended-fields` — include extended/auxiliary fields in the comparison that are otherwise summarized away.
- `--changes-only` — drop component types with no changes from the rendered output.
- `--show-only dimensions,metrics` — restrict the diff to listed component types.
- `--max-issues N` — cap per-component added/removed/modified counts in the rendered output.
- `--quiet-diff` — suppress unchanged-count trailers.
- `--diff-labels Source=Before Target=After` — override the default Source/Target labels.
- `--reverse-diff` — swap a/b before compare.
- `--warn-threshold N` — exit `3` (WARN) if total changes are `>= N`. Useful in CI.
- `--color-theme {default,accessible}` — console diff color palette.

## Sugar for the common diff

```bash
aa_auto_sdr --compare-with-prev <RSID> --profile prod
```

`--compare-with-prev` is shorthand for `--diff <RSID>@previous <RSID>@latest --profile <name>`. It's the typical "what changed since last capture" form, so prefer it to the long form unless you need a non-default base.

## Trending: rollup across a window of snapshots

```bash
aa_auto_sdr --trending-window 30d <RSID> --profile prod
aa_auto_sdr --trending-window 30d <RSID> --profile prod --format json --output - | jq '.summary'
```

`--trending-window <DURATION>` reads existing snapshots from the active snapshot store (no API contact) and emits a rollup of how component counts and quality signals moved across the window. Duration grammar is the same as `--keep-since` (`Nh|Nd|Nw`). `--snapshot-dir <PATH>` overrides the profile's snapshot directory; honored uniformly by every snapshot-aware action (`--snapshot`, `--diff`, `--list-snapshots`, `--prune-snapshots`, `--compare-with-prev`, `--trending-window`, `--watch`).

Trending renderers live under `output/trending_renderers/` (`console`, `json`, `markdown`); select with `--format`.

## Watch: foreground monitoring loop

```bash
aa_auto_sdr --watch --interval 1h <RSID> --profile prod
```

`--watch` runs a foreground loop that captures a fresh snapshot at each `--interval` tick, diffs it against the prior baseline, and emits NDJSON events to stdout (`aa-watch-event/v1`). Event types: `baseline` (first cycle), `change` (when at least `--watch-threshold` components differ; default 1), `error`.

- `--interval Nh|Nd|Nw` — required with `--watch`.
- `--watch-threshold N` — minimum changes to emit (default 1; `0` = heartbeat, emits every cycle).
- SIGINT / SIGTERM exit cleanly with code 0.
- `--watch` accepts only `--format json` or `--format notion`. Any other format value exits 2.
- `--quality-policy` and `--fail-on-quality` are rejected with `--watch` (exit 2).

## Sample outputs

Browse [`sample_outputs/`](../sample_outputs/) for committed examples of each diff renderer's output.

## See also

- [`CLI_REFERENCE.md`](CLI_REFERENCE.md) — full flag reference
- [`OUTPUT_FORMATS.md`](OUTPUT_FORMATS.md) — five generation formats
- [`sample_outputs/`](../sample_outputs/) — browse representative outputs
