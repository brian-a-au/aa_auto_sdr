# aa_auto_sdr v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the v0.1 cut of `aa_auto_sdr` — a CLI that authenticates against Adobe Analytics via OAuth Server-to-Server (API 2.0 only), fetches one report suite's components, and emits a Solution Design Reference document as both Excel and JSON. v0.1 is the proving ground for the full architecture: SDK isolation, normalized models, builder purity, writer protocol, and credential resolution.

**Architecture:** Strict layered design — `api/` isolates the `aanalytics2` SDK and produces normalized dataclasses; `sdr/builder.py` is pure (models in, `SdrDocument` out, no I/O); `output/writers/` registers per-format writers behind a `Writer` protocol; `pipeline/single.py` orchestrates the three. The CLI lives in `cli/`, with a fast-path `__main__.py` that handles `--version`/`--help` without importing heavy deps. v0.1 ships only JSON + Excel writers and only the single-RSID code path; everything else is stubbed out for later milestones.

**Tech Stack:** Python 3.14, `uv`, `hatchling`, `pytest`/`pytest-cov`, `ruff`, `aanalytics2`, `pandas`, `xlsxwriter`. OAuth S2S auth (no JWT). API 2.0 only.

**Reference docs:**
- Design spec: `docs/superpowers/specs/2026-04-25-aa-auto-sdr-v1-design.md` — read sections 0–6 before starting
- Project notes: `CLAUDE.md` (repo root)

---

## File Structure for v0.1

| File | Responsibility |
|------|----------------|
| `pyproject.toml` | Project metadata, deps, build backend, ruff/pytest config |
| `src/aa_auto_sdr/__init__.py` | Lazy `__version__` and `main` re-exports |
| `src/aa_auto_sdr/__main__.py` | Fast-path entry point (handles `--version`/`--help` cheaply, then delegates) |
| `src/aa_auto_sdr/core/version.py` | `__version__` — single source of truth |
| `src/aa_auto_sdr/core/exceptions.py` | Typed exception hierarchy |
| `src/aa_auto_sdr/core/json_io.py` | Atomic JSON read/write helpers |
| `src/aa_auto_sdr/core/credentials.py` | `Credentials` dataclass + 4-source resolution chain |
| `src/aa_auto_sdr/core/profiles.py` | Profile CRUD under `~/.aa/orgs/<name>/` |
| `src/aa_auto_sdr/api/auth.py` | OAuth S2S setup; converts `Credentials` → authenticated client |
| `src/aa_auto_sdr/api/client.py` | Wraps `aanalytics2.Analytics`; only file (besides `auth.py` and `fetch.py`) that imports the SDK |
| `src/aa_auto_sdr/api/models.py` | Normalized dataclasses: `ReportSuite`, `Dimension`, `Metric`, `Segment`, `CalculatedMetric`, `VirtualReportSuite`, `Classification` |
| `src/aa_auto_sdr/api/fetch.py` | Per-component fetchers — return normalized models |
| `src/aa_auto_sdr/sdr/document.py` | `SdrDocument` dataclass — the boundary type |
| `src/aa_auto_sdr/sdr/builder.py` | Pure builder: normalized models → `SdrDocument` |
| `src/aa_auto_sdr/output/protocols.py` | `Writer` protocol |
| `src/aa_auto_sdr/output/registry.py` | Format → Writer registry; aliases |
| `src/aa_auto_sdr/output/writers/json.py` | JSON writer (self-registers on import) |
| `src/aa_auto_sdr/output/writers/excel.py` | Multi-sheet Excel workbook (self-registers on import) |
| `src/aa_auto_sdr/pipeline/single.py` | Single-RSID orchestration |
| `src/aa_auto_sdr/pipeline/models.py` | `RunResult` |
| `src/aa_auto_sdr/cli/parser.py` | Argparse setup (v0.1 surface only) |
| `src/aa_auto_sdr/cli/main.py` | Dispatcher |
| `src/aa_auto_sdr/cli/commands/generate.py` | `<RSID>` command handler |
| `src/aa_auto_sdr/cli/commands/config.py` | `--profile-add`, `--profile`, `--show-config` handlers |
| `tests/conftest.py` | Pytest fixtures, auto-marker classification |
| `tests/fixtures/sample_rs.json` | Realistic mocked-AA response corpus |
| `README.md` | Install + auth + first run |
| `CHANGELOG.md` | Keep-a-Changelog header + v0.1 entry |
| `.gitignore` | Python defaults + `.env`, `config.json`, `dist/`, `.venv/` |
| `.env.example` | Documented OAuth env vars |
| `LICENSE` | MIT |

---

## Phase 1 — Project skeleton

### Task 1: Create `pyproject.toml`

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Write the file**

```toml
[project]
name = "aa-auto-sdr"
dynamic = ["version"]
description = "Adobe Analytics SDR Generator with snapshot diffing (API 2.0 only)"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.14"
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.14",
    "Topic :: Software Development :: Documentation",
]
dependencies = [
    "aanalytics2>=0.4.0",
    "pandas>=2.3.3,<3",
    "xlsxwriter>=3.2.9",
]

[project.urls]
Homepage = "https://github.com/brian-a-au/aa_auto_sdr"
Repository = "https://github.com/brian-a-au/aa_auto_sdr"

[project.scripts]
aa_auto_sdr = "aa_auto_sdr.__main__:main"
"aa-auto-sdr" = "aa_auto_sdr.__main__:main"

[project.optional-dependencies]
env = ["python-dotenv>=1.0.0"]
completion = ["argcomplete>=3.0.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.version]
path = "src/aa_auto_sdr/core/version.py"

[tool.hatch.build.targets.wheel]
packages = ["src/aa_auto_sdr"]

[tool.hatch.build.targets.sdist]
include = ["/src", "pyproject.toml", "README.md", "LICENSE"]

[dependency-groups]
dev = [
    "pytest>=9.0.3",
    "pytest-cov>=4.1.0",
    "openpyxl>=3.1.0",
    "ruff>=0.9.0",
]

[tool.ruff]
target-version = "py314"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --cov=aa_auto_sdr --cov-report=term-missing --cov-fail-under=70"
markers = [
    "unit: fast unit tests with no I/O",
    "integration: end-to-end with mocked SDK",
    "smoke: subprocess CLI smoke tests",
    "e2e: real-API tests, gated by env var",
]
```

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "feat: initialize project metadata and toolchain"
```

### Task 2: Create `.gitignore`, `LICENSE`, `.env.example`

**Files:**
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `.env.example`

- [ ] **Step 1: Write `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
dist/
*.egg-info/
.eggs/
*.egg

# Virtual envs
.venv/
venv/
env/

# Test / coverage
.pytest_cache/
.coverage
.coverage.*
htmlcov/
.tox/

# Editor
.vscode/
.idea/
*.swp
.DS_Store

# Project secrets — never commit
.env
.env.local
config.json

# Build artifacts
*.xlsx
*.csv
!tests/fixtures/**/*.csv
!tests/fixtures/**/*.xlsx
```

- [ ] **Step 2: Write `LICENSE`** (MIT)

```text
MIT License

Copyright (c) 2026 Brian Au

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: Write `.env.example`**

```bash
# aa_auto_sdr — Environment Variables
# Copy to .env and fill in. Requires `uv add python-dotenv` for .env loading.

# Adobe OAuth Server-to-Server (Required)
ORG_ID=your_org_id@AdobeOrg
CLIENT_ID=your_client_id
SECRET=your_client_secret
SCOPES=your_scopes_from_developer_console

# Optional
# SANDBOX=your_sandbox_name
# LOG_LEVEL=INFO

# Default profile (overrides --profile)
# AA_PROFILE=production
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore LICENSE .env.example
git commit -m "feat: add gitignore, license, env example"
```

### Task 3: Create empty package skeleton

**Files:**
- Create: `src/aa_auto_sdr/__init__.py`
- Create: `src/aa_auto_sdr/core/__init__.py`
- Create: `src/aa_auto_sdr/core/version.py`
- Create: `src/aa_auto_sdr/api/__init__.py`
- Create: `src/aa_auto_sdr/sdr/__init__.py`
- Create: `src/aa_auto_sdr/output/__init__.py`
- Create: `src/aa_auto_sdr/output/writers/__init__.py`
- Create: `src/aa_auto_sdr/pipeline/__init__.py`
- Create: `src/aa_auto_sdr/cli/__init__.py`
- Create: `src/aa_auto_sdr/cli/commands/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `core/version.py`**

```python
"""Single source of truth for the package version."""

__version__ = "0.1.0"
```

- [ ] **Step 2: Create top-level `__init__.py` with lazy forwarding**

```python
"""aa_auto_sdr — Adobe Analytics SDR generator (API 2.0 only)."""

from aa_auto_sdr.core.version import __version__

__all__ = ["__version__", "main"]


def __getattr__(name: str):
    if name == "main":
        from aa_auto_sdr.__main__ import main as _main

        return _main
    raise AttributeError(f"module 'aa_auto_sdr' has no attribute {name!r}")
