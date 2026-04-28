"""Central exit-code enum + explanations. Single source of truth.

Every CLI handler reads from ExitCode.X.value (or assigns directly to ExitCode.X
in handler return statements). Per-command `_EXIT_*` private constants in
generate.py / batch.py / diff.py / main.py are removed in v0.9; they used to
duplicate this map in five places."""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    GENERIC = 1
    USAGE = 2
    WARN = 3  # v1.2 — diff --warn-threshold exceeded (diff itself ran successfully)
    CONFIG = 10
    AUTH = 11
    API = 12
    NOT_FOUND = 13
    PARTIAL_SUCCESS = 14  # v0.5 batch: some succeeded, some failed
    OUTPUT = 15
    SNAPSHOT = 16  # v0.7 snapshot resolve / schema / git failure


# One-line description per code, used by --exit-codes.
ROWS: list[tuple[ExitCode, str]] = [
    (ExitCode.OK, "Success"),
    (ExitCode.GENERIC, "Generic error (uncategorized failure)"),
    (ExitCode.USAGE, "Argument / usage error from argparse"),
    (ExitCode.WARN, "Diff --warn-threshold exceeded (diff itself ran successfully)"),
    (ExitCode.CONFIG, "Bad config or missing credentials"),
    (ExitCode.AUTH, "Adobe OAuth Server-to-Server failure"),
    (ExitCode.API, "Adobe Analytics API request failed"),
    (ExitCode.NOT_FOUND, "Report suite or other resource not found"),
    (ExitCode.PARTIAL_SUCCESS, "Batch ran with mixed success and failure"),
    (ExitCode.OUTPUT, "Output writer failure (filesystem / format mismatch)"),
    (ExitCode.SNAPSHOT, "Snapshot resolve / schema / git failure"),
]


