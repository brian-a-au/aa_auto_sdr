"""--interactive handler: list visible report suites, prompt for selection,
emit chosen RSID(s) to stdout space-separated for shell composition.

The numbered list is printed to stderr so stdout is reserved for the chosen
RSID(s) — that lets users pipe / capture cleanly:

    RSIDS=$(aa_auto_sdr --interactive --profile prod) && aa_auto_sdr $RSIDS
"""

from __future__ import annotations

import sys

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core import credentials
from aa_auto_sdr.core.exceptions import ApiError, AuthError, ConfigError
from aa_auto_sdr.core.exit_codes import ExitCode


def run(*, profile: str | None) -> int:
    """List RSes, prompt for index (or 'all'), print chosen RSID(s) to stdout."""
    try:
        creds = credentials.resolve(profile=profile)
    except ConfigError as exc:
        print(f"error: {exc}", flush=True)
        return ExitCode.CONFIG.value

    try:
        client = AaClient.from_credentials(creds)
    except AuthError as exc:
        print(f"auth error: {exc}", flush=True)
        return ExitCode.AUTH.value

    try:
        records = fetch._records(client.handle.getReportSuites(extended_info=True))
    except ApiError as exc:
        print(f"api error: {exc}", flush=True)
        return ExitCode.API.value

    if not records:
        print("(no report suites visible)", flush=True)
        return ExitCode.NOT_FOUND.value

    # Print numbered list to stderr so stdout is reserved for the chosen RSID.
    print("Visible report suites:", file=sys.stderr)
    for i, rec in enumerate(records, start=1):
        rsid = rec.get("rsid", "")
        name = rec.get("name", "")
        print(f"  [{i}] {rsid}  —  {name}", file=sys.stderr)

    try:
        choice = input("Select index (1-N) or 'all': ").strip().lower()
    except KeyboardInterrupt, EOFError:
        return 130

    if choice == "all":
        chosen = [rec.get("rsid", "") for rec in records if rec.get("rsid")]
    else:
        try:
            idx = int(choice)
            if idx < 1 or idx > len(records):
                raise ValueError
        except ValueError:
            print(
                f"error: invalid selection '{choice}'; expected 1-{len(records)} or 'all'",
                flush=True,
            )
            return ExitCode.USAGE.value
        chosen = [records[idx - 1].get("rsid", "")]

    sys.stdout.write(" ".join(chosen) + "\n")
    sys.stdout.flush()
    return ExitCode.OK.value
