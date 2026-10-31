"""Rebuild an SdrDocument from a saved capture, for `--render-from`.

Pure: takes an already-parsed dict, returns an SdrDocument, does no I/O.
Two input shapes are accepted:

- SDR JSON: the `--format json` output, i.e. `SdrDocument.to_dict()`.
- A snapshot envelope (`aa-sdr-snapshot/v1` through `v5`).

The capture's own `captured_at`, `tool_version`, scope
(`collected_components`), fetch status, and quality block are kept. Scope
that the input does not record stays unknown (None); it is never inferred
from empty arrays. The render time and the rendering tool version go on
`SdrDocument.rendered`.

Rows are validated at this boundary: every row must be an object with a
non-empty string `id`, ids must be unique within a family, every required
model field must be present, and every field present must have the model's
type. Envelope problems raise `SnapshotCorruptError` (or
`SnapshotSchemaError` for an unsupported schema); SDR JSON problems raise
`SdrPayloadError`.

The report-suite rsid names the output files, so it must be a plain
file-name token: no path separators, no `..`, no NUL, no leading dot. An
envelope's top-level `rsid` must also match `components.report_suite.rsid`."""

from __future__ import annotations

from dataclasses import MISSING, fields
from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Literal

from aa_auto_sdr.api import models
from aa_auto_sdr.core.exceptions import AaAutoSdrError, SdrPayloadError, SnapshotCorruptError
from aa_auto_sdr.sdr.document import COMPONENT_FAMILIES, FetchOutcomeMeta, RenderProvenance, SdrDocument

PayloadKind = Literal["sdr_json", "envelope"]

# Family name -> model class, in COMPONENT_FAMILIES order.
_FAMILY_MODELS: dict[str, type] = {
    "calculated_metrics": models.CalculatedMetric,
    "classifications": models.ClassificationDataset,
    "dimensions": models.Dimension,
    "metrics": models.Metric,
    "segments": models.Segment,
    "virtual_report_suites": models.VirtualReportSuite,
}

_FETCH_STATUSES = ("healthy", "partial", "degraded")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# Annotation string (models.py uses `from __future__ import annotations`) ->
# (type check, human type name). Every annotation in api/models.py must be here.
_TYPE_CHECKS: dict[str, tuple[Any, str]] = {
    "str": (lambda v: isinstance(v, str), "string"),
    "str | None": (lambda v: v is None or isinstance(v, str), "string or null"),
    "bool": (lambda v: isinstance(v, bool), "boolean"),
    "int": (_is_int, "int"),
    "int | None": (lambda v: v is None or _is_int(v), "int or null"),
    "list[str]": (lambda v: isinstance(v, list), "list"),
    "list[Any]": (lambda v: isinstance(v, list), "list"),
    "dict[str, Any]": (lambda v: isinstance(v, dict), "object"),
}


def payload_kind(payload: Any) -> PayloadKind:
    """Classify a parsed JSON value as SDR JSON or a snapshot envelope.

    An object carrying `schema` is an envelope (its schema is validated
    later). An object carrying `report_suite` is SDR JSON. Anything else
    raises `SdrPayloadError`."""
    if isinstance(payload, list):
        raise SdrPayloadError(
            "unrecognized payload shape: top-level JSON array (render one SDR document or snapshot at a time)"
        )
    if not isinstance(payload, dict):
        raise SdrPayloadError(f"unrecognized payload shape: expected a JSON object, got {type(payload).__name__}")
    if "schema" in payload:
        return "envelope"
    if "report_suite" in payload:
        return "sdr_json"
    raise SdrPayloadError(
        "unrecognized payload shape: expected SDR JSON (a 'report_suite' key) or a snapshot envelope (a 'schema' key)"
    )


def document_from_payload(
    payload: Any,
    *,
    rendered_at: datetime,
    rendering_tool_version: str,
) -> SdrDocument:
    """Rebuild an SdrDocument from either accepted shape."""
    rendered = RenderProvenance(rendered_at=rendered_at, tool_version=rendering_tool_version)
    if payload_kind(payload) == "envelope":
        return _from_envelope(payload, rendered=rendered)
    return _from_sdr_json(payload, rendered=rendered)


# --- shape-specific readers --------------------------------------------------