# Multi-line explanation per code, used by --explain-exit-code.
EXPLANATIONS: dict[ExitCode, str] = {
    ExitCode.OK: """The command succeeded. The requested operation completed without error,
no further action needed.""",
    ExitCode.GENERIC: """An uncategorized failure. The CLI fell through every typed
exception handler. Inspect stderr for context.

Likely causes:
- An internal bug or unexpected condition in the tool itself.

What to try:
- Re-run with the same arguments and capture full stderr.
- Open an issue at https://github.com/brian-a-au/aa_auto_sdr/issues with the
  command, full output, and the version (`aa_auto_sdr -V`).""",
    ExitCode.USAGE: """The arguments did not parse correctly (argparse error).

Likely causes:
- A required positional or option is missing.
- A flag was combined with a mutually-exclusive flag (e.g. `--diff` + `<RSID>`).
- `--prune-snapshots` invoked on a non-interactive stdin without `--yes` and without
  `--dry-run` — the confirmation prompt cannot be answered, so the run
  refuses with USAGE rather than silently no-op (changed in v1.2.1).

What to try:
- Run `aa_auto_sdr --help` to see the full surface.
- Run `aa_auto_sdr --exit-codes` for the full code list.""",
    ExitCode.WARN: """The diff completed but the count of changes (added + removed +
modified) met or exceeded --warn-threshold.

Likely causes:
- Significant SDR drift between the two snapshots.
- Threshold set too low for normal churn rate.

What to try:
- Inspect the diff output to see which components changed.
- If the threshold is wrong, raise it; if the drift is real, address upstream.
- This is a soft signal — the diff itself ran successfully.""",
    ExitCode.CONFIG: """Configuration is missing or incomplete.

Likely causes:
- Required env vars unset (`ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES`).
- `--snapshot` or `--auto-snapshot` used without `--profile`.
- `--profile NAME` referenced but no profile file at `~/.aa/orgs/NAME/`.
- `--list-snapshots`, `--prune-snapshots`, `--profile-test`, `--profile-show`,
  or `--profile-import` used without `--profile` (when required) or with
  a profile that doesn't exist.
- `--prune-snapshots` or `--auto-prune` used without `--keep-last` or
  `--keep-since`.
- `--keep-since` value not in `<int><h|d|w>` form (e.g. `forever` is rejected;
  use `30d`, `12h`, `4w`).
- `--profile-import` source file missing required fields
  (`org_id`, `client_id`, `secret`, `scopes`).

What to try:
- Run `aa_auto_sdr --show-config` to see which credentials source resolved.
- Run `aa_auto_sdr --profile-add NAME` to create a profile interactively.
- Run `aa_auto_sdr --profile-list` to list known profiles.""",
    ExitCode.AUTH: """OAuth Server-to-Server authentication failed.

Likely causes:
- Bad client_id / secret combination.
- SCOPES missing the verified-minimum set (Adobe rejects reads silently).
- Integration not added to an Adobe Analytics Product Profile in Admin Console.
- `--profile-test` failed at OAuth or `getCompanyId()` for the named profile.

What to try:
- Verify credentials in Adobe Developer Console (https://developer.adobe.com/console).
- Confirm SCOPES contains the verified-minimum three: `openid AdobeID
  additional_info.projectedProductContext`. Two more are recommended for
  fuller endpoint coverage: `read_organizations` and
  `additional_info.job_function` (add them if `--list-reportsuites` returns
  empty or `/dimensions` / `/metrics` return 403 despite a successful auth).
- Run `aa_auto_sdr --profile-test NAME` to surface the underlying auth error.""",
    ExitCode.API: """An Adobe Analytics API request failed.

Likely causes:
- Network failure or AA API outage.
- Rate limit exceeded.
- A query timed out server-side.

What to try:
- Re-run after a short delay (rate limits typically reset within a minute).
- Check https://status.adobe.com for AA availability.""",
    ExitCode.NOT_FOUND: """The requested report suite (or related resource) does not exist.

Likely causes:
- Typo in the RSID.
- The report suite is in a different org than the credentials authorize.
- Name lookup matched zero suites (case-insensitive exact match).

What to try:
- Run `aa_auto_sdr --list-reportsuites` to see every visible RS.""",
    ExitCode.PARTIAL_SUCCESS: """A `--batch` run completed with at least one success and at least
one failure. The batch did not abort — failures are continue-on-error.

Likely causes:
- A subset of RSIDs was unreachable (rate limit, transient API error).
- One identifier was a typo or referred to a different org.

What to try:
- Inspect the BATCH PROCESSING SUMMARY for which RSes failed and why.
- Re-run just the failed RSes after addressing the root cause.""",
    ExitCode.OUTPUT: """An output writer or destination check failed.

Likely causes:
- `--output -` combined with a multi-format request (`--format all`,
  `--format excel`, etc.).
- `--output -` combined with `--batch` (multiple SDRs cannot share one stream).
- `--diff --format console --output -` (console diff is for humans, not pipes).
- `--list-snapshots` or `--profile-list` with a format value other than
  `json|table`.
- Filesystem write failure (permissions, disk full).

What to try:
- For piping, use `--format json` (single SDR) or `--format json|markdown`
  (diff). Use `--output-dir` for multi-format and batch.
- For `--list-snapshots` / `--profile-list`, use `--format json` or `--format table`.""",
    ExitCode.SNAPSHOT: """A snapshot could not be resolved, parsed, or read from git.

Likely causes:
- Snapshot file path doesn't exist (or is a directory).
- Snapshot envelope schema is missing/wrong (not `aa-sdr-snapshot/v1`).
- `<RSID>@<spec>` token used without `--profile`.
- `git:<ref>:<path>` ref or path doesn't exist in the current repo.

What to try:
- Verify the path with `ls`.
- For `<RSID>@latest` / `@previous`, ensure `--profile` is set and the profile's
  `~/.aa/orgs/<profile>/snapshots/<RSID>/` directory has at least one (or two,
  for `@previous`) JSON files.""",
}