```

- [ ] **Step 3: Create empty subpackage `__init__.py` files**

Each of `core/__init__.py`, `api/__init__.py`, `sdr/__init__.py`, `output/__init__.py`, `output/writers/__init__.py`, `pipeline/__init__.py`, `cli/__init__.py`, `cli/commands/__init__.py`:

```python
"""Subpackage stub — populated in later tasks."""
```

- [ ] **Step 4: Create `tests/__init__.py` (empty) and `tests/conftest.py`**

`tests/__init__.py`:

```python
```

`tests/conftest.py`:

```python
"""Pytest fixtures and auto-marker classification."""
import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-apply `unit` marker to anything not otherwise marked."""
    other_markers = {"integration", "smoke", "e2e"}
    for item in items:
        if not any(m.name in other_markers for m in item.iter_markers()):
            item.add_marker(pytest.mark.unit)
```

- [ ] **Step 5: Run `uv sync` to install**

Run: `uv sync --all-extras`
Expected: dependency resolution succeeds; `.venv` populated.

- [ ] **Step 6: Commit**

```bash
git add src/ tests/__init__.py tests/conftest.py
git commit -m "feat: scaffold package skeleton with lazy forwarding"
```

### Task 4: Add a smoke test for `__version__` (anchors test infra)

**Files:**
- Create: `tests/test_version.py`

- [ ] **Step 1: Write the failing test**

```python
"""Verify version is exposed and follows expected format."""
import re

import aa_auto_sdr


def test_version_is_exposed() -> None:
    assert hasattr(aa_auto_sdr, "__version__")


def test_version_matches_semver_dev() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[ab]\d+|rc\d+)?", aa_auto_sdr.__version__)


def test_version_is_0_1_0() -> None:
    assert aa_auto_sdr.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/test_version.py -v`
Expected: 3 passing.

- [ ] **Step 3: Commit**

```bash
git add tests/test_version.py
git commit -m "test: pin version exposure and format"
```

### Task 5: Wire fast-path entry point

**Files:**
- Create: `src/aa_auto_sdr/__main__.py`
- Create: `tests/test_main_fastpath.py`

- [ ] **Step 1: Write failing tests**

```python
"""Fast-path entry tests — must complete without importing pandas/aanalytics2."""
import subprocess
import sys


def test_version_flag_short() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "-V"],
        capture_output=True, text=True, check=True,
    )
    assert "0.1.0" in result.stdout


def test_version_flag_long() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--version"],
        capture_output=True, text=True, check=True,
    )
    assert "0.1.0" in result.stdout


def test_help_flag_does_not_import_aanalytics2() -> None:
    result = subprocess.run(
        [sys.executable, "-X", "importtime", "-m", "aa_auto_sdr", "--help"],
        capture_output=True, text=True, check=True,
    )
    assert "aanalytics2" not in result.stderr
    assert "pandas" not in result.stderr
```

- [ ] **Step 2: Run tests, expect failure**

Run: `uv run pytest tests/test_main_fastpath.py -v`
Expected: FAIL with `ModuleNotFoundError` or non-zero exit.

- [ ] **Step 3: Implement `__main__.py`**

```python
"""Fast-path entry point. Handles --version/--help/--exit-codes/--completion
without importing any heavy dependency. Delegates everything else to cli.main."""
from __future__ import annotations

import sys

from aa_auto_sdr.core.version import __version__

_FASTPATH_VERSION = {"-V", "--version"}
_FASTPATH_HELP = {"-h", "--help"}


def _print_version() -> int:
    print(f"aa_auto_sdr {__version__}")
    return 0


def _print_help() -> int:
    print(
        "aa_auto_sdr — Adobe Analytics SDR Generator (API 2.0 only)\n"
        "\n"
        "Usage:\n"
        "  aa_auto_sdr <RSID>                   Generate SDR for one report suite\n"
        "  aa_auto_sdr --profile-add <name>     Create a credentials profile\n"
        "  aa_auto_sdr --profile <name> ...     Use a named profile\n"
        "  aa_auto_sdr --show-config            Show resolved credentials source\n"
        "  aa_auto_sdr -V | --version           Print version\n"
        "  aa_auto_sdr -h | --help              Print this help\n"
        "\n"
        "v0.1: only single-RSID generation, JSON + Excel outputs, profile auth.\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in _FASTPATH_VERSION:
        return _print_version()
    if args and args[0] in _FASTPATH_HELP:
        return _print_help()
    from aa_auto_sdr.cli.main import run

    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Stub `cli/main.py` so help/version work before CLI is built**

Create `src/aa_auto_sdr/cli/main.py`:

```python
"""CLI dispatcher — populated incrementally."""
from __future__ import annotations


def run(argv: list[str]) -> int:
    print("error: full CLI not yet implemented in this build", flush=True)
    return 2
```

- [ ] **Step 5: Run tests, expect pass**

Run: `uv run pytest tests/test_main_fastpath.py -v`
Expected: 3 passing.

- [ ] **Step 6: Commit**

```bash
git add src/aa_auto_sdr/__main__.py src/aa_auto_sdr/cli/main.py tests/test_main_fastpath.py
git commit -m "feat: fast-path entry point with --version/--help"
```

### Task 6: Verify lint+test infrastructure end-to-end

- [ ] **Step 1: Run ruff**

Run: `uv run ruff check src/ tests/`
Expected: clean (no issues).

- [ ] **Step 2: Run ruff format check**

Run: `uv run ruff format --check src/ tests/`
Expected: clean.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest`
Expected: all passing; coverage report shown. (Coverage may be below 70% gate at this point — that is acceptable until later tasks add code.)

- [ ] **Step 4: If coverage gate trips, lower temporarily in `pyproject.toml`**

Set `--cov-fail-under=0` for now. Re-raise to 70 in Task 33.

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "chore: scaffolding lint/test green"
```

---

## Phase 2 — Core utilities

### Task 7: Typed exception hierarchy

**Files:**
- Create: `src/aa_auto_sdr/core/exceptions.py`
- Create: `tests/core/__init__.py`
- Create: `tests/core/test_exceptions.py`

- [ ] **Step 1: Write failing tests**

`tests/core/__init__.py`: empty file.

`tests/core/test_exceptions.py`:

```python
"""Verify the exception hierarchy is shaped as the design spec requires."""
import pytest

from aa_auto_sdr.core import exceptions as exc


def test_base_class_is_aaautosdrerror() -> None:
    assert issubclass(exc.AaAutoSdrError, Exception)


@pytest.mark.parametrize(
    "child",
    [
        exc.ConfigError,
        exc.AuthError,
        exc.ApiError,
        exc.ReportSuiteNotFoundError,
        exc.SnapshotError,
        exc.OutputError,
    ],
)
def test_top_level_children_inherit_base(child: type[Exception]) -> None:
    assert issubclass(child, exc.AaAutoSdrError)


def test_unsupported_by_api20_is_apierror() -> None:
    assert issubclass(exc.UnsupportedByApi20, exc.ApiError)


@pytest.mark.parametrize(
    "child",
    [exc.SnapshotResolveError, exc.SnapshotSchemaError],
)
def test_snapshot_children_inherit_snapshoterror(child: type[Exception]) -> None:
    assert issubclass(child, exc.SnapshotError)
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/core/test_exceptions.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement `core/exceptions.py`**

```python
"""Typed exception hierarchy. See design spec §6."""


class AaAutoSdrError(Exception):
    """Base class for all aa_auto_sdr errors."""


class ConfigError(AaAutoSdrError):
    """Bad config or missing credentials."""


class AuthError(AaAutoSdrError):
    """OAuth Server-to-Server failure."""


class ApiError(AaAutoSdrError):
    """Network or API-level error."""


class UnsupportedByApi20(ApiError):
    """Raised when a feature is only available in the legacy 1.4 API.

    The 1.4 API is explicitly out of scope; surface this rather than degrading.
    """


class ReportSuiteNotFoundError(AaAutoSdrError):
    """The requested RSID does not exist in this org."""


class SnapshotError(AaAutoSdrError):
    """Base for snapshot-related errors."""


class SnapshotResolveError(SnapshotError):
    """A snapshot identifier (path, RSID@ts, git ref) could not be resolved."""


class SnapshotSchemaError(SnapshotError):
    """A snapshot file's schema is unknown or unsupported."""


class OutputError(AaAutoSdrError):
    """An output writer failed (I/O, formatting, etc.)."""
```

- [ ] **Step 4: Run tests, expect pass**

Run: `uv run pytest tests/core/test_exceptions.py -v`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add src/aa_auto_sdr/core/exceptions.py tests/core/
git commit -m "feat(core): typed exception hierarchy"
```

### Task 8: Atomic JSON I/O helpers

**Files:**
- Create: `src/aa_auto_sdr/core/json_io.py`
- Create: `tests/core/test_json_io.py`

- [ ] **Step 1: Write failing tests**

```python
"""Atomic JSON reader/writer helpers."""
import json
from pathlib import Path

import pytest

from aa_auto_sdr.core import json_io


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    payload = {"a": 1, "b": [2, 3], "c": {"d": "x"}}
    target = tmp_path / "out.json"
    json_io.write_json(target, payload)
    assert json_io.read_json(target) == payload


def test_write_is_atomic_via_tmp_then_rename(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    json_io.write_json(target, {"x": 1})
    assert target.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_write_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "out.json"
    json_io.write_json(target, {"x": 1})
    assert target.exists()


def test_write_sorts_keys_for_diff_friendliness(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    json_io.write_json(target, {"b": 2, "a": 1, "c": 3})
    text = target.read_text()
    assert text.index('"a"') < text.index('"b"') < text.index('"c"')


def test_read_missing_raises_filenotfounderror(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        json_io.read_json(tmp_path / "missing.json")


def test_read_invalid_json_raises_jsondecodeerror(tmp_path: Path) -> None:
    target = tmp_path / "bad.json"
    target.write_text("not json")
    with pytest.raises(json.JSONDecodeError):
        json_io.read_json(target)
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/core/test_json_io.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `core/json_io.py`**

```python
"""Atomic JSON I/O. Writes go through a temp file + rename to avoid torn writes."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    """Read and parse a JSON file. Raises FileNotFoundError or json.JSONDecodeError."""
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Any, *, indent: int = 2) -> None:
    """Write a JSON payload atomically. Creates parent dirs as needed.

    Keys are sorted so that snapshot files diff cleanly across captures.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=indent, sort_keys=True, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/core/test_json_io.py -v`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add src/aa_auto_sdr/core/json_io.py tests/core/test_json_io.py
git commit -m "feat(core): atomic JSON I/O helpers"
```

### Task 9: `Credentials` dataclass

**Files:**
- Create: `src/aa_auto_sdr/core/credentials.py` (initial — type only; resolution chain in next task)
- Create: `tests/core/test_credentials_type.py`

- [ ] **Step 1: Write failing tests**

```python
"""Credentials dataclass tests."""
import pytest

from aa_auto_sdr.core.credentials import Credentials
from aa_auto_sdr.core.exceptions import ConfigError


def test_credentials_holds_required_fields() -> None:
    c = Credentials(org_id="O", client_id="C", secret="S", scopes="X", sandbox=None, source="env")
    assert c.org_id == "O"
    assert c.client_id == "C"
    assert c.secret == "S"
    assert c.scopes == "X"
    assert c.sandbox is None
    assert c.source == "env"


def test_credentials_is_frozen() -> None:
    c = Credentials(org_id="O", client_id="C", secret="S", scopes="X", sandbox=None, source="env")
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError
        c.org_id = "Q"  # type: ignore[misc]


def test_validate_raises_when_required_missing() -> None:
    with pytest.raises(ConfigError) as exc_info:
        Credentials(org_id="", client_id="C", secret="S", scopes="X", sandbox=None, source="env").validate()
    assert "org_id" in str(exc_info.value)


def test_validate_passes_when_all_required_present() -> None:
    Credentials(org_id="O", client_id="C", secret="S", scopes="X", sandbox=None, source="env").validate()


def test_validate_treats_whitespace_as_empty() -> None:
    with pytest.raises(ConfigError):
        Credentials(org_id="   ", client_id="C", secret="S", scopes="X", sandbox=None, source="env").validate()
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/core/test_credentials_type.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement minimal `core/credentials.py`**

```python
"""OAuth Server-to-Server credentials and resolution.

Resolution chain (highest precedence first) is implemented in `resolve()` —
see Task 10.
"""
from __future__ import annotations

from dataclasses import dataclass

from aa_auto_sdr.core.exceptions import ConfigError

_REQUIRED_FIELDS = ("org_id", "client_id", "secret", "scopes")


@dataclass(frozen=True, slots=True)
class Credentials:
    """OAuth S2S credentials plus diagnostic source label."""

    org_id: str
    client_id: str
    secret: str
    scopes: str
    sandbox: str | None
    source: str  # 'profile:<name>' | 'env' | '.env' | 'config.json'

    def validate(self) -> None:
        """Raise ConfigError if any required field is missing or whitespace-only."""
        missing = [f for f in _REQUIRED_FIELDS if not getattr(self, f).strip()]
        if missing:
            raise ConfigError(
                f"Missing required credential fields: {', '.join(missing)} "
                f"(loaded from {self.source})"
            )
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/core/test_credentials_type.py -v`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add src/aa_auto_sdr/core/credentials.py tests/core/test_credentials_type.py
git commit -m "feat(core): Credentials dataclass"
```

### Task 10: Credential resolution chain (4 sources)

**Files:**
- Modify: `src/aa_auto_sdr/core/credentials.py`
- Create: `src/aa_auto_sdr/core/profiles.py`
- Create: `tests/core/test_credentials_resolve.py`
- Create: `tests/core/test_profiles.py`

- [ ] **Step 1: Write failing test for `profiles.read_profile`**

`tests/core/test_profiles.py`:

```python
"""Profile CRUD tests. ~/.aa/orgs/<name>/config.json layout."""
import json
from pathlib import Path

import pytest

from aa_auto_sdr.core import profiles
from aa_auto_sdr.core.exceptions import ConfigError


def test_read_profile_returns_dict_when_present(tmp_path: Path) -> None:
    profile_dir = tmp_path / "orgs" / "test"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.json").write_text(json.dumps({
        "org_id": "O", "client_id": "C", "secret": "S", "scopes": "X",
    }))
    result = profiles.read_profile("test", base=tmp_path)
    assert result["org_id"] == "O"


def test_read_profile_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as exc_info:
        profiles.read_profile("missing", base=tmp_path)
    assert "missing" in str(exc_info.value)


def test_write_profile_creates_dir_and_file(tmp_path: Path) -> None:
    profiles.write_profile("p", {"org_id": "O"}, base=tmp_path)
    assert (tmp_path / "orgs" / "p" / "config.json").exists()


def test_default_base_is_home_aa(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert profiles.default_base() == tmp_path / ".aa"


def test_list_profiles_returns_sorted_names(tmp_path: Path) -> None:
    for name in ("zeta", "alpha", "mid"):
        profiles.write_profile(name, {"org_id": "O"}, base=tmp_path)
    assert profiles.list_profiles(base=tmp_path) == ["alpha", "mid", "zeta"]


def test_list_profiles_empty_when_no_dir(tmp_path: Path) -> None:
    assert profiles.list_profiles(base=tmp_path) == []
```

- [ ] **Step 2: Implement `core/profiles.py`**

```python
"""Profile CRUD under <base>/orgs/<name>/config.json."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from aa_auto_sdr.core.exceptions import ConfigError
from aa_auto_sdr.core.json_io import write_json


def default_base() -> Path:
    """Default profile root: ~/.aa/"""
    return Path(os.environ.get("HOME", "~")).expanduser() / ".aa"


def _profile_dir(name: str, base: Path | None) -> Path:
    return (base or default_base()) / "orgs" / name


def read_profile(name: str, *, base: Path | None = None) -> dict[str, Any]:
    """Read a profile's config.json. Raises ConfigError if missing."""
    path = _profile_dir(name, base) / "config.json"
    if not path.exists():
        raise ConfigError(f"Profile '{name}' not found at {path}")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def write_profile(name: str, data: dict[str, Any], *, base: Path | None = None) -> Path:
    """Write a profile's config.json (overwrites). Returns the file path."""
    path = _profile_dir(name, base) / "config.json"
    write_json(path, data)
    return path


def list_profiles(*, base: Path | None = None) -> list[str]:
    """List profile names in sorted order."""
    root = (base or default_base()) / "orgs"
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())
```

- [ ] **Step 3: Run profile tests**

Run: `uv run pytest tests/core/test_profiles.py -v`
Expected: all passing.

- [ ] **Step 4: Write failing tests for credential resolution chain**

`tests/core/test_credentials_resolve.py`:

```python
"""Credential resolution precedence: profile > env > .env > config.json."""
import json
from pathlib import Path

import pytest

from aa_auto_sdr.core import credentials
from aa_auto_sdr.core.exceptions import ConfigError


def _write_profile(base: Path, name: str, data: dict) -> None:
    p = base / "orgs" / name
    p.mkdir(parents=True)
    (p / "config.json").write_text(json.dumps(data))


def test_profile_wins_over_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_profile(tmp_path, "prod", {
        "org_id": "P", "client_id": "Pc", "secret": "Ps", "scopes": "Px",
    })
    monkeypatch.setenv("ORG_ID", "E")
    monkeypatch.setenv("CLIENT_ID", "Ec")
    monkeypatch.setenv("SECRET", "Es")
    monkeypatch.setenv("SCOPES", "Ex")

    creds = credentials.resolve(profile="prod", profiles_base=tmp_path, working_dir=tmp_path)
    assert creds.org_id == "P"
    assert creds.source == "profile:prod"


def test_env_wins_over_config_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ORG_ID", "E")
    monkeypatch.setenv("CLIENT_ID", "Ec")
    monkeypatch.setenv("SECRET", "Es")
    monkeypatch.setenv("SCOPES", "Ex")
    (tmp_path / "config.json").write_text(json.dumps({
        "org_id": "F", "client_id": "Fc", "secret": "Fs", "scopes": "Fx",
    }))
    creds = credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)
    assert creds.org_id == "E"
    assert creds.source == "env"


def test_config_json_wins_when_nothing_else(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(json.dumps({
        "org_id": "F", "client_id": "Fc", "secret": "Fs", "scopes": "Fx",
    }))
    creds = credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)
    assert creds.org_id == "F"
    assert creds.source == "config.json"


def test_aa_profile_env_var_picks_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_profile(tmp_path, "envdefault", {
        "org_id": "P", "client_id": "Pc", "secret": "Ps", "scopes": "Px",
    })
    monkeypatch.setenv("AA_PROFILE", "envdefault")
    creds = credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)
    assert creds.source == "profile:envdefault"


def test_explicit_profile_overrides_aa_profile_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_profile(tmp_path, "explicit", {
        "org_id": "X", "client_id": "Xc", "secret": "Xs", "scopes": "Xx",
    })
    _write_profile(tmp_path, "envdefault", {
        "org_id": "Y", "client_id": "Yc", "secret": "Ys", "scopes": "Yx",
    })
    monkeypatch.setenv("AA_PROFILE", "envdefault")
    creds = credentials.resolve(profile="explicit", profiles_base=tmp_path, working_dir=tmp_path)
    assert creds.source == "profile:explicit"
    assert creds.org_id == "X"


def test_resolve_raises_when_no_source_provides_creds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for var in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ConfigError):
        credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)


def test_sandbox_propagates_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ORG_ID", "E")
    monkeypatch.setenv("CLIENT_ID", "Ec")
    monkeypatch.setenv("SECRET", "Es")
    monkeypatch.setenv("SCOPES", "Ex")
    monkeypatch.setenv("SANDBOX", "dev1")
    creds = credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)
    assert creds.sandbox == "dev1"
```

- [ ] **Step 5: Run tests, expect failure**

Run: `uv run pytest tests/core/test_credentials_resolve.py -v`
Expected: FAIL — `credentials.resolve` does not exist.

- [ ] **Step 6: Implement resolution in `core/credentials.py`**

Append to `src/aa_auto_sdr/core/credentials.py`:

```python
import os
from pathlib import Path

from aa_auto_sdr.core import profiles


def _from_dict(d: dict, source: str) -> "Credentials":
    return Credentials(
        org_id=str(d.get("org_id", "")).strip(),
        client_id=str(d.get("client_id", "")).strip(),
        secret=str(d.get("secret", "")).strip(),
        scopes=str(d.get("scopes", "")).strip(),
        sandbox=(str(d["sandbox"]).strip() or None) if d.get("sandbox") else None,
        source=source,
    )


def _is_complete(c: "Credentials") -> bool:
    return all(getattr(c, f).strip() for f in ("org_id", "client_id", "secret", "scopes"))


def _from_env() -> "Credentials":
    return _from_dict(
        {
            "org_id": os.environ.get("ORG_ID", ""),
            "client_id": os.environ.get("CLIENT_ID", ""),
            "secret": os.environ.get("SECRET", ""),
            "scopes": os.environ.get("SCOPES", ""),
            "sandbox": os.environ.get("SANDBOX"),
        },
        source="env",
    )


def _from_dotenv(working_dir: Path) -> "Credentials | None":
    """Load .env via python-dotenv if installed; else return None."""
    try:
        from dotenv import dotenv_values  # type: ignore[import-not-found]
    except ImportError:
        return None
    path = working_dir / ".env"
    if not path.exists():
        return None
    values = dotenv_values(path)
    return _from_dict(values, source=".env")


def _from_config_json(working_dir: Path) -> "Credentials | None":
    path = working_dir / "config.json"
    if not path.exists():
        return None
    import json as _json

    with path.open(encoding="utf-8") as fh:
        data = _json.load(fh)
    return _from_dict(data, source="config.json")


def _from_profile(name: str, profiles_base: Path | None) -> "Credentials":
    data = profiles.read_profile(name, base=profiles_base)
    return _from_dict(data, source=f"profile:{name}")


def resolve(
    *,
    profile: str | None = None,
    profiles_base: Path | None = None,
    working_dir: Path | None = None,
) -> "Credentials":
    """Resolve credentials by precedence: profile > env > .env > config.json.

    `profiles_base` and `working_dir` are injection points for testability.
    """
    working_dir = working_dir or Path.cwd()
    chosen_profile = profile or os.environ.get("AA_PROFILE")

    if chosen_profile:
        creds = _from_profile(chosen_profile, profiles_base)
        creds.validate()
        return creds

    env_creds = _from_env()
    if _is_complete(env_creds):
        env_creds.validate()
        return env_creds

    dotenv_creds = _from_dotenv(working_dir)
    if dotenv_creds and _is_complete(dotenv_creds):
        dotenv_creds.validate()
        return dotenv_creds

    cfg_creds = _from_config_json(working_dir)
    if cfg_creds and _is_complete(cfg_creds):
        cfg_creds.validate()
        return cfg_creds

    raise ConfigError(
        "No credentials found. Set ORG_ID/CLIENT_ID/SECRET/SCOPES env vars, "
        "create a profile (--profile-add), or place a config.json in the working directory."
    )
```

- [ ] **Step 7: Run all credential/profile tests**

Run: `uv run pytest tests/core/ -v`
Expected: all passing.

- [ ] **Step 8: Commit**

```bash
git add src/aa_auto_sdr/core/credentials.py src/aa_auto_sdr/core/profiles.py tests/core/test_credentials_resolve.py tests/core/test_profiles.py
git commit -m "feat(core): credential resolution chain (profile > env > .env > config.json)"
```

---

## Phase 3 — API client and normalized models

### Task 11: Normalized component dataclasses

**Files:**
- Create: `src/aa_auto_sdr/api/models.py`
- Create: `tests/api/__init__.py`
- Create: `tests/api/test_models.py`

- [ ] **Step 1: Write failing tests**

`tests/api/__init__.py`: empty.

`tests/api/test_models.py`:

```python
"""Normalized SDK-agnostic component dataclasses."""
import pytest

from aa_auto_sdr.api import models


def test_reportsuite_holds_identity_and_metadata() -> None:
    rs = models.ReportSuite(rsid="abc.prod", name="Production", timezone="US/Pacific")
    assert rs.rsid == "abc.prod"
    assert rs.name == "Production"
    assert rs.timezone == "US/Pacific"


def test_dimension_minimal_construction() -> None:
    d = models.Dimension(id="evar1", name="User ID", type="string", description=None, extra={})
    assert d.id == "evar1"
    assert d.type == "string"


def test_metric_minimal_construction() -> None:
    m = models.Metric(id="metrics/pageviews", name="Page Views", type="int", description=None, extra={})
    assert m.id == "metrics/pageviews"


def test_segment_minimal_construction() -> None:
    s = models.Segment(id="s_123", name="Mobile", description=None, definition={"hits": "..."}, extra={})
    assert s.id == "s_123"
    assert s.definition == {"hits": "..."}


def test_calculated_metric_minimal_construction() -> None:
    cm = models.CalculatedMetric(
        id="cm_1", name="Conv Rate", description=None, formula={"func": "divide"}, extra={},
    )
    assert cm.id == "cm_1"


def test_virtual_report_suite_minimal_construction() -> None:
    vrs = models.VirtualReportSuite(
        id="vrs_1", name="EU Only", parent_rsid="parent.prod", segments=["s1"], extra={},
    )
    assert vrs.parent_rsid == "parent.prod"


def test_classification_minimal_construction() -> None:
    c = models.Classification(
        dimension_id="evar5", name="Campaign Owner", values_count=42, extra={},
    )
    assert c.dimension_id == "evar5"
    assert c.values_count == 42


@pytest.mark.parametrize(
    "cls,kwargs",
    [
        (models.ReportSuite, {"rsid": "x", "name": "n", "timezone": "T"}),
        (models.Dimension, {"id": "x", "name": "n", "type": "t", "description": None, "extra": {}}),
        (models.Metric, {"id": "x", "name": "n", "type": "t", "description": None, "extra": {}}),
    ],
)
def test_models_are_frozen(cls, kwargs) -> None:
    instance = cls(**kwargs)
    with pytest.raises((AttributeError, Exception)):
        instance.name = "modified"  # type: ignore[misc]
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/api/test_models.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `api/models.py`**

```python
"""SDK-agnostic normalized component models. Only `api/` produces these;
everything else consumes them. See design spec §2."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ReportSuite:
    """An Adobe Analytics report suite."""

    rsid: str
    name: str
    timezone: str | None


@dataclass(frozen=True, slots=True)
class Dimension:
    """A dimension (eVar, prop, event, etc.)."""

    id: str
    name: str
    type: str
    description: str | None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Metric:
    """A metric (numeric counter or rate)."""

    id: str
    name: str
    type: str
    description: str | None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Segment:
    """A segment definition."""

    id: str
    name: str
    description: str | None
    definition: dict[str, Any]
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CalculatedMetric:
    """A calculated metric — formula + metadata."""

    id: str
    name: str
    description: str | None
    formula: dict[str, Any]
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VirtualReportSuite:
    """A virtual report suite — a filtered view of a parent RS."""

    id: str
    name: str
    parent_rsid: str
    segments: list[str]
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Classification:
    """A classification on a dimension."""

    dimension_id: str
    name: str
    values_count: int
    extra: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/api/test_models.py -v`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add src/aa_auto_sdr/api/models.py tests/api/
git commit -m "feat(api): normalized component dataclasses"
```

### Task 12: API client wrapper (`api/client.py`)

**Files:**
- Create: `src/aa_auto_sdr/api/auth.py`
- Create: `src/aa_auto_sdr/api/client.py`
- Create: `tests/api/test_client.py`

- [ ] **Step 1: Write failing tests**

```python
"""Client wrapper isolates the aanalytics2 SDK."""
from unittest.mock import MagicMock, patch

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core.credentials import Credentials


def _creds() -> Credentials:
    return Credentials(
        org_id="O", client_id="C", secret="S", scopes="X", sandbox=None, source="env",
    )


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_client_constructs_aanalytics2_with_oauth(aa_module: MagicMock) -> None:
    aa_module.Analytics.return_value = MagicMock()
    AaClient.from_credentials(_creds())
    aa_module.configure.assert_called_once()
    aa_module.Analytics.assert_called_once()


@patch("aa_auto_sdr.api.client.aanalytics2")
def test_client_exposes_underlying_handle(aa_module: MagicMock) -> None:
    handle = MagicMock()
    aa_module.Analytics.return_value = handle
    client = AaClient.from_credentials(_creds())
    assert client.handle is handle
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/api/test_client.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `api/auth.py`**

```python
"""OAuth Server-to-Server credential dict for aanalytics2."""
from __future__ import annotations

from typing import Any

from aa_auto_sdr.core.credentials import Credentials


def credentials_to_aanalytics2_config(creds: Credentials) -> dict[str, Any]:
    """Map our Credentials shape to aanalytics2's configure() argument."""
    return {
        "org_id": creds.org_id,
        "client_id": creds.client_id,
        "secret": creds.secret,
        "scopes": creds.scopes,
    }
```

- [ ] **Step 4: Implement `api/client.py`**

```python
"""Wrapper around aanalytics2.Analytics.

This is the **only** module (besides api/auth.py and api/fetch.py) that
imports aanalytics2. SDK isolation is enforced by a meta-test in v0.9.

API 2.0 only. No 1.4 fallback paths exist or will be added here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aanalytics2  # type: ignore[import-untyped]

from aa_auto_sdr.api.auth import credentials_to_aanalytics2_config
from aa_auto_sdr.core.credentials import Credentials


@dataclass(slots=True)
class AaClient:
    """Authenticated handle to the AA 2.0 API."""

    handle: Any  # aanalytics2.Analytics

    @classmethod
    def from_credentials(cls, creds: Credentials) -> "AaClient":
        creds.validate()
        config = credentials_to_aanalytics2_config(creds)
        aanalytics2.configure(**config)
        handle = aanalytics2.Analytics()
        return cls(handle=handle)
```

- [ ] **Step 5: Run, expect pass**

Run: `uv run pytest tests/api/test_client.py -v`
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add src/aa_auto_sdr/api/auth.py src/aa_auto_sdr/api/client.py tests/api/test_client.py
git commit -m "feat(api): AaClient wrapper around aanalytics2"
```

### Task 13: Fixture corpus for fetcher tests

**Files:**
- Create: `tests/fixtures/__init__.py`
- Create: `tests/fixtures/sample_rs.json`

- [ ] **Step 1: Create empty `__init__.py`**

Empty file at `tests/fixtures/__init__.py`.

- [ ] **Step 2: Create the sample corpus**

`tests/fixtures/sample_rs.json`:

```json
{
  "report_suite": {
    "rsid": "demo.prod",
    "name": "Demo Production",
    "timezone": "US/Pacific"
  },
  "dimensions": [
    {"id": "evar1", "name": "User ID", "type": "string", "description": "Authenticated user identifier"},
    {"id": "evar2", "name": "Plan", "type": "string", "description": null},
    {"id": "prop1", "name": "Page Type", "type": "string", "description": "Section taxonomy"},
    {"id": "events", "name": "Custom Events", "type": "counter", "description": null}
  ],
  "metrics": [
    {"id": "metrics/pageviews", "name": "Page Views", "type": "int", "description": "Total page views"},
    {"id": "metrics/visits", "name": "Visits", "type": "int", "description": null},
    {"id": "metrics/orders", "name": "Orders", "type": "int", "description": "Conversion events"}
  ],
  "segments": [
    {"id": "s_111", "name": "Mobile Users", "description": "Mobile device traffic", "definition": {"hits": "device=mobile"}},
    {"id": "s_222", "name": "Returning Visitors", "description": null, "definition": {"visits": "type=returning"}}
  ],
  "calculated_metrics": [
    {"id": "cm_1", "name": "Conversion Rate", "description": "Orders divided by visits", "formula": {"func": "divide", "args": ["orders", "visits"]}}
  ],
  "virtual_report_suites": [
    {"id": "vrs_eu", "name": "EU Visitors Only", "parent_rsid": "demo.prod", "segments": ["s_eu"]}
  ],
  "classifications": [
    {"dimension_id": "evar5", "name": "Campaign Owner", "values_count": 42},
    {"dimension_id": "evar5", "name": "Campaign Type", "values_count": 8}
  ]
}
```

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/
git commit -m "test: add sample report-suite fixture corpus"
```

### Task 14: Implement `api/fetch.py` with mocked tests

**Files:**
- Create: `src/aa_auto_sdr/api/fetch.py`
- Create: `tests/api/test_fetch.py`

- [ ] **Step 1: Write failing tests**

```python
"""Fetcher tests use a mocked AaClient to avoid network."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aa_auto_sdr.api import fetch, models
from aa_auto_sdr.api.client import AaClient


FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


@pytest.fixture
def mock_client() -> AaClient:
    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()

    handle.getReportSuites.return_value = [raw["report_suite"]]
    handle.getDimensions.return_value = raw["dimensions"]
    handle.getMetrics.return_value = raw["metrics"]
    handle.getSegments.return_value = raw["segments"]
    handle.getCalculatedMetrics.return_value = raw["calculated_metrics"]
    handle.getVirtualReportSuites.return_value = raw["virtual_report_suites"]
    handle.getClassifications.return_value = raw["classifications"]

    return AaClient(handle=handle)


def test_fetch_report_suite_returns_normalized(mock_client: AaClient) -> None:
    rs = fetch.fetch_report_suite(mock_client, "demo.prod")
    assert isinstance(rs, models.ReportSuite)
    assert rs.rsid == "demo.prod"
    assert rs.name == "Demo Production"


def test_fetch_dimensions_returns_list(mock_client: AaClient) -> None:
    dims = fetch.fetch_dimensions(mock_client, "demo.prod")
    assert len(dims) == 4
    assert all(isinstance(d, models.Dimension) for d in dims)
    assert dims[0].id == "evar1"


def test_fetch_metrics_returns_list(mock_client: AaClient) -> None:
    mets = fetch.fetch_metrics(mock_client, "demo.prod")
    assert len(mets) == 3
    assert all(isinstance(m, models.Metric) for m in mets)


def test_fetch_segments_returns_list(mock_client: AaClient) -> None:
    segs = fetch.fetch_segments(mock_client, "demo.prod")
    assert len(segs) == 2
    assert all(isinstance(s, models.Segment) for s in segs)


def test_fetch_calculated_metrics_returns_list(mock_client: AaClient) -> None:
    cms = fetch.fetch_calculated_metrics(mock_client, "demo.prod")
    assert len(cms) == 1
    assert cms[0].name == "Conversion Rate"


def test_fetch_virtual_report_suites_returns_list(mock_client: AaClient) -> None:
    vrs = fetch.fetch_virtual_report_suites(mock_client, "demo.prod")
    assert len(vrs) == 1
    assert vrs[0].parent_rsid == "demo.prod"


def test_fetch_classifications_returns_list(mock_client: AaClient) -> None:
    cs = fetch.fetch_classifications(mock_client, "demo.prod")
    assert len(cs) == 2
    assert cs[0].dimension_id == "evar5"
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/api/test_fetch.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `api/fetch.py`**

