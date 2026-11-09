"""Guard the shape of the PyPI release workflow.

The PyPI trusted publisher is registered for workflow `release.yml` and
environment `pypi`. A tag push builds, publishes and creates the GitHub
Release. A manual run is a dry run of the build job only. These tests read the
workflow as text, since the project has no YAML dependency.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
TAG_PUSH_ONLY = "if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')"

_spec = importlib.util.spec_from_file_location("extract_release_notes", ROOT / "scripts" / "extract_release_notes.py")
assert _spec is not None
assert _spec.loader is not None
notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(notes)


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _top_level_block(name: str) -> str:
    match = re.search(rf"^{name}:\n(.*?)(?=^\S|\Z)", _text(), re.MULTILINE | re.DOTALL)
    assert match, f"release.yml has no top-level `{name}:` block"
    return match.group(1)


def _jobs() -> dict[str, str]:
    jobs = _top_level_block("jobs")
    parts = re.split(r"^  ([A-Za-z0-9_-]+):\n", jobs, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def _job_lines(job: str) -> list[str]:
    """Return the job's own keys (four-space indent), not the steps' keys."""
    return [line.strip() for line in _jobs()[job].splitlines() if re.match(r"^    \S", line)]


def test_triggers_are_tag_push_and_manual_dry_run() -> None:
    on = _top_level_block("on")
    assert re.search(r"^  push:\n    tags:\n      - 'v\*\.\*\.\*'\n", on, re.MULTILINE)
    assert re.search(r"^  workflow_dispatch:", on, re.MULTILINE)
    assert "branches" not in on
    assert "release:" not in on


def test_jobs_are_build_publish_github_release() -> None:
    assert list(_jobs()) == ["build", "publish", "github-release"]


def test_build_runs_for_every_trigger_with_read_only_contents() -> None:
    lines = _job_lines("build")
    assert not any(line.startswith("if:") for line in lines)
    assert "environment: pypi" not in lines
    assert re.search(r"^    permissions:\n      contents: read\n    \S", _jobs()["build"], re.MULTILINE)


def test_build_keeps_every_release_check() -> None:
    build = _jobs()["build"]
    for needle in (
        "ruff check",
        "ruff format --check",
        "uv lock --check",
        "scripts/check_version_sync.py",
        "pytest",
        "scripts/extract_release_notes.py",
        "uv build",
        "scripts/check_distribution_readme_links.py",
        "--help",
        "sha256sum",
        "actions/upload-artifact@",
    ):
        assert needle in build, f"build job lost `{needle}`"


def test_tag_check_runs_only_for_a_tag_push() -> None:
    build = _jobs()["build"]
    match = re.search(r"- name: Verify tag matches package version\n(.*?)(?=\n      - |\Z)", build, re.DOTALL)
    assert match, "build job has no tag check step"
    assert "if: github.event_name == 'push'" in match.group(1)
    assert '"$GITHUB_REF_NAME" != "v$VERSION"' in match.group(1)


def test_publish_runs_only_for_a_tag_push_in_pypi_environment() -> None:
    lines = _job_lines("publish")
    assert "needs: build" in lines
    assert TAG_PUSH_ONLY in lines
    assert "environment: pypi" in lines
    publish = _jobs()["publish"]
    assert re.search(r"^    permissions:\n      id-token: write\n    \S", publish, re.MULTILINE)
    assert "sha256sum -c ../SHA256SUMS" in publish
    assert re.search(r"pypa/gh-action-pypi-publish@[0-9a-f]{40} ", publish)
    assert "packages-dir: dist/packages/" in publish


def test_github_release_runs_only_after_publish_for_a_tag_push() -> None:
    lines = _job_lines("github-release")
    assert "needs: publish" in lines
    assert TAG_PUSH_ONLY in lines
    release = _jobs()["github-release"]
    assert re.search(r"^    permissions:\n      contents: write\n    \S", release, re.MULTILINE)
    assert "sha256sum -c ../SHA256SUMS" in release
    assert re.search(r"softprops/action-gh-release@[0-9a-f]{40} ", release)
    assert "body_path: dist/RELEASE_NOTES.md" in release
    for path in ("dist/packages/*.whl", "dist/packages/*.tar.gz", "dist/SHA256SUMS"):
        assert path in release


def test_only_publish_gets_an_id_token() -> None:
    jobs = _jobs()
    assert "id-token" not in jobs["build"]
    assert "id-token" not in jobs["github-release"]
    assert re.search(r"^permissions: \{\}$", _text(), re.MULTILINE)


def test_every_action_is_pinned_by_commit() -> None:
    uses = re.findall(r"uses: (\S+)", _text())
    assert uses
    for ref in uses:
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), f"{ref} is not pinned by commit SHA"


CHANGELOG = """# Changelog

Intro text.

## [1.2.4] — 2026-11-02

### Fixed
- Second fix.

## [1.2.3] — 2026-11-01

First release body.

### Added
- A thing.

## [1.2.2] — 2026-10-01
- Old.
"""


def test_extract_returns_only_the_requested_section() -> None:
    assert notes.extract(CHANGELOG, "1.2.3") == "First release body.\n\n### Added\n- A thing.\n"
    assert notes.extract(CHANGELOG, "1.2.2") == "- Old.\n"


def test_extract_does_not_match_a_version_prefix() -> None:
    with pytest.raises(ValueError, match=re.escape("no '## [1.2]' section")):
        notes.extract(CHANGELOG, "1.2")


def test_extract_rejects_an_empty_section() -> None:
    with pytest.raises(ValueError, match="is empty"):
        notes.extract("## [2.0.0] — 2026-11-03\n\n## [1.0.0]\n- x\n", "2.0.0")


def test_main_writes_notes_and_reports_missing_sections(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    output = tmp_path / "out" / "RELEASE_NOTES.md"
    assert notes.main(["1.2.4", str(output), "--changelog", str(changelog)]) == 0
    assert output.read_text(encoding="utf-8") == "### Fixed\n- Second fix.\n"
    assert notes.main(["9.9.9", str(output), "--changelog", str(changelog)]) == 1
    assert "no '## [9.9.9]' section" in capsys.readouterr().err


def test_current_version_has_release_notes() -> None:
    text = (ROOT / "src" / "aa_auto_sdr" / "core" / "version.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match
    assert notes.extract((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), match.group(1)).strip()
