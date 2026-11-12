"""Excel workbook parity: every part of the zip matches a recorded reference.

The reference in `tests/fixtures/excel_parity.json` maps each zip member to the
sha256 of its bytes, for four fixed documents. It pins the workbook the Excel
writer produces, so a change to how the writer builds the file (not to what it
puts in it) must leave every hash the same.

`docProps/core.xml` is left out: it holds the workbook's created and modified
timestamps, which xlsxwriter sets to the time of the write. No other member
carries a time, a path, or a random value.

The hashes are the same on every supported Python version and xlsxwriter
version (checked on Python 3.11 to 3.15, xlsxwriter 3.2.9 and 3.3.1). The
reference was recorded from the earlier pandas-based writer under pandas 3.

To record the reference again after an intended output change, run this test
with `AA_RECORD_EXCEL_PARITY=1` and review the fixture diff."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aa_auto_sdr.api import models as m
from aa_auto_sdr.output.writers.excel import ExcelWriter
from aa_auto_sdr.sdr.document import COMPONENT_FAMILIES, FetchOutcomeMeta, RenderProvenance, SdrDocument

FIXTURE = Path(__file__).parent.parent / "fixtures" / "excel_parity.json"
RECORD_ENV = "AA_RECORD_EXCEL_PARITY"
# Created / modified timestamps of the write. Nothing else is excluded.
EXCLUDED_MEMBERS = frozenset({"docProps/core.xml"})

CAPTURED = datetime(2026, 4, 25, 17, 30, tzinfo=UTC)
RENDERED = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)

LONG = "L" * 40_000  # past Excel's 32,767-character cell limit
ADVERSARIAL = [
    '=HYPERLINK("x")',
    "+1",
    "-2",
    "@SUM(A1)",
    "#N/A",
    "https://example.com/path?q=1&r=2",
    "mailto:someone@example.com",
    "0042",
    "1e5",
    "café 日本 😀 𝄞",
    "line1\nline2\r\nline3",
    "tab\tseparated",
    "  padded  ",
    "",
    "bell\x07char",
    LONG,
]


def _dimensions() -> list[m.Dimension]:
    dims = [
        m.Dimension(
            id=f"variables/evar{i}",
            name=f"eVar {i}",
            type="string",
            category="Conversion",
            parent="",
            pathable=False,
            description=f"desc {i}",
            tags=["a|b"],
            extra={"k": [1, 2]},
        )
        for i in range(1, 4)
    ]
    # One row per adversarial value, spread over name / category / description.
    for n, value in enumerate(ADVERSARIAL):
        dims.append(
            m.Dimension(
                id=f"variables/prop{n}",
                name=value,
                type="string",
                category=None if n % 3 == 0 else value,
                parent=value,
                pathable=n % 2 == 0,
                description=None if n % 4 == 0 else value,
                tags=[value] if n % 2 else [],
                extra={"v": value, "n": None} if n % 5 == 0 else {},
            )
        )
    return dims


def _metrics() -> list[m.Metric]:
    return [
        m.Metric(
            id="metrics/visits",
            name="Visits",
            type="int",
            category="Traffic",
            precision=0,
            segmentable=True,
            description=None,
        ),
        m.Metric(
            id="metrics/orders",
            name="Orders",
            type="int",
            category="Commerce",
            precision=0,
            segmentable=True,
            description="#N/A",
            data_group="Commerce",
        ),
        m.Metric(
            id="metrics/revenue",
            name="=1+1",
            type="currency",
            category=None,
            precision=2,
            segmentable=False,
            description="  revenue  ",
            tags=["money"],
            extra={"polarity": "positive"},
        ),
    ]


_SEGMENT_DEF = {
    "func": "segment",
    "version": [1, 0, 0],
    "container": {
        "func": "container",
        "context": "hits",
        "pred": {"func": "streq", "str": "Mobile Phone", "val": {"func": "attr", "name": "variables/evar1"}},
    },
}
_NESTED_SEGMENT_DEF = {
    "func": "segment",
    "version": [1, 0, 0],
    "container": {
        "func": "container",
        "context": "visits",
        "pred": {
            "func": "and",
            "preds": [
                {"func": "event-exists", "evt": {"func": "event", "name": "metrics/orders"}},
                {"func": "segment", "segment_id": "s_mobile"},
                {"func": "segment", "segment_id": "s_missing"},
            ],
        },
    },
}


def _segments() -> list[m.Segment]:
    return [
        m.Segment(
            id="s_mobile",
            name="Mobile hits",
            description="https://example.com/a",
            rsid="rs1",
            owner_id=1,
            definition=_SEGMENT_DEF,
            compatibility={"supported_products": ["oberon"]},
            tags=["mobile"],
            created="2026-01-01T00:00:00Z",
            modified="2026-02-01T00:00:00Z",
        ),
        m.Segment(
            id="s_engaged",
            name='=HYPERLINK("x")',
            description="line1\nline2",
            rsid="rs1",
            owner_id=None,
            definition=_NESTED_SEGMENT_DEF,
        ),
        m.Segment(
            id="s_empty",
            name="",
            description=None,
            rsid="rs1",
            owner_id=2,
            definition={},
            extra={"big": "x" * 500},
        ),
    ]


def _calculated_metrics() -> list[m.CalculatedMetric]:
    ratio = {
        "func": "calc-metric",
        "version": [1, 0, 0],
        "formula": {
            "func": "divide",
            "col1": {"func": "metric", "name": "metrics/orders"},
            "col2": {"func": "metric", "name": "metrics/visits"},
        },
    }
    nested = {
        "func": "calc-metric",
        "version": [1, 0, 0],
        "formula": {
            "func": "multiply",
            "col1": {"func": "segment", "segment_id": "s_mobile", "metric": {"func": "metric", "name": "cm_ratio"}},
            "col2": {"func": "metric", "name": "metrics/unknown"},
        },
    }
    return [
        m.CalculatedMetric(
            id="cm_ratio",
            name="Conversion rate",
            description="Orders / Visits",
            rsid="rs1",
            owner_id=1,
            polarity="positive",
            precision=2,
            type="percent",
            definition=ratio,
            tags=["kpi"],
            categories=["Commerce"],
        ),
        m.CalculatedMetric(
            id="cm_nested",
            name="+Nested",
            description=None,
            rsid="rs1",
            owner_id=None,
            polarity="negative",
            precision=0,
            type="decimal",
            definition=nested,
        ),
        m.CalculatedMetric(
            id="cm_bad",
            name="Bad formula",
            description="",
            rsid="rs1",
            owner_id=3,
            polarity="positive",
            precision=1,
            type="decimal",
            definition={"formula": "not-a-dict"},
        ),
    ]


def _virtual_report_suites() -> list[m.VirtualReportSuite]:
    return [
        m.VirtualReportSuite(
            id="vrs_mobile",
            name="Mobile VRS",
            parent_rsid="rs1",
            timezone="UTC",
            description=None,
            segment_list=["s_mobile"],
            curated_components=[{"id": "metrics/visits", "type": "metric"}],
            modified="2026-03-01T00:00:00Z",
        ),
        m.VirtualReportSuite(
            id="vrs_other",
            name="#N/A",
            parent_rsid="rs1",
            timezone=None,
            description="  spaced  ",
            segment_list=["s_missing", "s_engaged"],
        ),
    ]


def _classifications() -> list[m.ClassificationDataset]:
    return [
        m.ClassificationDataset(id="cls1", name="Campaign", rsid="rs1"),
        m.ClassificationDataset(id="cls2", name="Product 😀", rsid="rs1", extra={"dimension": "variables/evar1"}),
        m.ClassificationDataset(id="cls3", name="", rsid="rs1"),
    ]


def _issue(**fields) -> dict:
    base = {
        "severity": "LOW",
        "category": "naming",
        "type": "case_inconsistency",
        "item_id": "naming_audit",
        "item_name": "",
        "issue": "Mixed case styles detected.",
        "details": {},
        "rule_id": "dq.naming_case_inconsistency.v1",
        "component_ids": [],
        "occurrences": 1,
        "excepted": False,
        "exception_reason": None,
    }
    base.update(fields)
    return base


_NAMING_AUDIT = {
    "total_components": 22,
    "case_styles": {"snake_case": 3, "camelCase": 0, "PascalCase": 4, "other": 15},
    "prefix_groups": {"evar": 3, "prop": 16},
    "recommendations": ["Mixed case styles detected. Consider standardizing on a single style."],
}
_STALE = [
    {"id": "variables/evar1", "name": "eVar 1", "type": "dimension", "reasons": ["stale_keyword:legacy"]},
]
_ISSUES = [
    _issue(
        severity="MEDIUM",
        category="stale",
        type="stale_keyword",
        item_id="variables/evar1",
        item_name="eVar 1",
        issue="Component name matches stale_keyword pattern: legacy",
        details={"component_type": "dimension", "reason": "stale_keyword:legacy"},
        rule_id="dq.stale_keyword.v1",
        component_ids=["variables/evar1"],
        excepted=True,
        exception_reason="kept for audit trail",
    ),
    _issue(component_ids=[f"variables/prop{n}" for n in range(55)], occurrences=55),
    _issue(
        severity="HIGH",
        type="naming_convention",
        item_id="variables/prop0",
        item_name='=HYPERLINK("x")',
        issue="Name does not follow the dimensions naming rule:\nexpected snake_case",
        details={"component_type": "dimension", "violations": ["case"], "expected_case": "snake_case"},
        rule_id="dq.naming_convention.v1",
        component_ids=["variables/prop0"],
        occurrences=None,
    ),
    _issue(
        severity="INFO",
        category="stale",
        type="version_suffix",
        item_id="s_engaged",
        item_name="tab\tname 😀",
        issue="  version suffix  ",
        details={"reason": "version_suffix:v2"},
        rule_id=None,  # derived from `type` for older blocks
        excepted=True,
        exception_reason="",
    ),
]


def _base(**changes) -> SdrDocument:
    fields = {
        "report_suite": m.ReportSuite(
            rsid="rs1",
            name='=HYPERLINK("x") café 😀',
            timezone=None,
            currency="USD",
            parent_rsid=None,
        ),
        "dimensions": _dimensions(),
        "metrics": _metrics(),
        "segments": _segments(),
        "calculated_metrics": _calculated_metrics(),
        "virtual_report_suites": _virtual_report_suites(),
        "classifications": _classifications(),
        "captured_at": CAPTURED,
        "tool_version": "9.9.9",
        "collected_components": COMPONENT_FAMILIES,
    }
    fields.update(changes)
    return SdrDocument(**fields)


def _documents() -> dict[str, SdrDocument]:
    """Four documents that between them reach every branch of the writer."""
    gated = {
        "naming_audit": _NAMING_AUDIT,
        "stale_components": _STALE,
        "issues": _ISSUES,
        "summary": {
            "by_severity": {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 0, "LOW": 1, "INFO": 0},
            "total": 2,
            "excepted": 2,
            "verdict": "fail",
            "policy_threshold": "LOW",
        },
    }
    # No gate policy, no summary block: counts derive from the issues.
    ungated = {
        "naming_audit": _NAMING_AUDIT,
        "stale_components": _STALE,
        "issues": [i for i in _ISSUES if not i["excepted"]],
    }
    return {
        # Every family populated, a gate verdict with excepted findings.
        "full": _base(quality=gated),
        # Render provenance rows, one empty family, a degraded and a partial
        # fetch, an excluded family, quality without a gate.
        "rendered": _base(
            metrics=[],
            classifications=[],
            fetch_status={
                "virtual_report_suites": FetchOutcomeMeta(status="partial", expansion_level="minimal"),
                "classifications": FetchOutcomeMeta(status="degraded", expansion_level=None),
            },
            collected_components=tuple(f for f in COMPONENT_FAMILIES if f != "metrics"),
            quality=ungated,
            rendered=RenderProvenance(rendered_at=RENDERED, tool_version="10.0.0"),
        ),
        # An audit that found nothing: the issues table is a header row only.
        "clean": _base(
            quality={
                "naming_audit": _NAMING_AUDIT,
                "stale_components": [],
                "issues": [],
                "summary": {
                    "by_severity": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0},
                    "total": 0,
                    "excepted": 0,
                    "verdict": "pass",
                    "policy_threshold": "HIGH",
                },
            },
        ),
        # No audit ran, scope unknown, no references.
        "unaudited": _base(
            segments=[],
            calculated_metrics=[],
            virtual_report_suites=[],
            collected_components=None,
            quality=None,
        ),
    }


def _posix_bytes(data: bytes) -> bytes:
    """xlsxwriter writes each XML part in text mode, so on Windows every "\n"
    it writes becomes "\r\n" (the old pandas-based writer did the same). The
    reference hashes were recorded on POSIX. Every "\n" in a translated part
    is preceded by an inserted "\r", so replacing "\r\n" with "\n" restores
    the POSIX bytes exactly, including a "\r\n" that was part of a cell value."""
    if os.linesep == "\r\n":
        return data.replace(b"\r\n", b"\n")
    return data


def _member_hashes(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        return {
            name: hashlib.sha256(_posix_bytes(archive.read(name))).hexdigest()
            for name in sorted(archive.namelist())
            if name not in EXCLUDED_MEMBERS
        }


def _actual(tmp_path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for name, doc in _documents().items():
        (path,) = ExcelWriter().write(doc, tmp_path / f"{name}.xlsx")
        out[name] = _member_hashes(path)
    return out


@pytest.mark.filterwarnings("ignore:Cell contents too long:UserWarning")
def test_workbook_parts_match_reference(tmp_path: Path) -> None:
    actual = _actual(tmp_path)
    if os.environ.get(RECORD_ENV):
        FIXTURE.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        pytest.skip(f"recorded {FIXTURE.name}; unset {RECORD_ENV} to compare")
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert sorted(actual) == sorted(expected)
    for name in expected:
        differing = sorted(
            member
            for member in set(actual[name]) | set(expected[name])
            if actual[name].get(member) != expected[name].get(member)
        )
        assert differing == [], f"{name}.xlsx: members differ from the reference: {differing}"


@pytest.mark.filterwarnings("ignore:Cell contents too long:UserWarning")
def test_only_core_xml_varies_between_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two writes at different clock times differ in docProps/core.xml only."""
    import xlsxwriter.core

    doc = _documents()["full"]
    first = tmp_path / "a.xlsx"
    second = tmp_path / "b.xlsx"
    ExcelWriter().write(doc, first)
    # xlsxwriter stamps core.xml with the current time; move the clock on.
    real_datetime = xlsxwriter.core.datetime

    class _Later(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2030, 1, 2, 3, 4, 5, tzinfo=tz)

        @classmethod
        def utcnow(cls):
            return real_datetime(2030, 1, 2, 3, 4, 5)

    monkeypatch.setattr(xlsxwriter.core, "datetime", _Later)
    ExcelWriter().write(doc, second)
    with zipfile.ZipFile(first) as a, zipfile.ZipFile(second) as b:
        assert sorted(a.namelist()) == sorted(b.namelist())
        differing = [name for name in a.namelist() if a.read(name) != b.read(name)]
    assert differing == ["docProps/core.xml"]