```python
"""Per-component fetchers. Calls into the aanalytics2 SDK and normalizes
results into our SDK-agnostic dataclasses (api/models.py).

Method names on the SDK handle (e.g. `getDimensions`) match aanalytics2's
public API. If a name changes upstream, fix it here and only here.
"""
from __future__ import annotations

from typing import Any

from aa_auto_sdr.api import models
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core.exceptions import ReportSuiteNotFoundError


def _str_or_none(d: dict[str, Any], key: str) -> str | None:
    val = d.get(key)
    return str(val) if val not in (None, "") else None


def _extra(d: dict[str, Any], known: set[str]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k not in known}


def fetch_report_suite(client: AaClient, rsid: str) -> models.ReportSuite:
    suites = client.handle.getReportSuites()
    for raw in suites:
        if raw.get("rsid") == rsid:
            return models.ReportSuite(
                rsid=str(raw["rsid"]),
                name=str(raw.get("name", rsid)),
                timezone=_str_or_none(raw, "timezone"),
            )
    raise ReportSuiteNotFoundError(f"Report suite '{rsid}' not found")


def fetch_dimensions(client: AaClient, rsid: str) -> list[models.Dimension]:
    raws = client.handle.getDimensions(rsid=rsid) if _accepts_rsid(client.handle.getDimensions) else client.handle.getDimensions()
    known = {"id", "name", "type", "description"}
    return [
        models.Dimension(
            id=str(r["id"]),
            name=str(r.get("name", r["id"])),
            type=str(r.get("type", "unknown")),
            description=_str_or_none(r, "description"),
            extra=_extra(r, known),
        )
        for r in raws
    ]


def fetch_metrics(client: AaClient, rsid: str) -> list[models.Metric]:
    raws = client.handle.getMetrics(rsid=rsid) if _accepts_rsid(client.handle.getMetrics) else client.handle.getMetrics()
    known = {"id", "name", "type", "description"}
    return [
        models.Metric(
            id=str(r["id"]),
            name=str(r.get("name", r["id"])),
            type=str(r.get("type", "unknown")),
            description=_str_or_none(r, "description"),
            extra=_extra(r, known),
        )
        for r in raws
    ]


def fetch_segments(client: AaClient, rsid: str) -> list[models.Segment]:
    raws = client.handle.getSegments(rsid=rsid) if _accepts_rsid(client.handle.getSegments) else client.handle.getSegments()
    known = {"id", "name", "description", "definition"}
    return [
        models.Segment(
            id=str(r["id"]),
            name=str(r.get("name", r["id"])),
            description=_str_or_none(r, "description"),
            definition=dict(r.get("definition") or {}),
            extra=_extra(r, known),
        )
        for r in raws
    ]


def fetch_calculated_metrics(client: AaClient, rsid: str) -> list[models.CalculatedMetric]:
    raws = client.handle.getCalculatedMetrics(rsid=rsid) if _accepts_rsid(client.handle.getCalculatedMetrics) else client.handle.getCalculatedMetrics()
    known = {"id", "name", "description", "formula"}
    return [
        models.CalculatedMetric(
            id=str(r["id"]),
            name=str(r.get("name", r["id"])),
            description=_str_or_none(r, "description"),
            formula=dict(r.get("formula") or {}),
            extra=_extra(r, known),
        )
        for r in raws
    ]


def fetch_virtual_report_suites(client: AaClient, parent_rsid: str) -> list[models.VirtualReportSuite]:
    raws = client.handle.getVirtualReportSuites()
    known = {"id", "name", "parent_rsid", "segments"}
    return [
        models.VirtualReportSuite(
            id=str(r["id"]),
            name=str(r.get("name", r["id"])),
            parent_rsid=str(r.get("parent_rsid", "")),
            segments=list(r.get("segments") or []),
            extra=_extra(r, known),
        )
        for r in raws
        if r.get("parent_rsid") == parent_rsid
    ]


def fetch_classifications(client: AaClient, rsid: str) -> list[models.Classification]:
    raws = client.handle.getClassifications(rsid=rsid) if _accepts_rsid(client.handle.getClassifications) else client.handle.getClassifications()
    known = {"dimension_id", "name", "values_count"}
    return [
        models.Classification(
            dimension_id=str(r["dimension_id"]),
            name=str(r.get("name", "")),
            values_count=int(r.get("values_count", 0)),
            extra=_extra(r, known),
        )
        for r in raws
    ]


def _accepts_rsid(method: Any) -> bool:
    """Most aanalytics2 list methods accept rsid kwarg; mocks may not."""
    try:
        import inspect

        sig = inspect.signature(method)
        return "rsid" in sig.parameters
    except (TypeError, ValueError):
        return False
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/api/test_fetch.py -v`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add src/aa_auto_sdr/api/fetch.py tests/api/test_fetch.py
git commit -m "feat(api): per-component fetchers with normalized output"
```

---

## Phase 4 — SDR builder

### Task 15: `SdrDocument` dataclass

**Files:**
- Create: `src/aa_auto_sdr/sdr/document.py`
- Create: `tests/sdr/__init__.py`
- Create: `tests/sdr/test_document.py`

- [ ] **Step 1: Write failing tests**

`tests/sdr/__init__.py`: empty.

`tests/sdr/test_document.py`:

```python
"""SdrDocument is the boundary between fetch/builder and output/snapshot."""
from datetime import UTC, datetime

from aa_auto_sdr.api import models
from aa_auto_sdr.sdr.document import SdrDocument


def _ts() -> datetime:
    return datetime(2026, 4, 25, 17, 30, tzinfo=UTC)


def test_sdr_document_holds_all_component_lists() -> None:
    rs = models.ReportSuite(rsid="x", name="X", timezone=None)
    doc = SdrDocument(
        report_suite=rs,
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=_ts(),
        tool_version="0.1.0",
    )
    assert doc.report_suite == rs
    assert doc.tool_version == "0.1.0"


def test_sdr_document_to_dict_round_trip() -> None:
    rs = models.ReportSuite(rsid="x", name="X", timezone="UTC")
    dim = models.Dimension(id="evar1", name="User", type="string", description=None, extra={})
    doc = SdrDocument(
        report_suite=rs, dimensions=[dim],
        metrics=[], segments=[], calculated_metrics=[],
        virtual_report_suites=[], classifications=[],
        captured_at=_ts(), tool_version="0.1.0",
    )
    d = doc.to_dict()
    assert d["report_suite"]["rsid"] == "x"
    assert d["dimensions"][0]["id"] == "evar1"
    assert d["captured_at"] == "2026-04-25T17:30:00+00:00"
    assert d["tool_version"] == "0.1.0"
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/sdr/test_document.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `sdr/document.py`**

```python
"""SdrDocument — the boundary type produced by builder and consumed by output/snapshot."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from aa_auto_sdr.api import models


@dataclass(frozen=True, slots=True)
class SdrDocument:
    report_suite: models.ReportSuite
    dimensions: list[models.Dimension]
    metrics: list[models.Metric]
    segments: list[models.Segment]
    calculated_metrics: list[models.CalculatedMetric]
    virtual_report_suites: list[models.VirtualReportSuite]
    classifications: list[models.Classification]
    captured_at: datetime
    tool_version: str

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict shape used by JSON output and snapshots."""
        return {
            "report_suite": asdict(self.report_suite),
            "dimensions": [asdict(d) for d in self.dimensions],
            "metrics": [asdict(m) for m in self.metrics],
            "segments": [asdict(s) for s in self.segments],
            "calculated_metrics": [asdict(c) for c in self.calculated_metrics],
            "virtual_report_suites": [asdict(v) for v in self.virtual_report_suites],
            "classifications": [asdict(c) for c in self.classifications],
            "captured_at": self.captured_at.isoformat(),
            "tool_version": self.tool_version,
        }
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/sdr/test_document.py -v`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add src/aa_auto_sdr/sdr/document.py tests/sdr/
git commit -m "feat(sdr): SdrDocument boundary type"
```

### Task 16: Pure SDR builder

**Files:**
- Create: `src/aa_auto_sdr/sdr/builder.py`
- Create: `tests/sdr/test_builder.py`

- [ ] **Step 1: Write failing tests**

```python
"""Pure builder: fetch → SdrDocument with no I/O."""
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.sdr.builder import build_sdr


FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


def _mock_client() -> AaClient:
    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = [raw["report_suite"]]
    handle.getDimensions.return_value = raw["dimensions"]
    handle.getMetrics.return_value = raw["metrics"]
    handle.getSegments.return_value = raw["segments"]
    handle.getCalculatedMetrics.return_value = raw["calculated_metrics"]
    handle.getVirtualReportSuites.return_value = raw["virtual_report_suites"]
    handle.getClassifications.return_value = raw["classifications"]
    return AaClient(handle=handle)


def test_build_sdr_returns_complete_document() -> None:
    client = _mock_client()
    captured_at = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
    doc = build_sdr(client, "demo.prod", captured_at=captured_at, tool_version="0.1.0")

    assert doc.report_suite.rsid == "demo.prod"
    assert len(doc.dimensions) == 4
    assert len(doc.metrics) == 3
    assert len(doc.segments) == 2
    assert len(doc.calculated_metrics) == 1
    assert len(doc.virtual_report_suites) == 1
    assert len(doc.classifications) == 2
    assert doc.captured_at == captured_at
    assert doc.tool_version == "0.1.0"


def test_build_sdr_components_sorted_by_id() -> None:
    client = _mock_client()
    doc = build_sdr(
        client, "demo.prod",
        captured_at=datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
        tool_version="0.1.0",
    )
    dim_ids = [d.id for d in doc.dimensions]
    assert dim_ids == sorted(dim_ids)
    metric_ids = [m.id for m in doc.metrics]
    assert metric_ids == sorted(metric_ids)
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/sdr/test_builder.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `sdr/builder.py`**

```python
"""Pure SDR builder: AaClient + RSID → SdrDocument.

NO I/O. Side effects belong elsewhere (output writers, snapshot store).
Component lists are sorted by ID for stable diffs."""
from __future__ import annotations

from datetime import datetime

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.sdr.document import SdrDocument


def build_sdr(
    client: AaClient,
    rsid: str,
    *,
    captured_at: datetime,
    tool_version: str,
) -> SdrDocument:
    """Fetch all components for `rsid` and assemble an SdrDocument."""
    rs = fetch.fetch_report_suite(client, rsid)
    return SdrDocument(
        report_suite=rs,
        dimensions=sorted(fetch.fetch_dimensions(client, rsid), key=lambda d: d.id),
        metrics=sorted(fetch.fetch_metrics(client, rsid), key=lambda m: m.id),
        segments=sorted(fetch.fetch_segments(client, rsid), key=lambda s: s.id),
        calculated_metrics=sorted(
            fetch.fetch_calculated_metrics(client, rsid), key=lambda c: c.id,
        ),
        virtual_report_suites=sorted(
            fetch.fetch_virtual_report_suites(client, rsid), key=lambda v: v.id,
        ),
        classifications=sorted(
            fetch.fetch_classifications(client, rsid),
            key=lambda c: (c.dimension_id, c.name),
        ),
        captured_at=captured_at,
        tool_version=tool_version,
    )
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/sdr/test_builder.py -v`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add src/aa_auto_sdr/sdr/builder.py tests/sdr/test_builder.py
git commit -m "feat(sdr): pure builder assembles SdrDocument"
```

---

## Phase 5 — Output writers

### Task 17: `Writer` protocol and registry

**Files:**
- Create: `src/aa_auto_sdr/output/protocols.py`
- Create: `src/aa_auto_sdr/output/registry.py`
- Create: `tests/output/__init__.py`
- Create: `tests/output/test_registry.py`

- [ ] **Step 1: Write failing tests**

`tests/output/__init__.py`: empty.

`tests/output/test_registry.py`:

```python
"""Format → Writer registry with alias resolution.

Writer-existence tests live in test_writer_json.py and test_writer_excel.py;
this file covers only the registry contract."""
from typing import Any
from pathlib import Path

import pytest

from aa_auto_sdr.output import registry


@pytest.fixture(autouse=True)
def _isolate_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset _WRITERS so tests in this module don't leak into one another."""
    monkeypatch.setattr(registry, "_WRITERS", {})


def test_unknown_format_raises() -> None:
    with pytest.raises(KeyError):
        registry.resolve_formats("nonsense")


def test_concrete_format_resolves_to_self() -> None:
    assert registry.resolve_formats("json") == ["json"]


def test_alias_all_resolves_to_five_formats() -> None:
    assert set(registry.resolve_formats("all")) == {"excel", "csv", "json", "html", "markdown"}


def test_alias_reports_resolves_to_excel_markdown() -> None:
    assert set(registry.resolve_formats("reports")) == {"excel", "markdown"}


def test_alias_data_resolves_to_csv_json() -> None:
    assert set(registry.resolve_formats("data")) == {"csv", "json"}


def test_alias_ci_resolves_to_json_markdown() -> None:
    assert set(registry.resolve_formats("ci")) == {"json", "markdown"}


def test_register_writer_then_get_writer_round_trip() -> None:
    class _Stub:
        extension = ".stub"

        def write(self, doc: Any, output_path: Path) -> Path:
            return output_path

    registry.register_writer("stub", _Stub())
    assert isinstance(registry.get_writer("stub"), _Stub)


def test_get_writer_unknown_raises() -> None:
    with pytest.raises(KeyError):
        registry.get_writer("not-registered")
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/output/test_registry.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `output/protocols.py`**

```python
"""Writer protocol — every output format implements this."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from aa_auto_sdr.sdr.document import SdrDocument


class Writer(Protocol):
    """Renders an SdrDocument to a file (or stdout)."""

    extension: str

    def write(self, doc: SdrDocument, output_path: Path) -> Path:
        """Write `doc` to `output_path` (or a derived path). Return the actual path written."""
        ...
```

