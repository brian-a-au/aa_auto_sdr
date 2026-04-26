"""Shared helpers for output writers — stringification + escaping."""

from aa_auto_sdr.output._helpers import escape_html, escape_pipe, stringify_cell


def test_stringify_none_returns_empty_string() -> None:
    assert stringify_cell(None) == ""


def test_stringify_bool_returns_lowercase_word() -> None:
    assert stringify_cell(True) == "true"
    assert stringify_cell(False) == "false"


def test_stringify_int_and_float() -> None:
    assert stringify_cell(42) == "42"
    assert stringify_cell(3.14) == "3.14"


def test_stringify_string_passthrough() -> None:
    assert stringify_cell("hello") == "hello"


def test_stringify_empty_string_passthrough() -> None:
    assert stringify_cell("") == ""


def test_stringify_dict_emits_compact_sorted_json() -> None:
    result = stringify_cell({"b": 2, "a": 1})
    assert result == '{"a": 1, "b": 2}'


def test_stringify_list_emits_compact_json() -> None:
    assert stringify_cell([1, 2, 3]) == "[1, 2, 3]"


def test_stringify_nested_dict() -> None:
    result = stringify_cell({"x": {"y": [1, 2]}})
    assert result == '{"x": {"y": [1, 2]}}'


def test_escape_pipe_replaces_pipe_with_backslash_pipe() -> None:
    assert escape_pipe("a|b|c") == r"a\|b\|c"


def test_escape_pipe_replaces_newline_with_br() -> None:
    assert escape_pipe("line1\nline2") == "line1<br>line2"


def test_escape_pipe_handles_both_at_once() -> None:
    assert escape_pipe("a|b\nc|d") == r"a\|b<br>c\|d"


def test_escape_html_escapes_special_chars() -> None:
    assert escape_html("<script>") == "&lt;script&gt;"


def test_escape_html_escapes_quotes() -> None:
    # Pythons html.escape with quote=True escapes both " and '
    assert escape_html('a "b" c') == "a &quot;b&quot; c"


def test_escape_html_passthrough_safe_text() -> None:
    assert escape_html("hello world") == "hello world"
