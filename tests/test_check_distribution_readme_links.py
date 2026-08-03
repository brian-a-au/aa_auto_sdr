"""Artifact-level checks for the PyPI README link policy."""

from __future__ import annotations

import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_distribution_readme_links.py"


def _metadata(description: str) -> str:
    return (
        "Metadata-Version: 2.4\n"
        "Name: example-package\n"
        "Version: 1.0.0\n"
        "Description-Content-Type: text/markdown\n"
        f"\n{description}\n"
    )


def _write_wheel(path: Path, description: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("example_package-1.0.0.dist-info/METADATA", _metadata(description))


def _write_sdist(path: Path, description: str) -> None:
    payload = _metadata(description).encode()
    info = tarfile.TarInfo("example_package-1.0.0/PKG-INFO")
    info.size = len(payload)
    with tarfile.open(path, "w:gz") as archive:
        archive.addfile(info, io.BytesIO(payload))


def _run(*artifacts: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(artifact) for artifact in artifacts)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_accepts_absolute_and_fragment_links_in_matching_artifacts(tmp_path: Path) -> None:
    description = (
        "[Guide](https://github.com/example/project/blob/main/docs/GUIDE.md)\n"
        "[Section](#section)\n"
        '<img src="https://example.com/badge.svg" alt="badge">'
    )
    wheel = tmp_path / "example_package-1.0.0-py3-none-any.whl"
    sdist = tmp_path / "example_package-1.0.0.tar.gz"
    _write_wheel(wheel, description)
    _write_sdist(sdist, description)

    result = _run(wheel, sdist)

    assert result.returncode == 0, result.stderr
    assert "distribution README links OK" in result.stdout


def test_rejects_relative_markdown_and_html_targets(tmp_path: Path) -> None:
    description = '[Guide](docs/GUIDE.md)\n<img src="assets/logo.svg" alt="logo">'
    wheel = tmp_path / "example_package-1.0.0-py3-none-any.whl"
    _write_wheel(wheel, description)

    result = _run(wheel)

    assert result.returncode == 1
    assert "docs/GUIDE.md" in result.stderr
    assert "assets/logo.svg" in result.stderr
    assert "repository-relative" in result.stderr


def test_rejects_wheel_and_sdist_description_drift(tmp_path: Path) -> None:
    wheel = tmp_path / "example_package-1.0.0-py3-none-any.whl"
    sdist = tmp_path / "example_package-1.0.0.tar.gz"
    _write_wheel(wheel, "[Guide](https://example.com/wheel)")
    _write_sdist(sdist, "[Guide](https://example.com/sdist)")

    result = _run(wheel, sdist)

    assert result.returncode == 1
    assert "descriptions differ" in result.stderr


def test_rejects_non_ascii_wheel_and_sdist_description_drift(tmp_path: Path) -> None:
    wheel = tmp_path / "example_package-1.0.0-py3-none-any.whl"
    sdist = tmp_path / "example_package-1.0.0.tar.gz"
    _write_wheel(wheel, "Café")
    _write_sdist(sdist, "Cafè")

    result = _run(wheel, sdist)

    assert result.returncode == 1
    assert "descriptions differ" in result.stderr


def test_rejects_malformed_and_unsupported_schemes(tmp_path: Path) -> None:
    description = "[Malformed](https:docs/GUIDE.md)\n[Unsupported](file:README.md)"
    wheel = tmp_path / "example_package-1.0.0-py3-none-any.whl"
    _write_wheel(wheel, description)

    result = _run(wheel)

    assert result.returncode == 1
    assert "https:docs/GUIDE.md" in result.stderr
    assert "file:README.md" in result.stderr


def test_rejects_relative_reference_style_target(tmp_path: Path) -> None:
    description = "[Guide][guide]\n\n[guide]: docs/GUIDE.md"
    wheel = tmp_path / "example_package-1.0.0-py3-none-any.whl"
    _write_wheel(wheel, description)

    result = _run(wheel)

    assert result.returncode == 1
    assert "docs/GUIDE.md" in result.stderr
