"""Cross-platform 'open file in default app' helper.

Best-effort: silently ignore failure (headless, no display, etc.). Tests mock
subprocess.run rather than relying on actual shell invocation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def os_open(path: Path) -> None:
    """Open `path` in the OS default app. Best-effort: silently ignore failure."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        elif sys.platform == "win32":
            subprocess.run(
                ["cmd", "/c", "start", "", str(path)],
                check=False,
                shell=False,
            )
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except OSError:
        # Best-effort: don't crash the run if the user has no display.
        pass
