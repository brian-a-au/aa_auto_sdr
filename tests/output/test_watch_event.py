"""WatchEventEmitter — NDJSON-to-stdout for the aa-watch-event/v1 stream."""

from __future__ import annotations

import io
import json

import pytest

from aa_auto_sdr.output.watch_event import (
    WATCH_EVENT_SCHEMA,
    StdoutEmitter,
)


class TestSchemaConstant:
    def test_schema_string_is_versioned(self) -> None:
        assert WATCH_EVENT_SCHEMA == "aa-watch-event/v1"


class TestStdoutEmitter:
    def test_emits_one_json_object_per_line(self) -> None:
        buf = io.StringIO()
        emitter = StdoutEmitter(stream=buf)
        emitter.emit({"schema": WATCH_EVENT_SCHEMA, "event": "baseline", "cycle": 0})
        emitter.emit({"schema": WATCH_EVENT_SCHEMA, "event": "change", "cycle": 1})
        lines = buf.getvalue().rstrip("\n").split("\n")
        assert len(lines) == 2
        for line in lines:
            obj = json.loads(line)
            assert obj["schema"] == "aa-watch-event/v1"

    def test_flush_called_after_each_emit(self) -> None:
        flushes: list[int] = []

        class CountingStream(io.StringIO):
            def flush(self) -> None:
                flushes.append(1)
                super().flush()

        buf = CountingStream()
        emitter = StdoutEmitter(stream=buf)
        emitter.emit({"event": "baseline"})
        emitter.emit({"event": "change"})
        assert len(flushes) == 2

    def test_utf8_round_trip(self) -> None:
        buf = io.StringIO()
        emitter = StdoutEmitter(stream=buf)
        emitter.emit({"event": "change", "rsid": "rs_üñîçødé"})
        obj = json.loads(buf.getvalue().rstrip("\n"))
        assert obj["rsid"] == "rs_üñîçødé"

    def test_compact_separators_no_trailing_whitespace(self) -> None:
        buf = io.StringIO()
        emitter = StdoutEmitter(stream=buf)
        emitter.emit({"a": 1, "b": 2})
        line = buf.getvalue().rstrip("\n")
        assert ", " not in line
        assert ": " not in line

    def test_each_emit_ends_with_single_newline(self) -> None:
        buf = io.StringIO()
        emitter = StdoutEmitter(stream=buf)
        emitter.emit({"event": "baseline"})
        text = buf.getvalue()
        assert text.endswith("\n")
        assert not text.endswith("\n\n")

    def test_default_stream_is_sys_stdout(self) -> None:
        import sys

        from aa_auto_sdr.output.watch_event import StdoutEmitter as E

        emitter = E()
        assert emitter._stream is sys.stdout

    def test_emit_payload_is_dict_not_string(self) -> None:
        buf = io.StringIO()
        emitter = StdoutEmitter(stream=buf)
        with pytest.raises(TypeError):
            emitter.emit("not a dict")  # type: ignore[arg-type]