def _from_sdr_json(payload: dict[str, Any], *, rendered: RenderProvenance) -> SdrDocument:
    err = SdrPayloadError
    captured_at = _parse_captured_at(payload.get("captured_at"), err)
    tool_version = payload.get("tool_version")
    if not isinstance(tool_version, str) or not tool_version:
        raise err("SDR JSON 'tool_version' must be a non-empty string")
    report_suite = _report_suite(payload.get("report_suite"), err, fallback_rsid=None)
    families = {family: _rows(payload.get(family, []), family, err) for family in COMPONENT_FAMILIES}

    collected = _collected(payload.get("collected_components"), err)
    fetch_status = _sdr_json_fetch_status(payload.get("fetch_status", {}), err)
    _require_flagged_in_scope(fetch_status, collected, err)

    quality = payload.get("quality")
    if quality is not None and not isinstance(quality, dict):
        raise err("SDR JSON 'quality' must be an object or null")
    if quality is not None:
        _require_quality_parts(quality, err)

    return SdrDocument(
        report_suite=report_suite,
        captured_at=captured_at,
        tool_version=tool_version,
        fetch_status=fetch_status,
        quality=quality,
        collected_components=collected,
        rendered=rendered,
        **families,
    )



def _require_quality_parts(quality: dict[str, Any], err: type[AaAutoSdrError]) -> None:
    """Shape-check the quality parts the writers read, with the same rules
    snapshot `validate_envelope` applies: a part may be absent, but a
    present part must have the right type."""
    for key in ("naming_audit", "summary"):
        if key in quality and not isinstance(quality[key], dict):
            raise err(f"SDR JSON 'quality.{key}' must be an object")
    summary = quality.get("summary")
    if isinstance(summary, dict) and "by_severity" in summary and not isinstance(summary["by_severity"], dict):
        raise err("SDR JSON 'quality.summary.by_severity' must be an object")
    for key in ("stale_components", "issues"):
        if key in quality:
            rows = quality[key]
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise err(f"SDR JSON 'quality.{key}' must be a list of objects")

def _from_envelope(env: dict[str, Any], *, rendered: RenderProvenance) -> SdrDocument:
    # Lazy: the snapshot package is only needed for this shape.
    from aa_auto_sdr.snapshot.schema import validate_envelope

    err = SnapshotCorruptError
    validate_envelope(env)  # idempotent; defaults legacy keys in memory
    components = env["components"]
    rsid = env["rsid"]
    if not isinstance(rsid, str) or not rsid:
        raise err("snapshot 'rsid' must be a non-empty string")
    _require_safe_rsid(rsid, "rsid", err)
    tool_version = env["tool_version"]
    if not isinstance(tool_version, str) or not tool_version:
        raise err("snapshot 'tool_version' must be a non-empty string")
    report_suite = _report_suite(components.get("report_suite"), err, fallback_rsid=rsid)
    if report_suite.rsid != rsid:
        raise err(
            f"snapshot 'rsid' {rsid!r} does not match 'components.report_suite.rsid' {report_suite.rsid!r}",
        )
    families = {family: _rows(components.get(family, []), family, err) for family in COMPONENT_FAMILIES}

    # Scope is never defaulted: an envelope without the key has unknown scope.
    collected = _collected(env.get("collected_components"), err)
    fetch_status = _envelope_fetch_status(env["degraded_components"], env["partial_components"], err)
    _require_flagged_in_scope(fetch_status, collected, err)

    return SdrDocument(
        report_suite=report_suite,
        captured_at=_parse_captured_at(env["captured_at"], err),
        tool_version=tool_version,
        fetch_status=fetch_status,
        quality=env.get("quality"),
        collected_components=collected,
        rendered=rendered,
        **families,
    )


# --- shared validators -------------------------------------------------------


