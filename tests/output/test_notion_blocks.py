"""Tests for the Notion block builder (pure functions, no API calls)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.output import notion_blocks as nb
from aa_auto_sdr.sdr.document import FetchOutcomeMeta, SdrDocument
from aa_auto_sdr.snapshot.schema import document_to_envelope


def _rs(
    rsid="examplersid1", name="Example RS", currency="USD", timezone_="America/Los_Angeles", parent_rsid=None
) -> models.ReportSuite:
    return models.ReportSuite(
        rsid=rsid,
        name=name,
        timezone=timezone_,
        currency=currency,
        parent_rsid=parent_rsid,
    )


def _make_doc(
    *,
    report_suite=None,
    dimensions=None,
    metrics=None,
    segments=None,
    calculated_metrics=None,
    virtual_report_suites=None,
    classifications=None,
    fetch_status=None,
) -> SdrDocument:
    return SdrDocument(
        report_suite=report_suite or _rs(),
        dimensions=dimensions or [],
        metrics=metrics or [],
        segments=segments or [],
        calculated_metrics=calculated_metrics or [],
        virtual_report_suites=virtual_report_suites or [],
        classifications=classifications or [],
        captured_at=datetime(2026, 5, 14, 10, 0, 0, tzinfo=UTC),
        tool_version="1.18.0",
        fetch_status=fetch_status or {},
        quality=None,
    )


def _make_metric(name="Page Views", id_="event1", type_="counter", description="Total page views") -> models.Metric:
    return models.Metric(
        id=id_,
        name=name,
        type=type_,
        category=None,
        precision=0,
        segmentable=True,
        description=description,
        tags=[],
        data_group=None,
        extra={},
    )


def _make_dimension(name="First eVar", id_="evar1", type_="string") -> models.Dimension:
    return models.Dimension(
        id=id_,
        name=name,
        type=type_,
        category=None,
        parent="evars",
        pathable=False,
        description=None,
        tags=[],
        extra={},
    )


# --- low-level block helpers ---------------------------------------------


def test_rich_text_returns_text_object():
    out = nb._rich_text("hello")
    assert out == [{"type": "text", "text": {"content": "hello"}}]


def test_rich_text_truncates_long_content_to_2000_chars_with_ellipsis():
    long = "x" * 5000
    out = nb._rich_text(long)
    content = out[0]["text"]["content"]
    assert len(content) == 2000
    assert content.endswith("…")


def test_heading2_block_type():
    blk = nb._heading2_block("Metrics")
    assert blk["type"] == "heading_2"
    assert blk["heading_2"]["rich_text"][0]["text"]["content"] == "Metrics"


def test_callout_block_default_emoji():
    blk = nb._callout_block("hi")
    assert blk["callout"]["icon"]["emoji"] == "📋"


def test_callout_block_custom_emoji():
    blk = nb._callout_block("hi", emoji="⚠️")
    assert blk["callout"]["icon"]["emoji"] == "⚠️"


def test_table_row_block_cell_structure():
    blk = nb._table_row_block(["a", "b"])
    assert blk["type"] == "table_row"
    assert blk["table_row"]["cells"][0][0]["text"]["content"] == "a"
    assert blk["table_row"]["cells"][1][0]["text"]["content"] == "b"


def test_table_block_has_header_row_plus_data_rows():
    blk = nb._table_block([["m1", "id1"], ["m2", "id2"]], ["Name", "ID"])
    assert blk["type"] == "table"
    children = blk["table"]["children"]
    # header + 2 rows
    assert len(children) == 3
    assert children[0]["table_row"]["cells"][0][0]["text"]["content"] == "Name"
    assert children[1]["table_row"]["cells"][0][0]["text"]["content"] == "m1"


def test_section_blocks_omitted_for_empty_component_list():
    assert nb._section_blocks("Metrics", ["Name"], []) == []


# --- top-level block builder --------------------------------------------


def test_section_blocks_present_when_rows_nonempty():
    out = nb._section_blocks("Metrics", ["Name"], [["m1"]])
    assert len(out) == 2
    assert out[0]["type"] == "heading_2"
    assert out[1]["type"] == "table"


def test_build_sdr_blocks_from_document_has_callout_divider_heading_table_paragraph():
    doc = _make_doc(metrics=[_make_metric()])
    blocks = nb.build_blocks_from_document(doc)
    types = [b["type"] for b in blocks]
    assert types[0] == "callout"  # metadata callout
    assert "divider" in types
    assert "heading_2" in types
    assert "table" in types
    assert types[-1] == "paragraph"  # footer


def test_build_sdr_blocks_omits_empty_sections():
    doc = _make_doc()  # nothing
    blocks = nb.build_blocks_from_document(doc)
    types = [b["type"] for b in blocks]
    assert "heading_2" not in types  # no section headings without rows
    assert "table" not in types


def test_fetch_status_callouts_show_severity_icon():
    doc = _make_doc(
        fetch_status={
            "virtual_report_suites": FetchOutcomeMeta(status="degraded", expansion_level=None),
        },
    )
    blocks = nb.build_blocks_from_document(doc)
    # Find the data-quality heading and following callouts
    headings = [b for b in blocks if b["type"] == "heading_2"]
    assert any(
        "Data Quality" in h["heading_2"]["rich_text"][0]["text"]["content"]
        or "Fetch Status" in h["heading_2"]["rich_text"][0]["text"]["content"]
        for h in headings
    )
    # at least one callout with the degraded emoji
    callouts = [b for b in blocks if b["type"] == "callout"]
    assert any(c["callout"]["icon"]["emoji"] == "⚠️" for c in callouts)


def test_metadata_callout_includes_rsid_name_captured_at_tool_version():
    doc = _make_doc()
    blocks = nb.build_blocks_from_document(doc)
    metadata = blocks[0]
    text = metadata["callout"]["rich_text"][0]["text"]["content"]
    assert "examplersid1" in text
    assert "Example RS" in text
    assert "2026-05-14" in text  # captured_at iso
    assert "1.18.0" in text  # tool_version


def test_metadata_callout_handles_none_currency_and_timezone():
    doc = _make_doc(report_suite=_rs(currency=None, timezone_=None))
    blocks = nb.build_blocks_from_document(doc)
    # Should not crash; rendering pinned to "—" for missing values
    text = blocks[0]["callout"]["rich_text"][0]["text"]["content"]
    assert "—" in text  # at least one missing field rendered as em dash


def test_build_sdr_blocks_from_dict_matches_from_document():
    doc = _make_doc(metrics=[_make_metric()], dimensions=[_make_dimension()])
    from_doc = nb.build_blocks_from_document(doc)
    from_dict = nb.build_blocks_from_dict(doc.to_dict())
    # Compare section ordering + cell content. Block list is the same shape.
    assert [b["type"] for b in from_doc] == [b["type"] for b in from_dict]
    # Heading content equality
    h2_doc = [b for b in from_doc if b["type"] == "heading_2"]
    h2_dict = [b for b in from_dict if b["type"] == "heading_2"]
    assert [h["heading_2"]["rich_text"][0]["text"]["content"] for h in h2_doc] == [
        h["heading_2"]["rich_text"][0]["text"]["content"] for h in h2_dict
    ]


def test_normalize_envelope_to_sdr_dict_unwraps_components():
    doc = _make_doc(metrics=[_make_metric()])
    envelope = document_to_envelope(doc)
    normalized = nb._normalize_payload(envelope)
    assert "report_suite" in normalized
    assert normalized["report_suite"]["rsid"] == "examplersid1"
    assert normalized["captured_at"] == envelope["captured_at"]


def test_normalize_envelope_synthesizes_fetch_status_from_degraded_and_partial():
    doc = _make_doc(
        fetch_status={
            "virtual_report_suites": FetchOutcomeMeta(status="degraded", expansion_level=None),
            "classifications": FetchOutcomeMeta(status="partial", expansion_level="ids_only"),
        },
    )
    envelope = document_to_envelope(doc)
    # The envelope strips fetch_status from the components payload — confirm
    # so the test guards against the real on-disk shape, not a mock.
    assert "fetch_status" not in envelope["components"]
    assert "virtual_report_suites" in envelope["degraded_components"]
    assert envelope["partial_components"]["classifications"] == "ids_only"

    normalized = nb._normalize_payload(envelope)
    fetch_status = normalized["fetch_status"]
    assert fetch_status["virtual_report_suites"]["status"] == "degraded"
    assert fetch_status["classifications"]["status"] == "partial"
    assert fetch_status["classifications"]["expansion_level"] == "ids_only"

    blocks = nb.build_blocks_from_dict(envelope)
    headings = [b for b in blocks if b["type"] == "heading_2"]
    assert any("Data Quality" in h["heading_2"]["rich_text"][0]["text"]["content"] for h in headings)
    warn_callouts = [b for b in blocks if b["type"] == "callout" and b["callout"]["icon"]["emoji"] == "⚠️"]
    assert len(warn_callouts) >= 2


def test_normalize_payload_accepts_sdr_dict_as_is():
    doc = _make_doc()
    d = doc.to_dict()
    out = nb._normalize_payload(d)
    assert out is d  # returned as-is


def test_normalize_payload_raises_on_unknown_shape():
    with pytest.raises(ValueError, match="Unrecognized"):
        nb._normalize_payload({"hello": "world"})


def test_section_with_more_than_99_rows_splits_into_multiple_tables():
    # Notion caps block children at 100 per request; a single table holds at
    # most 99 data rows + 1 header. Suites with hundreds of dimensions/metrics
    # must split into multiple sibling tables under the same heading.
    metrics = [_make_metric(name=f"m{i}", id_=f"event{i}") for i in range(250)]
    doc = _make_doc(metrics=metrics)
    blocks = nb.build_blocks_from_document(doc)

    metrics_heading_idx = next(
        i
        for i, b in enumerate(blocks)
        if b["type"] == "heading_2" and "Metrics" in b["heading_2"]["rich_text"][0]["text"]["content"]
    )
    # Walk forward and collect tables until the next non-table sibling.
    tables_after_heading = []
    for b in blocks[metrics_heading_idx + 1 :]:
        if b["type"] != "table":
            break
        tables_after_heading.append(b)

    # 250 rows → 99 + 99 + 52, so three tables under one heading.
    assert len(tables_after_heading) == 3
    for tbl in tables_after_heading:
        children = tbl["table"]["children"]
        assert len(children) <= 100  # Notion's hard cap
        # Each chunk repeats the header row so rows stay readable.
        assert children[0]["table_row"]["cells"][0][0]["text"]["content"] == "Name"


def test_section_with_exactly_99_rows_stays_single_table():
    metrics = [_make_metric(name=f"m{i}", id_=f"event{i}") for i in range(99)]
    doc = _make_doc(metrics=metrics)
    blocks = nb.build_blocks_from_document(doc)
    tables = [b for b in blocks if b["type"] == "table"]
    assert len(tables) == 1
    assert len(tables[0]["table"]["children"]) == 100  # 99 data + 1 header


def test_table_cell_truncated_at_2000_chars():
    doc = _make_doc(metrics=[_make_metric(description="d" * 5000)])
    blocks = nb.build_blocks_from_document(doc)
    table = next(b for b in blocks if b["type"] == "table")
    # Data row (index 1); find description column
    row_cells = table["table"]["children"][1]["table_row"]["cells"]
    contents = [c[0]["text"]["content"] for c in row_cells]
    long = next(c for c in contents if c.startswith("d"))
    assert len(long) == 2000
    assert long.endswith("…")
