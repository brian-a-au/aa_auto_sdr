"""--interactive handler: list visible report suites, prompt for selection,
emit chosen RSID(s) to stdout space-separated for shell composition.

The numbered list is printed to stderr so stdout is reserved for the chosen
RSID(s) — that lets users pipe / capture cleanly:

    RSIDS=$(aa_auto_sdr --interactive --profile prod) && aa_auto_sdr $RSIDS
"""

from __future__ import annotations

import logging
import sys
import time

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core import credentials
from aa_auto_sdr.core.exceptions import ApiError, AuthError, ConfigError
from aa_auto_sdr.core.exit_codes import ExitCode

logger = logging.getLogger(__name__)


def run(*, profile: str | None) -> int:
    """List RSes, prompt for index (or 'all'), print chosen RSID(s) to stdout."""
    started_ms = time.monotonic()
    logger.info("command_start command=interactive", extra={"command": "interactive"})
    exit_code = ExitCode.GENERIC.value
    try:
        try:
            creds = credentials.resolve(profile=profile)
        except ConfigError as exc:
            print(f"error: {exc}", flush=True)
            exit_code = ExitCode.CONFIG.value
            return exit_code

        try:
            client = AaClient.from_credentials(creds)
        except AuthError as exc:
            print(f"auth error: {exc}", flush=True)
            exit_code = ExitCode.AUTH.value
            return exit_code

        try:
            summaries = fetch.fetch_report_suite_summaries(client)
        except ApiError as exc:
            print(f"api error: {exc}", flush=True)
            exit_code = ExitCode.API.value
            return exit_code

        if not summaries:
            print("(no report suites visible)", flush=True)
            exit_code = ExitCode.NOT_FOUND.value
            return exit_code

        # Print numbered list to stderr so stdout is reserved for the chosen RSID.
        print("Visible report suites:", file=sys.stderr)
        for i, s in enumerate(summaries, start=1):
            print(f"  [{i}] {s.rsid}  —  {s.name or ''}", file=sys.stderr)

        try:
            choice = input("Select index (1-N) or 'all': ").strip().lower()
        except KeyboardInterrupt:
            exit_code = 130
            return exit_code
        except EOFError:
            exit_code = 130
            return exit_code

        if choice == "all":
            chosen = [s.rsid for s in summaries]
        else:
            try:
                idx = int(choice)
                if idx < 1 or idx > len(summaries):
                    raise ValueError
            except ValueError:
                print(
                    f"error: invalid selection '{choice}'; expected 1-{len(summaries)} or 'all'",
                    flush=True,
                )
                exit_code = ExitCode.USAGE.value
                return exit_code
            chosen = [summaries[idx - 1].rsid]

        sys.stdout.write(" ".join(chosen) + "\n")
        sys.stdout.flush()
        exit_code = ExitCode.OK.value
        return exit_code
    finally:
        duration_ms = int((time.monotonic() - started_ms) * 1000)
        logger.info(
            "command_complete command=interactive exit_code=%s duration_ms=%s",
            exit_code,
            duration_ms,
            extra={
                "command": "interactive",
                "exit_code": exit_code,
                "duration_ms": duration_ms,
            },
        )
