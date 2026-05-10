"""Duration-string parsing (`Nh|Nd|Nw`) shared by retention and trending.

Months and years are deliberately NOT supported — calendar arithmetic is
ambiguous (do 30 days approximate a month?). Users wanting a quarterly
window should pass `90d`.
"""

from __future__ import annotations

import re
from datetime import timedelta

_DURATION_RE = re.compile(r"^(\d+)([hdw])$")
_UNIT_TO_HOURS = {"h": 1, "d": 24, "w": 24 * 7}


def parse_duration(spec: str) -> timedelta:
    """Parse `Nh`, `Nd`, or `Nw` into a timedelta.

    Raises ValueError on malformed input. The error message names the
    expected grammar so CLI handlers can surface it directly.
    """
    match = _DURATION_RE.fullmatch(spec)
    if match is None:
        raise ValueError(
            f"invalid duration: {spec!r} (expected format Nh|Nd|Nw, e.g. '30d')",
        )
    n_str, unit = match.groups()
    return timedelta(hours=int(n_str) * _UNIT_TO_HOURS[unit])