def _parse_captured_at(value: Any, err: type[AaAutoSdrError]) -> datetime:
    if not isinstance(value, str):
        raise err("'captured_at' must be an ISO-8601 timestamp string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise err(f"'captured_at' is not an ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise err(f"'captured_at' must carry a timezone offset: {value!r}")
    return parsed


def _report_suite(value: Any, err: type[AaAutoSdrError], *, fallback_rsid: str | None) -> models.ReportSuite:
    if value is None and fallback_rsid is not None:
        # Envelopes may omit the report_suite block; the envelope rsid is authoritative.
        return models.ReportSuite(
            rsid=fallback_rsid, name=fallback_rsid, timezone=None, currency=None, parent_rsid=None
        )
    if not isinstance(value, dict):
        raise err("'report_suite' must be an object")
    report_suite = _build_row(models.ReportSuite, value, "report_suite", err, id_field="rsid")
    _require_safe_rsid(report_suite.rsid, "report_suite.rsid", err)
    return report_suite


def _require_safe_rsid(rsid: str, field: str, err: type[AaAutoSdrError]) -> None:
    """The rsid becomes an output file name, so it must not be able to leave
    the output directory on any platform."""
    unsafe = (
        not rsid
        or "\x00" in rsid
        or "/" in rsid
        or "\\" in rsid
        or rsid.startswith(".")
        or ".." in rsid
        or PurePosixPath(rsid).name != rsid
        or PureWindowsPath(rsid).name != rsid
    )
    if unsafe:
        raise err(
            f"'{field}' {rsid!r} is not a plain file-name token (no path separators, '..', NUL, or leading '.')",
        )


def _rows(value: Any, family: str, err: type[AaAutoSdrError]) -> list[Any]:
    if not isinstance(value, list):
        raise err(f"'{family}' must be a list of objects")
    cls = _FAMILY_MODELS[family]
    out: list[Any] = []
    seen: set[str] = set()
    for index, row in enumerate(value):
        where = f"{family}[{index}]"
        if not isinstance(row, dict):
            raise err(f"{where} must be an object, got {type(row).__name__}")
        item = _build_row(cls, row, where, err, id_field="id")
        if item.id in seen:
            raise err(f"duplicate component id in {family}: {item.id!r}")
        seen.add(item.id)
        out.append(item)
    return out


def _build_row(cls: type, row: dict[str, Any], where: str, err: type[AaAutoSdrError], *, id_field: str) -> Any:
    ident = row.get(id_field)
    if not isinstance(ident, str) or not ident:
        raise err(f"{where} is missing a non-empty string '{id_field}'")
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        check, type_name = _TYPE_CHECKS[f.type]  # type: ignore[index]
        if f.name not in row:
            has_default = f.default is not MISSING or f.default_factory is not MISSING
            if has_default:
                continue
            if f.type.endswith("| None"):  # type: ignore[union-attr]
                kwargs[f.name] = None
                continue
            raise err(f"{where} ({ident!r}) is missing required field '{f.name}'")
        value = row[f.name]
        if not check(value):
            raise err(f"{where} ({ident!r}) field '{f.name}' must be {type_name}, got {type(value).__name__}")
        kwargs[f.name] = value
    # Keys the model does not know are ignored: they cannot be rendered.
    return cls(**kwargs)


def _collected(value: Any, err: type[AaAutoSdrError]) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise err("'collected_components' must be a list of family names or null")
    unknown = [name for name in value if not isinstance(name, str) or name not in COMPONENT_FAMILIES]
    if unknown:
        raise err(f"'collected_components' has unknown family names: {unknown!r}")
    if len(set(value)) != len(value):
        raise err("'collected_components' has duplicate family names")
    return tuple(sorted(value))


def _sdr_json_fetch_status(value: Any, err: type[AaAutoSdrError]) -> dict[str, FetchOutcomeMeta]:
    if not isinstance(value, dict):
        raise err("'fetch_status' must be an object")
    out: dict[str, FetchOutcomeMeta] = {}
    for family, meta in value.items():
        if family not in COMPONENT_FAMILIES:
            raise err(f"'fetch_status' names unknown family: {family!r}")
        if not isinstance(meta, dict):
            raise err(f"'fetch_status.{family}' must be an object")
        status = meta.get("status")
        if status not in _FETCH_STATUSES:
            raise err(f"'fetch_status.{family}.status' must be one of {list(_FETCH_STATUSES)}, got {status!r}")
        level = meta.get("expansion_level")
        if level is not None and not isinstance(level, str):
            raise err(f"'fetch_status.{family}.expansion_level' must be a string or null")
        out[family] = FetchOutcomeMeta(status=status, expansion_level=level)
    return out


def _envelope_fetch_status(degraded: Any, partial: Any, err: type[AaAutoSdrError]) -> dict[str, FetchOutcomeMeta]:
    out: dict[str, FetchOutcomeMeta] = {}
    for family in degraded:
        if not isinstance(family, str) or family not in COMPONENT_FAMILIES:
            raise err(f"degraded_components names unknown family: {family!r}")
        out[family] = FetchOutcomeMeta(status="degraded", expansion_level=None)
    for family, level in partial.items():
        if family not in COMPONENT_FAMILIES:
            raise err(f"partial_components names unknown family: {family!r}")
        if level is not None and not isinstance(level, str):
            raise err(f"partial_components.{family} expansion level must be a string or null")
        out[family] = FetchOutcomeMeta(status="partial", expansion_level=level)
    return out


def _require_flagged_in_scope(
    fetch_status: dict[str, FetchOutcomeMeta],
    collected: tuple[str, ...] | None,
    err: type[AaAutoSdrError],
) -> None:
    """A degraded or partial family was collected, so a known scope must list it."""
    if collected is None:
        return
    outside = sorted(f for f, meta in fetch_status.items() if meta.status != "healthy" and f not in collected)
    if outside:
        raise err(f"degraded or partial families missing from collected_components: {outside!r}")
