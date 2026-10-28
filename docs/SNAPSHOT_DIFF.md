# Snapshot & Diff

The "version control of SDR" capability. Capture a snapshot of a report suite's state at one point in time, then compare to a later (or earlier) capture to see exactly what added, removed, or modified.

## Why snapshots

Adobe Analytics report suites change over time — dimensions get renamed, metrics get retired, segments get tweaked. Without a structured way to capture state, "what did the SDR look like last quarter?" is unanswerable. The snapshot/diff feature solves this:

- **Capture** — `--snapshot` persists the normalized SdrDocument as JSON into the profile's snapshot store (see [Storage convention](#storage-convention) below), not next to your format outputs.
- **Compare** — `--diff <a> <b>` produces a structured report of what changed: added components, removed components, per-field deltas on modified components.

Diffs run on the **normalized model**, not on rendered files — renaming a column in Excel does not create a false diff.

## Snapshot file format

Schema: `aa-sdr-snapshot/v4` for a full capture, `aa-sdr-snapshot/v5` for a filtered one. Sorted keys, atomic writes, git-diff-friendly out of the box. Loaders read older majors (`v1`, `v2`, `v3`) and `v4` files without `collected_components` forward-compat — see `CHANGELOG.md` for the per-version field additions.

```json
{
  "schema": "aa-sdr-snapshot/v4",
  "rsid": "demo.prod",
  "captured_at": "2026-04-26T17:29:01+00:00",
  "tool_version": "X.Y.Z",
  "collected_components": [
    "calculated_metrics", "classifications", "dimensions",
    "metrics", "segments", "virtual_report_suites"
  ],
  "degraded_components": [],
  "partial_components": {},
  "quality": {
    "naming_audit": { ... },
    "stale_components": [ ... ],
    "issues": [ ... ],
    "summary": { ... }
  },
  "components": {
    "report_suite": { ... },
    "dimensions": [ ... ],
    "metrics": [ ... ],
    "segments": [ ... ],
    "calculated_metrics": [ ... ],
    "virtual_report_suites": [ ... ],
    "classifications": [ ... ]
  }
}
```

`degraded_components` (a list of component types whose fetch returned no data) and `partial_components` (a map of component type → reduced expansion level) are always present — empty by default. The `quality` block is `null` when no audit ran; when populated it carries `naming_audit`, `stale_components`, `issues`, and `summary`.

### Capture scope (`collected_components`)

`collected_components` is the sorted list of component families the capture requested. An empty array under `components` cannot tell "this family was excluded" apart from "this family really has no rows", so the scope list records which one it is. Scope says what was requested, not how the fetch went: a degraded family is still listed here and also appears in `degraded_components`.

Which schema a new snapshot gets depends on its scope:

| Capture | `schema` | Why |
| --- | --- | --- |
| All six families collected | `aa-sdr-snapshot/v4` | Older readers ignore the extra key, so full captures stay readable by them. |
| Any family left out | `aa-sdr-snapshot/v5` | Older readers refuse v5 with a schema error instead of reading excluded families as deletions. |

Reading rules:

| Envelope | `collected_components` | Result |
| --- | --- | --- |
| `v5` | required | Missing, not a list, unknown or duplicate names → `SnapshotCorruptError`. |
| `v4` | optional | Same checks when present, and the list must name all six families. |
| `v1`–`v4` without the key | absent | Scope is unknown. It is never inferred from empty arrays, and the file is never rewritten. |
| any | — | A family in `degraded_components` or `partial_components` must also be in `collected_components` when the list is present. |