- [ ] **Step 4: Implement `output/registry.py`**

```python
"""Format alias resolution and writer registry.

Writers register themselves by being imported. Callers that need a writer
should call `bootstrap()` first; the pipeline does this in one place."""
from __future__ import annotations

from aa_auto_sdr.output.protocols import Writer

_ALIASES: dict[str, list[str]] = {
    "all": ["excel", "csv", "json", "html", "markdown"],
    "reports": ["excel", "markdown"],
    "data": ["csv", "json"],
    "ci": ["json", "markdown"],
}

_CONCRETE = {"excel", "csv", "json", "html", "markdown"}

_WRITERS: dict[str, Writer] = {}


def resolve_formats(name: str) -> list[str]:
    """Resolve a user-facing format name to one or more concrete format keys."""
    if name in _ALIASES:
        return list(_ALIASES[name])
    if name in _CONCRETE:
        return [name]
    raise KeyError(f"Unknown format or alias: {name!r}")


def register_writer(name: str, writer: Writer) -> None:
    _WRITERS[name] = writer


def get_writer(name: str) -> Writer:
    if name not in _WRITERS:
        raise KeyError(f"No writer registered for format {name!r}")
    return _WRITERS[name]


def bootstrap() -> None:
    """Import the v0.1 writer modules so they self-register.

    Heavy deps (pandas, xlsxwriter) are pulled in here, not at registry import,
    so the fast-path entry stays cheap."""
    from aa_auto_sdr.output.writers import excel as _excel  # noqa: F401, PLC0415
    from aa_auto_sdr.output.writers import json as _json  # noqa: F401, PLC0415
```

- [ ] **Step 5: Run tests, expect pass**

Run: `uv run pytest tests/output/test_registry.py -v`
Expected: all passing — tests cover only the registry contract; writer-existence tests live with each writer.

- [ ] **Step 6: Commit infrastructure**

```bash
git add src/aa_auto_sdr/output/protocols.py src/aa_auto_sdr/output/registry.py tests/output/
git commit -m "feat(output): Writer protocol and registry"
```

### Task 18: JSON writer

**Files:**
- Create: `src/aa_auto_sdr/output/writers/json.py`
- Create: `tests/output/test_writer_json.py`

- [ ] **Step 1: Write failing tests**

```python
"""JSON writer: serializes SdrDocument.to_dict() via atomic write."""
import json
from datetime import UTC, datetime
from pathlib import Path

from aa_auto_sdr.api import models
from aa_auto_sdr.output.writers.json import JsonWriter
from aa_auto_sdr.sdr.document import SdrDocument


def _doc() -> SdrDocument:
    return SdrDocument(
        report_suite=models.ReportSuite(rsid="x", name="X", timezone="UTC"),
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.1.0",
    )


def test_json_writer_extension() -> None:
    assert JsonWriter().extension == ".json"


def test_json_writer_writes_valid_json(tmp_path: Path) -> None:
    target = tmp_path / "sdr.json"
    actual = JsonWriter().write(_doc(), target)
    assert actual == target
    assert target.exists()
    parsed = json.loads(target.read_text())
    assert parsed["report_suite"]["rsid"] == "x"
    assert parsed["tool_version"] == "0.1.0"


def test_json_writer_appends_extension_if_missing(tmp_path: Path) -> None:
    target = tmp_path / "sdr"
    actual = JsonWriter().write(_doc(), target)
    assert actual.suffix == ".json"
    assert actual.exists()
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/output/test_writer_json.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `output/writers/json.py`**

```python
"""JSON writer. Self-registers with the registry on import."""
from __future__ import annotations

from pathlib import Path

from aa_auto_sdr.core.json_io import write_json
from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument


class JsonWriter:
    extension = ".json"

    def write(self, doc: SdrDocument, output_path: Path) -> Path:
        target = output_path if output_path.suffix == self.extension else output_path.with_suffix(self.extension)
        write_json(target, doc.to_dict())
        return target


register_writer("json", JsonWriter())
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/output/test_writer_json.py -v`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add src/aa_auto_sdr/output/writers/json.py tests/output/test_writer_json.py
git commit -m "feat(output): JSON writer"
```

### Task 19: Excel writer (multi-sheet)

**Files:**
- Create: `src/aa_auto_sdr/output/writers/excel.py`
- Create: `tests/output/test_writer_excel.py`

- [ ] **Step 1: Write failing tests**

```python
"""Excel writer: one sheet per component type, frozen header row, autofilter."""
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.output.writers.excel import ExcelWriter
from aa_auto_sdr.sdr.builder import build_sdr
from unittest.mock import MagicMock


FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


@pytest.fixture
def doc():
    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = [raw["report_suite"]]
    handle.getDimensions.return_value = raw["dimensions"]
    handle.getMetrics.return_value = raw["metrics"]
    handle.getSegments.return_value = raw["segments"]
    handle.getCalculatedMetrics.return_value = raw["calculated_metrics"]
    handle.getVirtualReportSuites.return_value = raw["virtual_report_suites"]
    handle.getClassifications.return_value = raw["classifications"]
    client = AaClient(handle=handle)
    return build_sdr(client, "demo.prod", captured_at=datetime(2026, 4, 25, tzinfo=UTC), tool_version="0.1.0")


def test_excel_extension() -> None:
    assert ExcelWriter().extension == ".xlsx"


def test_excel_writer_creates_file(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.xlsx"
    actual = ExcelWriter().write(doc, target)
    assert actual == target
    assert target.exists()


def test_excel_has_summary_and_one_sheet_per_component(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.xlsx"
    ExcelWriter().write(doc, target)
    wb = load_workbook(target, read_only=True)
    expected = {"Summary", "Dimensions", "Metrics", "Segments", "Calculated Metrics", "Virtual Report Suites", "Classifications"}
    assert expected.issubset(set(wb.sheetnames))


def test_excel_freezes_header_row(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.xlsx"
    ExcelWriter().write(doc, target)
    wb = load_workbook(target, read_only=False)
    assert wb["Dimensions"].freeze_panes == "A2"


def test_excel_dimension_rows_match_doc(doc, tmp_path: Path) -> None:
    target = tmp_path / "sdr.xlsx"
    ExcelWriter().write(doc, target)
    wb = load_workbook(target, read_only=True)
    sheet = wb["Dimensions"]
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0][0] == "id"
    assert len(rows) == 1 + len(doc.dimensions)
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/output/test_writer_excel.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `output/writers/excel.py`**

```python
"""Excel writer — multi-sheet workbook, frozen header row, autofilter on every sheet.

Heavy imports (pandas, xlsxwriter) are deferred to method scope so the registry
can be loaded without paying the import cost on fast paths.

Self-registers with the registry on import."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument


def _stringify(v: Any) -> Any:
    """Coerce dict/list values to str for Excel cell-friendliness."""
    if isinstance(v, (dict, list)):
        import json as _json

        return _json.dumps(v, sort_keys=True)
    return v


class ExcelWriter:
    extension = ".xlsx"

    def write(self, doc: SdrDocument, output_path: Path) -> Path:
        target = (
            output_path if output_path.suffix == self.extension else output_path.with_suffix(self.extension)
        )

        import pandas as pd  # noqa: PLC0415 — lazy import is intentional

        sheets: dict[str, pd.DataFrame] = {
            "Summary": pd.DataFrame(
                [
                    ("RSID", doc.report_suite.rsid),
                    ("Name", doc.report_suite.name),
                    ("Timezone", doc.report_suite.timezone or ""),
                    ("Captured at", doc.captured_at.isoformat()),
                    ("Tool version", doc.tool_version),
                    ("Dimensions", len(doc.dimensions)),
                    ("Metrics", len(doc.metrics)),
                    ("Segments", len(doc.segments)),
                    ("Calculated Metrics", len(doc.calculated_metrics)),
                    ("Virtual Report Suites", len(doc.virtual_report_suites)),
                    ("Classifications", len(doc.classifications)),
                ],
                columns=["Field", "Value"],
            ),
            "Dimensions": _component_df([asdict(d) for d in doc.dimensions]),
            "Metrics": _component_df([asdict(m) for m in doc.metrics]),
            "Segments": _component_df([asdict(s) for s in doc.segments]),
            "Calculated Metrics": _component_df([asdict(c) for c in doc.calculated_metrics]),
            "Virtual Report Suites": _component_df([asdict(v) for v in doc.virtual_report_suites]),
            "Classifications": _component_df([asdict(c) for c in doc.classifications]),
        }

        target.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(target, engine="xlsxwriter") as xl:
            for name, df in sheets.items():
                df.to_excel(xl, sheet_name=name, index=False)
                ws = xl.sheets[name]
                ws.freeze_panes(1, 0)
                if df.shape[1] > 0 and df.shape[0] > 0:
                    ws.autofilter(0, 0, df.shape[0], df.shape[1] - 1)
                for col_idx, col in enumerate(df.columns):
                    width = max(len(str(col)), int(df[col].astype(str).str.len().max() or 10))
                    ws.set_column(col_idx, col_idx, min(width + 2, 60))
        return target


def _component_df(rows: list[dict[str, Any]]):
    """Build a DataFrame for one component sheet, stringifying nested values."""
    import pandas as pd  # noqa: PLC0415

    if not rows:
        return pd.DataFrame()
    flat = [{k: _stringify(v) for k, v in r.items()} for r in rows]
    return pd.DataFrame(flat)


register_writer("excel", ExcelWriter())
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/output/test_writer_excel.py -v`
Expected: all passing.

- [ ] **Step 5: Run the full output test suite**

Run: `uv run pytest tests/output/ -v`
Expected: all passing (registry + json + excel).

- [ ] **Step 6: Commit**

```bash
git add src/aa_auto_sdr/output/writers/excel.py tests/output/test_writer_excel.py
git commit -m "feat(output): Excel writer with multi-sheet, frozen header, autofilter"
```

---

## Phase 6 — Pipeline

### Task 20: `RunResult` and single-RSID pipeline

**Files:**
- Create: `src/aa_auto_sdr/pipeline/models.py`
- Create: `src/aa_auto_sdr/pipeline/single.py`
- Create: `tests/pipeline/__init__.py`
- Create: `tests/pipeline/test_single.py`

- [ ] **Step 1: Write failing tests**

`tests/pipeline/__init__.py`: empty.

`tests/pipeline/test_single.py`:

```python
"""Pipeline orchestration for single-RSID generation."""
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.pipeline import single
from aa_auto_sdr.pipeline.models import RunResult


FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


@pytest.fixture
def mock_client() -> AaClient:
    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = [raw["report_suite"]]
    handle.getDimensions.return_value = raw["dimensions"]
    handle.getMetrics.return_value = raw["metrics"]
    handle.getSegments.return_value = raw["segments"]
    handle.getCalculatedMetrics.return_value = raw["calculated_metrics"]
    handle.getVirtualReportSuites.return_value = raw["virtual_report_suites"]
    handle.getClassifications.return_value = raw["classifications"]
    return AaClient(handle=handle)


def test_run_single_writes_excel_and_json(mock_client: AaClient, tmp_path: Path) -> None:
    result = single.run_single(
        client=mock_client,
        rsid="demo.prod",
        formats=["excel", "json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.1.0",
    )
    assert isinstance(result, RunResult)
    assert result.rsid == "demo.prod"
    assert result.success is True
    assert {p.suffix for p in result.outputs} == {".xlsx", ".json"}
    for p in result.outputs:
        assert p.exists()


def test_run_single_default_filename_uses_rsid(mock_client: AaClient, tmp_path: Path) -> None:
    result = single.run_single(
        client=mock_client,
        rsid="demo.prod",
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.1.0",
    )
    [path] = result.outputs
    assert path.name == "demo.prod.json"
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/pipeline/test_single.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `pipeline/models.py`**

```python
"""Pipeline result models."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RunResult:
    rsid: str
    success: bool
    outputs: list[Path] = field(default_factory=list)
    error: str | None = None