def test_long_cell_warns_like_before(tmp_path: Path) -> None:
    """A cell past 32,767 characters still raises the UserWarning pandas 3 raised."""
    doc = _documents()["unaudited"]
    with pytest.warns(UserWarning, match="Cell contents too long, truncated to 32767 characters"):
        ExcelWriter().write(doc, tmp_path / "long.xlsx")


def test_excel_module_and_write_do_not_import_pandas(tmp_path: Path) -> None:
    """Importing the writer and writing a workbook leave pandas unloaded."""
    script = f"""
import sys, warnings
warnings.simplefilter("ignore")
sys.path.insert(0, {str(Path(__file__).parent)!r})
import aa_auto_sdr.output.writers.excel as excel
assert "pandas" not in sys.modules, "import loaded pandas"
from test_writer_excel_parity import _documents
for name, doc in _documents().items():
    excel.ExcelWriter().write(doc, __import__("pathlib").Path({str(tmp_path)!r}) / (name + ".xlsx"))
assert "xlsxwriter" in sys.modules
assert "pandas" not in sys.modules, "write loaded pandas"
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert len(list(tmp_path.glob("*.xlsx"))) == 4


class _RecordingSheet:
    def __init__(self) -> None:
        self.cells: dict[tuple[int, int], object] = {}

    def write(self, row: int, col: int, value: object) -> None:
        self.cells[(row, col)] = value


def test_table_cells_follow_the_pandas_writer_rules() -> None:
    """None and "" leave a cell empty, other values are written, and widths use str()."""
    from aa_auto_sdr.output.writers import excel

    ws = _RecordingSheet()
    with pytest.warns(UserWarning, match="Cell contents too long"):
        excel._write_cell(ws.write, 0, 0, "x" * 32_768)
    excel._write_cell(ws.write, 0, 1, None)
    excel._write_cell(ws.write, 0, 2, 7)
    excel._write_cell(ws.write, 0, 3, "")
    assert sorted(ws.cells) == [(0, 0), (0, 2)]

    ws = _RecordingSheet()
    longest = excel._write_table(ws, 2, ["a", "b"], [[None, 12345], ["", "xy"]])
    assert ws.cells == {(2, 0): "a", (2, 1): "b", (3, 1): 12345, (4, 1): "xy"}
    # None counts as "None" (4), as pandas' str() of an object cell did.
    assert longest == [4, 5]


def test_oversized_table_raises_like_pandas() -> None:
    from aa_auto_sdr.output.writers import excel

    excel._check_size(2**20, 2**14)
    with pytest.raises(ValueError, match=r"This sheet is too large! Your sheet size is: 1048577, 1 "):
        excel._check_size(2**20 + 1, 1)
    with pytest.raises(ValueError, match="Max sheet size is: 1048576, 16384"):
        excel._check_size(1, 2**14 + 1)