The SDR JSON output (`--format json`) carries the same `collected_components` list. Filtered runs (`--metrics-only` / `--dimensions-only` with `--snapshot` / `--auto-snapshot`) write v5 snapshots; `--watch` always captures every family. How diffs use the scope is described under [Comparability](#comparability-capture-scope-and-fetch-quality).

### Schema compatibility

The `schema` field enables migrations. Loaders reject unknown majors (e.g. `aa-sdr-snapshot/v6`, `aa-sdr-snapshot/v999`) with `SnapshotSchemaError` and naive (timezone-less) timestamps with the same. Older envelopes load forward-compat: `v1` envelopes load with `degraded_components` / `partial_components` defaulted to empty and `quality` defaulted to `null`.

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

Snapshots are profile-scoped, and the directory is chosen by precedence: `--snapshot-dir <path>` if given, else `~/.aa/orgs/<profile>/snapshots/` when `--profile` is set, else the `~/.aa/orgs/default/snapshots/` fallback. That final fallback is **unconditional** — it does not depend on the credential source or on a `default` profile already existing — so `--snapshot` works without `--profile` and simply lands in the `default` store. (Generation still needs resolvable credentials, as any run does; that is separate from the snapshot directory.) Run `--profile-add` once if you want a named profile store instead of the default.

The snapshot file is appended to `RunResult.outputs`, so the `wrote: <path>` trail and batch banner bytes-count both include it.

## The `--diff` action

```text
aa_auto_sdr --diff <a> <b> [--format console|json|markdown|pr-comment] [--output -|<path>] [--profile <name> | --snapshot-dir <path>]
```

Each token is one of five forms:

| Token form | Example | Resolution |
|----|----|----|
| Filesystem path | `./snap-a.json` or `/abs/path.json` | Read JSON, validate schema, return envelope. |
| `<rsid>@<timestamp>` | `demo.prod@2026-04-26T17-29-01+00-00` | Exact match in the active snapshot dir. |
| `<rsid>@latest` | `demo.prod@latest` | Most-recent file in the active snapshot dir. |
| `<rsid>@previous` | `demo.prod@previous` | Second-most-recent file (errors if only one exists). |
| `git:<ref>:<path>` | `git:HEAD~1:snapshots/demo.prod.json` | `git show <ref>:<path>` from cwd. |

Profile-form tokens (`<rsid>@<spec>`) resolve against the active snapshot dir, chosen by the same precedence as capture: `--snapshot-dir` if set, else `~/.aa/orgs/<profile>/snapshots/` when `--profile` is set, else the `~/.aa/orgs/default/snapshots/` fallback. Because that fallback is unconditional, `@spec` tokens resolve even without `--profile` or `--snapshot-dir` (against the `default` store). Path-only and git-only tokens don't touch the snapshot dir at all.

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

### Snapshots from older releases

Two kinds of older snapshot hold values that came from how they were
captured, not from your report suite. The comparison handles both, so a new
capture does not report them as changes:

- **Captured before 1.21.5:** some missing values were written as the text
  `"nan"`, for example `parent_rsid`, `description`, and `category`. When such
  a snapshot loads, those values read as missing. The file on disk does not
  change. In a current snapshot, `"nan"` is kept as written.
- **Captured before 1.21.25:** dimension and metric `tags`, `data_group`,
  and `extra` were not collected. When either snapshot is this old,
  `--extended-fields` skips those three fields for dimensions and metrics
  and logs a `diff_legacy_capture_fields` warning. The default comparison
  never includes them.

These rules were adopted from the sister project `cja_auto_sdr`'s diff comparator after observing they suppressed the most common false-positive categories in real-world snapshot history.

### Comparability (capture scope and fetch quality)

Before diffing a component family, the comparator decides whether the two sides can be compared at all. When they cannot, the section is suppressed: it counts toward no totals or thresholds, renderers show its `suppression_reason` instead of rows, and it carries a `comparability` value. For `excluded` and `unknown` sections the JSON `added` / `removed` / `modified` lists are empty, because one side holds no data for the family. For `degraded` and `partial` sections the JSON keeps the raw rows as evidence. The rules apply in this order; the first match wins.

| Situation for the family | `comparability` | `suppression_reason` |
| --- | --- | --- |
| Neither side collected it | `excluded` | `not collected in either snapshot` |
| The source did not collect it | `excluded` | `not collected in source` |
| The target did not collect it | `excluded` | `not collected in target` |
| Either side's fetch was degraded | `degraded` | `fetch degraded` |
| The sides were fetched at different partial expansion levels | `partial` | `fetch partial (expansion_level=…)` |
| A side has unknown scope (no `collected_components`), its list is empty, and the other side has rows | `unknown` | `capture scope unknown (legacy snapshot)` |
| Anything else | `comparable` | — (normal diff) |

A side with unknown scope that has rows counts as collected, since the rows show the family was fetched. Two empty lists are comparable and give zero changes. When both sides have unknown scope, the family diffs normally: released versions never wrote filtered snapshots, so two snapshots without scope are both full captures. So a filtered capture never produces false additions or removals, while a family that was collected on both sides and really became empty still reports its removals. The cost of the unknown rule: a family that really was empty in a snapshot without scope and is populated now shows as suppressed, with that label, rather than as additions.

`--compare-with-prev`, `--watch`, and `--trending-window` all use the same comparator, so the same rules apply there.

**Filtered snapshots in a history.** Automatic baselines skip snapshots that left out families the current capture collected. Watch, `--compare-with-prev`, and each `--trending-window` point compare against the newest earlier snapshot whose scope covers the current one: it collected every family the current capture collected, and a snapshot without scope counts as a full capture. So a `--metrics-only --snapshot` run between two full captures never hides changes to dimensions, segments, or the other families. A metrics-only capture compares against the last capture that included metrics.

- Diff JSON (from `--compare-with-prev`) carries `baseline_skipped`, the `captured_at` values of the newer snapshots that were passed over; `a_captured_at` names the baseline used (`b_captured_at` with `--reverse`). Older snapshots that cannot be read are passed over with a `baseline_candidate_skipped` warning; only the latest snapshot must load.
- Watch `change` events carry `baseline: {captured_at, skipped}`. Watch always captures every family, so its baseline is the newest full capture; with only filtered history, the next cycle is a new `baseline` event that carries `baseline: {captured_at: null, skipped}`.
- Trending series points carry `baseline_captured_at` (the snapshot each point was compared against) and `collected_components`. A point with no covering earlier snapshot has no deltas. Drift counts each change once: a point is left out of drift (but keeps its deltas) when a later point compared against the same baseline and covers its scope, and only counted points enter `n_pairs` for volatility.
- `--keep-last` / `--keep-since` pruning never deletes the newest full capture, so a covering baseline survives retention.
- Explicit `--diff` tokens stay literal: `<RSID>@previous` is always the second-newest file, and paths or `<RSID>@<timestamp>` are used as given. If such a pair covers different scopes, the comparison logs a `diff_scope_mismatch` warning.

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
  "a_tool_version": "1.21.0",
  "b_tool_version": "1.21.15",
  "report_suite_deltas": [
    {"field": "timezone", "before": "US/Pacific", "after": "US/Mountain"}
  ],
  "components": [
    {
      "component_type": "dimensions",
      "added": [{"id": "evar99", "name": "Mobile Operator"}, ...],
      "removed": [],
      "modified": [{"id": "evar15", "name": "Page Type", "deltas": [...]}],
      "unchanged_count": 124,
      "suppressed": false,
      "suppression_reason": null,
      "comparability": "comparable"
    },
    ...
  ],
  "rsid_mismatch": false,
  "settings_changes": 1,
  "coverage": {
    "compare_fields": ["curated_components", "definition", "name", "parent", "..."],
    "ignored_fields": ["categories", "category", "compatibility", "created", "data_group",
                       "description", "extra", "modified", "owner_id", "tags"],
    "component_types": ["dimensions", "metrics", "segments", "calculated_metrics",
                        "virtual_report_suites", "classifications"],
    "settings_fields": ["currency", "name", "parent_rsid", "timezone"],
    "settings_policy": "reported",
    "show_only": null,
    "limitations": ["warn_threshold_counts_components_only"]
  }
}
```

Sorted keys, stable shape, jq-friendly. Pipe-safe via `--output -`. Keys are emitted alphabetically sorted (shown grouped above for readability). `report_suite_deltas` carries the report-suite header changes (timezone, currency, etc.) and is an empty list when the header is unchanged; it is also emptied in `--summary` mode. `settings_changes` counts those changed fields (one per field) and is kept in `--summary` mode. It is never added to component totals. Each component carries `suppressed` / `suppression_reason` — non-null only when the [comparability rules](#comparability-capture-scope-and-fetch-quality) skip that component's per-item diff — and `comparability` (`comparable`, `excluded`, `unknown`, `degraded`, or `partial`).

#### Diff JSON `coverage`

The top-level `coverage` object says what the comparison compared, so a reader can judge the evidence behind it. Its shape follows the diff `coverage` object in `cja_auto_sdr`, with aa's field names. It describes the full comparison, before `--show-only`, `--changes-only`, or `--max-issues` trim the rendered `components`, and it is kept in `--summary` mode.

| Key | Meaning |
|-----|---------|
| `compare_fields` | Sorted top-level component fields that were compared. The identity fields `id` and `rsid` are never deltas, and ignored fields are left out. Keys nested under these fields are compared too. |
| `ignored_fields` | Sorted effective ignore set: `--ignore-fields` plus the default extended-field set, or only `--ignore-fields` with `--extended-fields`. It applies at every nesting level and to report-suite settings. |
| `component_types` | The six component types in render order. |
| `settings_fields` | Sorted report-suite settings that were compared. |
| `settings_policy` | Always `reported`: setting changes appear in `report_suite_deltas` and `settings_changes` but never count toward `--warn-threshold`. `--watch` treats any setting change as a trigger. |
| `show_only` | Sorted `--show-only` types, or `null`. |
| `limitations` | Stable string IDs, listed below. |

Limitation IDs:

- `warn_threshold_counts_components_only`: always present. `--warn-threshold` counts added, removed, and modified components in comparable sections only.
- `baseline_chosen_by_time`: an explicit `--diff` side was `<RSID>@latest` or `<RSID>@previous`. Those tokens pick snapshots by time, not by capture scope. `--compare-with-prev` never reports it, because it chooses a covering baseline.
- `excluded_families_not_compared`: at least one family has `comparability: "excluded"`. This includes a family that neither side collected.
- `suppressed_families_not_compared`: at least one family is `unknown`, `degraded`, or `partial` and was not compared.
- `show_only_does_not_narrow_warn_threshold`: `--show-only` was given. It hides sections from the output, but `--warn-threshold` still counts every comparable section.

`compare_fields` and `settings_fields` come from the current tool's models, not from the keys in the two snapshots. A field that is present only in older snapshots is still compared (unless it is ignored), but it is not listed.

Each `--compare-with-prev` JSON result's `report` is a diff JSON document, so it carries `coverage` too. Watch events do not.

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

Alongside the per-run `--snapshot` flag, `--auto-snapshot`, retention, listing, and pruning manage snapshots as a long-lived store scoped to the selected snapshot directory.

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
- `--warn-threshold N` — exit `3` (WARN) if total component changes are `>= N`. Report-suite setting changes are always shown (every format, including `--summary` and `pr-comment`) but do not count. Useful in CI.
- `--color-theme {default,accessible}` — console diff color palette.

## Sugar for the common diff

```bash
aa_auto_sdr --compare-with-prev <RSID> --profile prod
```

`--compare-with-prev` is shorthand for `--diff <RSID>@previous <RSID>@latest --profile <name>`. It's the typical "what changed since last capture" form, so prefer it to the long form unless you need a non-default base.

### Multiple previous comparisons

With two or more positional RSIDs, `--compare-with-prev` emits one combined
result in input order and writes a file destination once, atomically. Console,
Markdown, and PR-comment output include a section for every suite with its
`exit_code`, including snapshot errors. One-RSID output retains the ordinary
diff format.

JSON uses this envelope (each result contains exactly one of `report` or `error`):

```json
{
  "schema": "aa-compare-with-prev/v1",
  "results": [
    {"rsid": "rs1", "exit_code": 0, "report": {"a_rsid": "rs1"}},
    {"rsid": "missing", "exit_code": 16,
     "error": {"error_type": "SnapshotResolveError", "error": "Snapshot not found"}}
  ],
  "exit_code": 16
}
```

The abbreviated `report` above is the existing JSON diff report, with the same
presentation flags applied. `error_type` is the exception class name and `error`
is its message. Snapshot failures also retain the usual stderr diagnostics;
JSON and Markdown stdout destinations use the existing stderr JSON error envelope.

The result and command exit codes are the maximum per-suite code: warning `3`
remains lower than snapshot failure `16`; mixed results do not introduce a
partial-success code. Warning thresholds and GitHub step summaries use full
unfiltered reports. A failure to write the combined output raises `OutputError`
(exit `15`), even when a suite failed with `16`, because the requested artifact
was not emitted. Failed atomic replacement preserves an existing destination.

## Trending: rollup across a window of snapshots

```bash
aa_auto_sdr --trending-window 30d <RSID> --profile prod
aa_auto_sdr --trending-window 30d <RSID> --profile prod --format json --output - | jq '.summary'
```

`--trending-window <DURATION>` reads existing snapshots from the active snapshot store (no API contact) and reports component counts and lifecycle changes across the window. Its drift summary includes total changes, a volatility score, the most active component type, and churn by component type; it does not summarize quality findings. Duration grammar is the same as `--keep-since` (`Nh|Nd|Nw`). `--snapshot-dir <PATH>` overrides the active snapshot directory for capture (`--snapshot` / `--auto-snapshot`), `--diff`, `--list-snapshots`, `--prune-snapshots`, `--compare-with-prev`, `--trending-window`, and `--watch`.

Trending renderers live under `output/trending_renderers/` (`console`, `json`, `markdown`); select with `--format`. Families that were not comparable between two snapshots contribute zero churn. JSON carries `comparability` and `suppression_reason` in each `delta_by_type` entry, and the console and Markdown tables add a "Not comparable" note naming the families and the reason.

## Watch: foreground monitoring loop

```bash
aa_auto_sdr --watch --interval 1h <RSID> --profile prod
```

`--watch` runs a foreground loop that captures a fresh snapshot at each `--interval` tick, diffs it against the prior baseline, and emits NDJSON events to stdout (`aa-watch-event/v1`). Event types: `baseline` (first cycle), `change` (when at least `--watch-threshold` components differ, default 1, or when any report-suite setting changed), `error`. `summary.settings_changes` counts changed setting fields; setting changes ignore the threshold and never enter component counts.

Watch counts only comparable component changes after applying `--ignore-fields`
and the default extended-field filtering. Sections that are not comparable (a
family one side did not collect, unknown legacy scope, degraded fetches, or
mismatched partial-fetch levels) contribute zero counts, including unchanged
counts, while their `summary.by_type` entries remain present. Every `by_type`
entry carries `comparability`; suppressed entries also carry
`suppression_reason`, so their zeros read as "not comparable", not "no changes". Captured snapshots
retain the raw data and availability markers; suppression does not establish
that unavailable components are unchanged.

Before fetching, watch reads history from newest to oldest in the store's
existing filename order. It skips malformed JSON, invalid UTF-8, and supported
envelopes whose structure cannot be used for comparison. Each skipped file
produces a warning on stderr/logs and remains untouched. Watch compares the
fresh capture against the first usable candidate, so a recovery diff can span
several capture intervals. When no usable history remains, the fresh capture
establishes a `baseline`; subsequent cycles compare against it.

Unsupported schema identifiers, errors reading discovered snapshot files, and
a valid snapshot with the wrong RSID remain cycle errors. Watch does not fetch
or save that suite in that cycle; other suites and later cycles continue. Recovery
does not quarantine, delete, or repair history, and it does not change the
stdout event schema.

Watch completes directory discovery before loading history. Permission, I/O,
and incomplete-listing failures produce a cycle `error` before fetching or
saving that suite, so they cannot establish a false baseline or trigger Git or
Notion publication. Other suites and later cycles continue; once access returns,
watch compares against the existing usable history. A missing RSID directory
at initial open (including a missing snapshot root), or a readable empty
directory, still permits a first baseline. Shared snapshot list, prune, diff,
and trending commands retain their existing discovery behavior.

At threshold `0`, heartbeat cycles still emit `change` events with zero eligible
changes and run Git operations when enabled. Zero-change cycles never publish
to Notion; the first baseline still publishes when configured.

- `--interval Nh|Nd|Nw` — required with `--watch`.
- `--watch-threshold N` — minimum changes to emit (default 1; `0` = heartbeat, emits every cycle).
- SIGINT / SIGTERM exit cleanly with code 0.
- `--watch` accepts only `--format json` or `--format notion`. Any other format value exits 2.
- `--quality-policy` and `--fail-on-quality` are rejected with `--watch` (exit 2).

## Sample outputs

Browse [`sample_outputs/`](../sample_outputs/) for committed examples of each diff renderer's output.

## See also

- [`CLI_REFERENCE.md`](CLI_REFERENCE.md) — full flag reference
- [`OUTPUT_FORMATS.md`](OUTPUT_FORMATS.md) — generation formats, aliases, and file layouts
- [`sample_outputs/`](../sample_outputs/) — browse representative outputs
