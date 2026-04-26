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

What to try:
- Run `aa_auto_sdr --help` to see the full surface.
- Run `aa_auto_sdr --exit-codes` for the full code list.""",
    ExitCode.CONFIG: """Configuration is missing or incomplete.

Likely causes:
- Required env vars unset (`ORG_ID`, `CLIENT_ID`, `SECRET`, `SCOPES`).
- `--snapshot` used without `--profile`.
- `--profile NAME` referenced but no profile file at `~/.aa/orgs/NAME/`.

What to try:
- Run `aa_auto_sdr --show-config` to see which credentials source resolved.
- Run `aa_auto_sdr --profile-add NAME` to create a profile interactively.""",
    ExitCode.AUTH: """OAuth Server-to-Server authentication failed.

Likely causes:
- Bad client_id / secret combination.
- Scopes missing `additional_info.job_function` (Adobe rejects reads silently
  without it).
- Integration not added to an Adobe Analytics Product Profile in Admin Console.

What to try:
- Verify credentials in Adobe Developer Console (https://developer.adobe.com/console).
- Confirm SCOPES contains `openid AdobeID read_organizations
  additional_info.projectedProductContext additional_info.job_function`.""",
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
- Filesystem write failure (permissions, disk full).

What to try:
- For piping, use `--format json` (single SDR) or `--format json|markdown`
  (diff). Use `--output-dir` for multi-format and batch.""",
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