```

- [ ] **Step 4: Implement `pipeline/single.py`**

```python
"""Single-RSID pipeline: AaClient → SdrDocument → output files."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.output import registry
from aa_auto_sdr.pipeline.models import RunResult
from aa_auto_sdr.sdr.builder import build_sdr


def run_single(
    *,
    client: AaClient,
    rsid: str,
    formats: list[str],
    output_dir: Path,
    captured_at: datetime,
    tool_version: str,
) -> RunResult:
    """Generate an SDR for `rsid` and write it in every requested `format`."""
    registry.bootstrap()
    doc = build_sdr(client, rsid, captured_at=captured_at, tool_version=tool_version)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for fmt in formats:
        writer = registry.get_writer(fmt)
        target = output_dir / f"{rsid}{writer.extension}"
        paths.append(writer.write(doc, target))
    return RunResult(rsid=rsid, success=True, outputs=paths)
```

- [ ] **Step 5: Run, expect pass**

Run: `uv run pytest tests/pipeline/test_single.py -v`
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add src/aa_auto_sdr/pipeline/ tests/pipeline/
git commit -m "feat(pipeline): single-RSID orchestration"
```

---

## Phase 7 — CLI

### Task 21: Argparse parser for v0.1 surface

**Files:**
- Create: `src/aa_auto_sdr/cli/parser.py`
- Create: `tests/cli/__init__.py`
- Create: `tests/cli/test_parser.py`

- [ ] **Step 1: Write failing tests**

`tests/cli/__init__.py`: empty.

`tests/cli/test_parser.py`:

```python
"""Argparse surface for v0.1: positional RSID, profile, format, output-dir, profile-add, show-config."""
import pytest

from aa_auto_sdr.cli.parser import build_parser


def test_positional_rsid() -> None:
    p = build_parser()
    ns = p.parse_args(["demo.prod"])
    assert ns.rsid == "demo.prod"


def test_format_default_is_excel() -> None:
    p = build_parser()
    ns = p.parse_args(["demo.prod"])
    assert ns.format == "excel"


def test_format_accepts_aliases() -> None:
    p = build_parser()
    for fmt in ("excel", "json", "all", "data", "ci", "reports"):
        ns = p.parse_args(["demo.prod", "--format", fmt])
        assert ns.format == fmt


def test_format_rejects_unknown() -> None:
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["demo.prod", "--format", "nonsense"])


def test_output_dir_default_is_dot() -> None:
    p = build_parser()
    ns = p.parse_args(["demo.prod"])
    assert str(ns.output_dir) == "."


def test_profile_add_is_action() -> None:
    p = build_parser()
    ns = p.parse_args(["--profile-add", "prod"])
    assert ns.profile_add == "prod"


def test_profile_add_is_mutually_exclusive_with_rsid() -> None:
    """v0.1 defines --profile-add as a standalone action — RSID not required."""
    p = build_parser()
    ns = p.parse_args(["--profile-add", "prod"])
    assert ns.rsid is None


def test_show_config_is_action() -> None:
    p = build_parser()
    ns = p.parse_args(["--show-config"])
    assert ns.show_config is True
    assert ns.rsid is None


def test_profile_flag() -> None:
    p = build_parser()
    ns = p.parse_args(["demo.prod", "--profile", "prod"])
    assert ns.profile == "prod"
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/cli/test_parser.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `cli/parser.py`**

```python
"""Argparse surface for v0.1.

Only flags shippable in v0.1 are defined here. Discovery, inspection, batch,
and diff flags land in v0.3+ in their own milestones."""
from __future__ import annotations

import argparse
from pathlib import Path

_VALID_FORMATS = ["excel", "csv", "json", "html", "markdown", "all", "reports", "data", "ci"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aa_auto_sdr",
        description="Adobe Analytics SDR Generator (API 2.0 only)",
    )
    p.add_argument(
        "rsid", nargs="?", default=None,
        help="Report Suite ID to generate an SDR for",
    )
    p.add_argument(
        "--format", choices=_VALID_FORMATS, default="excel",
        help="Output format or alias (default: excel)",
    )
    p.add_argument(
        "--output-dir", type=Path, default=Path("."),
        help="Directory to write outputs into (default: cwd)",
    )
    p.add_argument(
        "--profile", default=None,
        help="Use a named credentials profile from ~/.aa/orgs/<name>/",
    )
    p.add_argument(
        "--profile-add", metavar="NAME", default=None,
        help="Create or update a credentials profile interactively",
    )
    p.add_argument(
        "--show-config", action="store_true",
        help="Print which credential source resolved and exit",
    )
    return p
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/cli/test_parser.py -v`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add src/aa_auto_sdr/cli/parser.py tests/cli/
git commit -m "feat(cli): argparse surface for v0.1"
```

### Task 22: `generate` command handler

**Files:**
- Create: `src/aa_auto_sdr/cli/commands/generate.py`
- Create: `tests/cli/test_commands_generate.py`

- [ ] **Step 1: Write failing tests**

```python
"""generate command: builds AaClient from credentials, runs single pipeline."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.cli.commands import generate as cmd


FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


@pytest.fixture
def env_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_writes_excel_default(mock_client_cls, env_creds, tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = [raw["report_suite"]]
    handle.getDimensions.return_value = raw["dimensions"]
    handle.getMetrics.return_value = raw["metrics"]
    handle.getSegments.return_value = raw["segments"]
    handle.getCalculatedMetrics.return_value = raw["calculated_metrics"]
    handle.getVirtualReportSuites.return_value = raw["virtual_report_suites"]
    handle.getClassifications.return_value = raw["classifications"]
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle)

    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="excel", profile=None)
    assert rc == 0
    assert (tmp_path / "demo.prod.xlsx").exists()


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_writes_all_when_format_is_all(mock_client_cls, env_creds, tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = [raw["report_suite"]]
    handle.getDimensions.return_value = raw["dimensions"]
    handle.getMetrics.return_value = raw["metrics"]
    handle.getSegments.return_value = raw["segments"]
    handle.getCalculatedMetrics.return_value = raw["calculated_metrics"]
    handle.getVirtualReportSuites.return_value = raw["virtual_report_suites"]
    handle.getClassifications.return_value = raw["classifications"]
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle)

    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="data", profile=None)
    # data alias = csv + json; v0.1 only supports json (csv arrives in v0.3)
    # so this run should report a missing-writer error rather than crash
    assert rc != 0


def test_generate_returns_config_error_when_no_creds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="excel", profile=None)
    assert rc == 10
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/cli/test_commands_generate.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `cli/commands/generate.py`**

```python
"""generate command: resolve creds → build client → run single pipeline."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core import credentials
from aa_auto_sdr.core.exceptions import (
    AaAutoSdrError,
    ApiError,
    AuthError,
    ConfigError,
    OutputError,
    ReportSuiteNotFoundError,
)
from aa_auto_sdr.core.version import __version__
from aa_auto_sdr.output import registry
from aa_auto_sdr.pipeline import single


_EXIT_OK = 0
_EXIT_GENERIC = 1
_EXIT_CONFIG = 10
_EXIT_AUTH = 11
_EXIT_API = 12
_EXIT_NOT_FOUND = 13
_EXIT_OUTPUT = 15


def run(*, rsid: str, output_dir: Path, format_name: str, profile: str | None) -> int:
    try:
        creds = credentials.resolve(profile=profile)
    except ConfigError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_CONFIG

    print(f"using credentials from: {creds.source}")

    try:
        formats = registry.resolve_formats(format_name)
    except KeyError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_GENERIC

    # In v0.1 only `json` and `excel` writers are registered. Surface a clean
    # error if a user requests a format whose writer is not in this build.
    registry.bootstrap()
    for fmt in formats:
        try:
            registry.get_writer(fmt)
        except KeyError:
            print(
                f"error: format '{fmt}' is not available in this build (v0.1 ships excel + json)",
                flush=True,
            )
            return _EXIT_OUTPUT

    try:
        client = AaClient.from_credentials(creds)
    except AuthError as e:
        print(f"auth error: {e}", flush=True)
        return _EXIT_AUTH

    try:
        result = single.run_single(
            client=client,
            rsid=rsid,
            formats=formats,
            output_dir=output_dir,
            captured_at=datetime.now(UTC),
            tool_version=__version__,
        )
    except ReportSuiteNotFoundError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_NOT_FOUND
    except ApiError as e:
        print(f"api error: {e}", flush=True)
        return _EXIT_API
    except OutputError as e:
        print(f"output error: {e}", flush=True)
        return _EXIT_OUTPUT
    except AaAutoSdrError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_GENERIC

    for path in result.outputs:
        print(f"wrote: {path}")
    return _EXIT_OK
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/cli/test_commands_generate.py -v`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add src/aa_auto_sdr/cli/commands/generate.py tests/cli/test_commands_generate.py
git commit -m "feat(cli): generate command handler"
```

### Task 23: `--profile-add` and `--show-config` handlers

**Files:**
- Create: `src/aa_auto_sdr/cli/commands/config.py`
- Create: `tests/cli/test_commands_config.py`

- [ ] **Step 1: Write failing tests**

```python
"""--profile-add and --show-config handlers."""
import json
from pathlib import Path

import pytest

from aa_auto_sdr.cli.commands import config as cmd


def test_profile_add_writes_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--profile-add reads from stdin in interactive mode; we feed it a script."""
    inputs = iter(["O@AdobeOrg", "Cid", "Sec", "Scp", ""])
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(inputs))
    rc = cmd.profile_add("prod", base=tmp_path)
    assert rc == 0
    cfg_path = tmp_path / "orgs" / "prod" / "config.json"
    assert cfg_path.exists()
    cfg = json.loads(cfg_path.read_text())
    assert cfg["org_id"] == "O@AdobeOrg"
    assert cfg["sandbox"] is None  # blank input → null


def test_show_config_prints_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")
    monkeypatch.chdir(tmp_path)
    rc = cmd.show_config(profile=None, profiles_base=tmp_path)
    assert rc == 0
    captured = capsys.readouterr()
    assert "env" in captured.out


def test_show_config_returns_config_error_when_no_creds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)
    rc = cmd.show_config(profile=None, profiles_base=tmp_path)
    assert rc == 10
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/cli/test_commands_config.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `cli/commands/config.py`**

```python
"""--profile-add and --show-config handlers."""
from __future__ import annotations

from pathlib import Path

from aa_auto_sdr.core import credentials, profiles
from aa_auto_sdr.core.exceptions import ConfigError


_EXIT_OK = 0
_EXIT_CONFIG = 10


def profile_add(name: str, *, base: Path | None = None) -> int:
    """Interactively prompt for credential fields and write them to a profile."""
    print(f"Creating profile '{name}'. Press Ctrl+C to cancel.")
    org_id = input("ORG_ID (e.g. abc@AdobeOrg): ").strip()
    client_id = input("CLIENT_ID: ").strip()
    secret = input("SECRET: ").strip()
    scopes = input("SCOPES: ").strip()
    sandbox = input("SANDBOX (optional, press enter to skip): ").strip()

    data = {
        "org_id": org_id,
        "client_id": client_id,
        "secret": secret,
        "scopes": scopes,
        "sandbox": sandbox or None,
    }
    path = profiles.write_profile(name, data, base=base)
    print(f"profile written: {path}")
    return _EXIT_OK


def show_config(*, profile: str | None, profiles_base: Path | None = None) -> int:
    """Print which credential source resolves first, without exposing secrets."""
    try:
        creds = credentials.resolve(profile=profile, profiles_base=profiles_base)
    except ConfigError as e:
        print(f"error: {e}", flush=True)
        return _EXIT_CONFIG

    print(f"source:    {creds.source}")
    print(f"org_id:    {creds.org_id}")
    print(f"client_id: {creds.client_id[:4]}…{creds.client_id[-4:] if len(creds.client_id) > 8 else ''}")
    print(f"sandbox:   {creds.sandbox or '(none)'}")
    return _EXIT_OK
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/cli/test_commands_config.py -v`
Expected: all passing.

- [ ] **Step 5: Commit**

```bash
git add src/aa_auto_sdr/cli/commands/config.py tests/cli/test_commands_config.py
git commit -m "feat(cli): --profile-add and --show-config commands"
```

### Task 24: Wire CLI dispatcher (`cli/main.py`)

**Files:**
- Modify: `src/aa_auto_sdr/cli/main.py`
- Create: `tests/cli/test_main_dispatch.py`

- [ ] **Step 1: Write failing tests**

```python
"""End-to-end CLI dispatch — covers the routing decisions in cli/main.run."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.cli.main import run


FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


def test_no_args_returns_usage_error(capsys) -> None:
    rc = run([])
    assert rc == 2
    err = capsys.readouterr().err + capsys.readouterr().out
    assert "rsid" in err.lower() or "usage" in err.lower()


def test_show_config_with_no_creds_returns_10(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)
    rc = run(["--show-config"])
    assert rc == 10


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_rsid_runs_generate(
    mock_client_cls, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = [raw["report_suite"]]
    handle.getDimensions.return_value = raw["dimensions"]
    handle.getMetrics.return_value = raw["metrics"]
    handle.getSegments.return_value = raw["segments"]
    handle.getCalculatedMetrics.return_value = raw["calculated_metrics"]
    handle.getVirtualReportSuites.return_value = raw["virtual_report_suites"]
    handle.getClassifications.return_value = raw["classifications"]
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle)

    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")

    rc = run(["demo.prod", "--format", "json", "--output-dir", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "demo.prod.json").exists()
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/cli/test_main_dispatch.py -v`
Expected: FAIL.

- [ ] **Step 3: Replace `cli/main.py` with the real dispatcher**

```python
"""CLI dispatcher — routes parsed args to a command handler."""
from __future__ import annotations

from aa_auto_sdr.cli.commands import config as config_cmd
from aa_auto_sdr.cli.commands import generate as generate_cmd
from aa_auto_sdr.cli.parser import build_parser


_EXIT_USAGE = 2


def run(argv: list[str]) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)

    if ns.profile_add:
        return config_cmd.profile_add(ns.profile_add)

    if ns.show_config:
        return config_cmd.show_config(profile=ns.profile)

    if not ns.rsid:
        parser.print_usage()
        return _EXIT_USAGE

    return generate_cmd.run(
        rsid=ns.rsid,
        output_dir=ns.output_dir,
        format_name=ns.format,
        profile=ns.profile,
    )
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/cli/ -v`
Expected: all CLI tests passing.

- [ ] **Step 5: Commit**

```bash
git add src/aa_auto_sdr/cli/main.py tests/cli/test_main_dispatch.py
git commit -m "feat(cli): dispatcher routes args to generate/config handlers"
```

---

## Phase 8 — Integration smoke and v0.1 polish

### Task 25: End-to-end smoke test through `python -m aa_auto_sdr`

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_e2e.py`

- [ ] **Step 1: Write tests**

`tests/integration/__init__.py`: empty.

`tests/integration/test_e2e.py`:

```python
"""End-to-end smoke: invoke the CLI as a subprocess against fully mocked SDK."""
import json
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


def test_module_invocation_without_args_exits_2(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr"],
        capture_output=True, text=True, check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 2


def test_module_invocation_show_config_with_creds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = {
        "PATH": __import__("os").environ["PATH"],
        "HOME": str(tmp_path),
        "ORG_ID": "O", "CLIENT_ID": "C", "SECRET": "S", "SCOPES": "X",
    }
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "--show-config"],
        capture_output=True, text=True, check=False, cwd=tmp_path, env=env,
    )
    assert result.returncode == 0
    assert "env" in result.stdout


def test_version_invocation(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", "-V"],
        capture_output=True, text=True, check=False, cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "0.1.0" in result.stdout
```

- [ ] **Step 2: Run**

Run: `uv run pytest tests/integration/ -v`
Expected: all passing.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/
git commit -m "test: end-to-end smoke via python -m aa_auto_sdr"
```

### Task 26: README + CHANGELOG for v0.1

**Files:**
- Create: `README.md`
- Create: `CHANGELOG.md`

- [ ] **Step 1: Write `README.md`**

````markdown
# aa_auto_sdr

Adobe Analytics SDR Generator — a CLI that generates Solution Design Reference documentation from an Adobe Analytics report suite. Sister project to [`cja_auto_sdr`](https://github.com/brian-a-au/cja_auto_sdr); shares UX conventions, does **not** share code.

> **Status:** v0.1 — single-RSID generation, JSON + Excel output, OAuth Server-to-Server auth. See [design spec](docs/superpowers/specs/2026-04-25-aa-auto-sdr-v1-design.md) for the full v1.0.0 roadmap.

## Requirements

- Python 3.14+
- `uv`
- An Adobe Analytics OAuth Server-to-Server credential set (Org ID, Client ID, Secret, Scopes)

## Install

```bash
uv sync --all-extras
```

## Authenticate

Pick one. Resolution precedence: `--profile` > env vars > `.env` > `./config.json`.

### Profile (recommended for daily use)

```bash
uv run aa_auto_sdr --profile-add prod
```

Stored at `~/.aa/orgs/prod/config.json`.

```bash
uv run aa_auto_sdr <RSID> --profile prod
```

### Environment variables

```bash
export ORG_ID=...@AdobeOrg
export CLIENT_ID=...
export SECRET=...
export SCOPES=...
uv run aa_auto_sdr <RSID>
```

### `.env` file

`uv add python-dotenv` and copy `.env.example` to `.env`.

### `config.json`

A `config.json` in the working directory with the same fields as the profile.

## Generate an SDR

```bash
uv run aa_auto_sdr <RSID>                     # default Excel
uv run aa_auto_sdr <RSID> --format json
uv run aa_auto_sdr <RSID> --output-dir /tmp/sdr
```

v0.1 supports `excel` and `json`. Other formats arrive in v0.3.

## Verify

```bash
uv run aa_auto_sdr -V
uv run aa_auto_sdr --show-config
```

## Develop

```bash
uv run pytest                # all tests
uv run pytest -m unit        # unit only
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

## Roadmap

See [design spec §9](docs/superpowers/specs/2026-04-25-aa-auto-sdr-v1-design.md). v0.3 = remaining output formats + discovery/inspect commands. v0.5 = `--batch`. v0.7 = snapshot + `--diff`. v0.9 = release-gate hardening. v1.0.0 = PyPI publish.
````

- [ ] **Step 2: Write `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to this project will be documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2026-04-25

### Added
- Project skeleton: `pyproject.toml`, package layout, `uv` toolchain.
- OAuth Server-to-Server authentication; four-source resolution chain (profile / env / `.env` / `config.json`).
- Profile CRUD via `--profile-add`; lookup via `--profile`.
- `--show-config` to print the resolved credential source without exposing secrets.
- Single-RSID SDR generation: dimensions, metrics, segments, calculated metrics, virtual report suites, classifications.
- JSON and Excel writers (multi-sheet, frozen header row, autofilter).
- `--version` / `--help` fast-path entry — no heavy imports.
- Pytest harness with auto-marker classification; coverage reporting.

### Out of scope (planned for later milestones)
- Remaining output formats (`csv`, `html`, `markdown`) — v0.3.
- Discovery and inspection commands — v0.3.
- Batch generation (`--batch`) — v0.5.
- Snapshot save and `--diff` — v0.7.
```

- [ ] **Step 3: Commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: README and CHANGELOG for v0.1"
```

### Task 27: Raise coverage gate, finalize, tag

- [ ] **Step 1: Re-enable the coverage gate**

Edit `pyproject.toml`, restore the unit-slice gate:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --cov=aa_auto_sdr --cov-report=term-missing --cov-fail-under=70"
markers = [
    "unit: fast unit tests with no I/O",
    "integration: end-to-end with mocked SDK",
    "smoke: subprocess CLI smoke tests",
    "e2e: real-API tests, gated by env var",
]
```

- [ ] **Step 2: Run full suite with coverage**

Run: `uv run pytest`
Expected: all passing, coverage ≥70% on the unit slice.

If coverage falls short, add tests on the lowest-covered modules until the gate is met. **Do not lower the gate.**

- [ ] **Step 3: Run lint**

Run: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
Expected: clean.

- [ ] **Step 4: Verify the package builds**

Run: `uv build`
Expected: `dist/aa_auto_sdr-0.1.0-*.whl` and `.tar.gz` produced.

- [ ] **Step 5: Verify install from the wheel works in a fresh env**

```bash
python3.14 -m venv /tmp/aa-smoke
/tmp/aa-smoke/bin/pip install dist/aa_auto_sdr-0.1.0-*.whl
/tmp/aa-smoke/bin/aa_auto_sdr -V
```

Expected: prints `aa_auto_sdr 0.1.0`.

- [ ] **Step 6: Commit and tag**

```bash
git add pyproject.toml
git commit -m "chore: re-enable 70% coverage gate for v0.1"
git tag v0.1.0
git log --oneline -10
```

- [ ] **Step 7: Verify clean tree**

Run: `git status`
Expected: working tree clean, tag `v0.1.0` present.

---

## Self-Review

After implementation, run this checklist before declaring v0.1 done:

1. **Spec coverage** — every section of the v1 design that's marked v0.1-scope has at least one task above.
   - §0 Non-goals: enforced implicitly (no CJA imports, no 1.4 paths, no shared core).
   - §1 System overview: covered by Tasks 11–20.
   - §2 Architecture: package layout matches; no `aanalytics2` import outside `api/` (formal meta-test arrives in v0.9).
   - §3 Data flow: implemented by `pipeline/single.py` (Task 20).
   - §4 Snapshot: deferred to v0.7 — no v0.1 work.
   - §5 CLI surface (v0.1 subset): `<RSID>`, `--format`, `--output-dir`, `--profile`, `--profile-add`, `--show-config`, `--version`, `--help`. ✓
   - §5.5 Auth: all four sources implemented (profile, env, `.env`, `config.json`). ✓
   - §6 Error handling: typed exceptions; exit codes 0/1/2/10/11/12/13/15 wired in `cli/commands/generate.py`. ✓
   - §7 Testing: unit + integration markers; 70% gate temporarily, raises to 90% in v0.9.
   - §8 Release infrastructure: deferred to v0.9.
   - §9 Milestone roadmap: this plan implements v0.1 cell.

2. **Type / name consistency** — function names used in later tasks match earlier definitions:
   - `AaClient.from_credentials` — defined Task 12, used in Tasks 22, 24.
   - `Credentials.validate` — defined Task 9, used in Task 12.
   - `credentials.resolve` — defined Task 10, used in Tasks 22, 23.
   - `build_sdr` — defined Task 16, used in Task 20.
   - `registry.get_writer` / `resolve_formats` — defined Task 17, used in Tasks 20, 22.

3. **No placeholders** — every step has either runnable commands or full source. No "TBD", no "similar to above", no "implement validation".

4. **Frequent commits** — every task ends with a commit; logical chunks are tight (≤200 lines diff each).

5. **TDD discipline** — every code task starts with a failing test, ends with a passing test, then commits.
