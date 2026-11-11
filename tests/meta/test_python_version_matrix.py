"""Meta-test: CI tests every Python version the package says it supports.

The pyproject classifiers are the list of supported versions. The
`tests.yml` matrix and the pip smoke loops in `release-gate.yml` and
`release.yml` must list the same versions, and the lowest one must match `requires-python`. The
`min-versions.yml` matrix runs only the lowest and highest of them. The README
badge shows only the floor (`Python 3.11+`), so it must match
`requires-python`. Adding a version in one place and not the others fails
here."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _classifier_versions() -> list[str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    prefix = "Programming Language :: Python :: "
    versions = [
        c.removeprefix(prefix) for c in project["classifiers"] if re.fullmatch(r"3\.\d+", c.removeprefix(prefix))
    ]
    return sorted(versions, key=_version_key)


def test_classifiers_are_contiguous_from_requires_python() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    floor = re.fullmatch(r">=(3\.\d+)", project["requires-python"])
    assert floor, f"unexpected requires-python: {project['requires-python']}"
    versions = _classifier_versions()
    assert versions[0] == floor.group(1)
    minors = [_version_key(v)[1] for v in versions]
    assert minors == list(range(minors[0], minors[-1] + 1)), f"gap in classifiers: {versions}"


def _matrix_versions(workflow: str) -> list[str]:
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    match = re.search(r"^\s*python-version: \[(.*)\]\s*$", text, re.MULTILINE)
    assert match, f"{workflow} has no python-version matrix list"
    return [v.strip().strip("\"'") for v in match.group(1).split(",")]


def test_tests_workflow_matrix_lists_every_supported_version() -> None:
    assert _matrix_versions("tests.yml") == _classifier_versions()


def test_min_versions_workflow_uses_floor_and_ceiling() -> None:
    versions = _classifier_versions()
    assert _matrix_versions("min-versions.yml") == [versions[0], versions[-1]]


@pytest.mark.parametrize("workflow", ["release-gate.yml", "release.yml"])
def test_smoke_install_covers_every_supported_version(workflow: str) -> None:
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    match = re.search(r"^\s*for py in ([\d. ]+); do\s*$", text, re.MULTILINE)
    assert match, f"{workflow} has no `for py in ...` smoke loop"
    assert match.group(1).split() == _classifier_versions()


def test_readme_badge_shows_the_floor() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(
        r"\[!\[Python (3\.\d+)\+\]\(https://img\.shields\.io/badge/python-(3\.\d+)%2B-blue\.svg\)\]", text
    )
    assert match, "README has no `Python 3.X+` shields.io badge"
    floor = _classifier_versions()[0]
    assert match.group(1) == floor
    assert match.group(2) == floor
