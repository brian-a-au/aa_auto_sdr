"""Reject repository-relative links in built distribution descriptions."""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

INLINE_TARGET_RE = re.compile(r"]\(\s*(?:<([^>]+)>|([^\s)]+))")
REFERENCE_TARGET_RE = re.compile(
    r"^\s{0,3}\[[^]]+]:\s*(?:<([^>]+)>|([^\s]+))",
    re.MULTILINE,
)


class _HTMLLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: list[str] = []

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.targets.extend(value for name, value in attrs if name in {"href", "src"} and value)

    handle_startendtag = handle_starttag


def _description_from_metadata(metadata: bytes, artifact: Path) -> str:
    message = BytesParser(policy=policy.default).parsebytes(metadata)
    content_type = message.get("Description-Content-Type", "")
    if not content_type.lower().startswith("text/markdown"):
        raise ValueError(f"{artifact}: Description-Content-Type is not text/markdown")

    payload = message.get_payload(decode=True)
    if not isinstance(payload, bytes):
        raise ValueError(f"{artifact}: package description is missing")
    description = payload.decode("utf-8")
    if not description.strip():
        raise ValueError(f"{artifact}: package description is missing")
    return description


def _read_wheel(path: Path) -> bytes:
    with zipfile.ZipFile(path) as archive:
        candidates = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(candidates) != 1:
            raise ValueError(f"{path}: expected one .dist-info/METADATA file, found {len(candidates)}")
        return archive.read(candidates[0])


def _read_sdist(path: Path) -> bytes:
    with tarfile.open(path, "r:*") as archive:
        candidates = [
            member for member in archive.getmembers() if member.isfile() and member.name.endswith("/PKG-INFO")
        ]
        if len(candidates) != 1:
            raise ValueError(f"{path}: expected one top-level PKG-INFO file, found {len(candidates)}")
        extracted = archive.extractfile(candidates[0])
        if extracted is None:
            raise ValueError(f"{path}: could not read PKG-INFO")
        return extracted.read()


def read_description(path: Path) -> str:
    if path.suffix == ".whl":
        metadata = _read_wheel(path)
    elif path.name.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
        metadata = _read_sdist(path)
    else:
        raise ValueError(f"{path}: unsupported distribution type")
    return _description_from_metadata(metadata, path)


def _markdown_targets(description: str) -> list[str]:
    matches = [*INLINE_TARGET_RE.finditer(description), *REFERENCE_TARGET_RE.finditer(description)]
    return [next(group for group in match.groups() if group is not None) for match in matches]


def _html_targets(description: str) -> list[str]:
    parser = _HTMLLinkParser()
    parser.feed(description)
    return parser.targets


def _is_pypi_safe_target(target: str) -> bool:
    if target.startswith("#"):
        return True

    parsed = urlsplit(target)
    if parsed.scheme in {"http", "https"}:
        return bool(parsed.netloc)
    if parsed.scheme == "mailto":
        return bool(parsed.path)
    return not parsed.scheme and bool(parsed.netloc)


def relative_targets(description: str) -> list[str]:
    targets = _markdown_targets(description) + _html_targets(description)
    return sorted({target for target in targets if not _is_pypi_safe_target(target)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="+", type=Path, help="Built wheel and sdist paths")
    args = parser.parse_args(argv)

    try:
        descriptions = {artifact: read_description(artifact) for artifact in args.artifacts}
    except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    failed = False
    for artifact, description in descriptions.items():
        targets = relative_targets(description)
        if targets:
            failed = True
            print(
                f"error: {artifact}: unsafe or repository-relative README targets are not PyPI-safe:",
                file=sys.stderr,
            )
            for target in targets:
                print(f"  - {target}", file=sys.stderr)

    unique_descriptions = set(descriptions.values())
    if len(unique_descriptions) != 1:
        failed = True
        print("error: wheel and sdist package descriptions differ", file=sys.stderr)

    if failed:
        return 1

    print(f"distribution README links OK: {len(descriptions)} artifact(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
