"""Runs the shared cases of the Adobe credentials standard against this tool.

This module is the tool's adapter. It reads the case files in
`tests/standard_cases/`, builds each case in a temporary home and working
folder, runs the lookup or the command, and checks `expect`. No case calls
Adobe: the sign-in request and the SDK are replaced.

`known-differences.json` at the repo root lists the cases the tool does not
pass yet. Those cases must fail here and every other case must pass. A listed
case that starts to pass fails the run, so the list can only get shorter.

To update the case files, run `sync_cases.py` from the standards repo with
`tests/standard_cases` as the destination.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.api import sign_in
from aa_auto_sdr.cli.main import run
from aa_auto_sdr.core import credentials, profiles
from aa_auto_sdr.core.exceptions import ConfigError

TOOL = "aa_auto_sdr"
PRODUCT = "aa"
PROFILE_VARIABLE = "AA_PROFILE"

_REPO = Path(__file__).resolve().parent.parent
_CASES_DIR = _REPO / "tests" / "standard_cases"
_CASE_FILES = (
    "config-check.json",
    "lookup-order.json",
    "masking.json",
    "partial-sources.json",
    "permissions.json",
    "profile-names.json",
    "sign-in-codes.json",
    "variable-forms.json",
)
_FIXTURES = json.loads((_CASES_DIR / "fixtures.json").read_text(encoding="utf-8"))["credentials"]
_KNOWN = json.loads((_REPO / "known-differences.json").read_text(encoding="utf-8"))
_EXPECTED_TO_FAIL = {case_id for diff in _KNOWN["differences"] for case_id in diff.get("cases", [])}
# Commands this tool does not have. The rule is under `not_applicable` in known-differences.json.
_COMMANDS_NOT_IN_THIS_TOOL = {"run_child"}


def _load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for name in _CASE_FILES:
        data = json.loads((_CASES_DIR / name).read_text(encoding="utf-8"))
        cases.extend({**case, "area": data["area"]} for case in data["cases"])
    return cases


_CASES = _load_cases()


def _skip_reason(case: dict[str, Any]) -> str | None:
    if "products" in case and PRODUCT not in case["products"]:
        return "the case is for another product"
    if "tools" in case and TOOL not in case["tools"]:
        return "the case is for another tool"
    if case["given"].get("command") in _COMMANDS_NOT_IN_THIS_TOOL:
        return "the tool has no such command"
    if case["area"] == "permissions" and os.name == "nt":
        return "mode bits do not describe access on Windows"
    return None


# --- the JSON shapes -------------------------------------------------------


def _type_ok(value: Any, name: str) -> bool:
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "string":
        return isinstance(value, str)
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, dict)
    raise AssertionError(f"type {name} is not handled by this check")


def check_shape(value: Any, schema: dict[str, Any], where: str = "$") -> None:
    """A small JSON Schema check for the keywords the two shapes use.

    The repo has no JSON Schema library as a dependency, so this covers
    `type`, `const`, `enum`, `required`, `properties`, `items` and
    `not: {required: [...]}`. Any other keyword in a shape fails the test, so
    a change to the shapes cannot pass without a look at this check."""
    handled = {"type", "const", "enum", "required", "properties", "items", "not", "additionalProperties"}
    ignored = {"$schema", "$id", "title", "description"}
    unknown = set(schema) - handled - ignored
    assert not unknown, f"{where}: schema keywords not handled: {sorted(unknown)}"
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        assert any(_type_ok(value, t) for t in types), f"{where}: {value!r} is not of type {types}"
    if "const" in schema:
        assert value == schema["const"], f"{where}: {value!r} is not {schema['const']!r}"
    if "enum" in schema:
        assert value in schema["enum"], f"{where}: {value!r} is not one of {schema['enum']}"
    if "not" in schema:
        assert set(schema["not"]) == {"required"}, f"{where}: only not/required is handled"
        assert not all(key in value for key in schema["not"]["required"]), f"{where}: holds a forbidden key"
    if isinstance(value, dict):
        for key in schema.get("required", []):
            assert key in value, f"{where}: required key {key!r} is missing"
        assert schema.get("additionalProperties", True) is True, f"{where}: closed objects are not handled"
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                check_shape(value[key], sub, f"{where}.{key}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            check_shape(item, schema["items"], f"{where}[{index}]")


def _shape(name: str) -> dict[str, Any]:
    return json.loads((_CASES_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


# --- building a case -------------------------------------------------------


def _credential(spec: dict[str, Any]) -> dict[str, str]:
    cred = dict(_FIXTURES[spec["credential"]]) if "credential" in spec else {}
    for name in spec.get("omit", []):
        cred.pop(name)
    cred.update(spec.get("override", {}))
    return cred


def _write_json(path: Path, spec: dict[str, Any]) -> None:
    """Write a credential file. The mode is 0600 unless the case gives one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    target = path
    if spec.get("through_symlink"):
        target = path.parent / "real" / path.name
        target.parent.mkdir()
        path.symlink_to(target)
    target.write_text(json.dumps({**_credential(spec), **spec.get("extra_keys", {})}), encoding="utf-8")
    target.chmod(int(spec.get("file_mode", "0600"), 8))


class World:
    """One case built in a temporary home and working folder."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.home = tmp_path / "home"
        self.work = tmp_path / "parent" / "work"
        self.home.mkdir()
        self.work.mkdir(parents=True)
        self.extra = tmp_path / "extra"
        self.monkeypatch = monkeypatch
        self.profile: str | None = None
        self.config: Path | None = None
        monkeypatch.setenv("HOME", str(self.home))
        monkeypatch.chdir(self.work)

    @property
    def orgs(self) -> Path:
        return self.home / ".aa" / "orgs"

    def write_profile(self, spec: dict[str, Any]) -> None:
        if "credential" in spec:
            _write_json(self.orgs / spec["name"] / "config.json", spec)

    def build(self, sources: dict[str, Any]) -> None:
        for kind, spec in sources.items():
            if kind == "flag_profile":
                self.write_profile(spec)
                self.profile = spec["name"]
            elif kind == "flag_config":
                self.config = self.extra / "credential.json"
                _write_json(self.config, spec)
            elif kind == "profile_variable":
                self.write_profile(spec)
                self.monkeypatch.setenv(PROFILE_VARIABLE, spec["name"])
            elif kind == "profile_variable_target":
                self.write_profile(spec)
            elif kind == "environment":
                for name, value in _credential(spec).items():
                    self.monkeypatch.setenv(name.upper(), value)
                if spec.get("other_settings"):
                    self.monkeypatch.setenv("LOG_LEVEL", "INFO")
            elif kind == "dotenv":
                folder = self.work.parent if spec.get("location") == "parent_folder" else self.work
                lines = [f"{name.upper()}={value}" for name, value in _credential(spec).items()]
                for name, value in spec.get("extra_keys", {}).items():
                    lines.append(f"{PROFILE_VARIABLE if name == 'PROFILE_VARIABLE' else name}={value}")
                path = folder / ".env"
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                path.chmod(0o600)
            elif kind == "default_config":
                _write_json(self.work / "config.json", spec)
            else:
                raise AssertionError(f"source {kind} is not handled by the adapter")

    def flags(self) -> list[str]:
        out: list[str] = []
        if self.profile is not None:
            out += ["--profile", self.profile]
        if self.config is not None:
            out += ["--config", str(self.config)]
        return out


def _shows_secret(secret: str, text: str) -> bool:
    """True when `text` holds 4 characters in a row from the secret.

    The made-up secrets are built from plain words, e.g. "secret" and
    "credential", which any output about credentials holds. So the check uses
    the runs that belong to this secret alone: a run that is also in another
    made-up secret, or that is digits only, is left out."""
    others = [cred["secret"] for cred in _FIXTURES.values() if cred["secret"] != secret]
    runs = {secret[i : i + 4] for i in range(len(secret) - 3)}
    own = {run for run in runs if not run.isdigit() and not any(run in other for other in others)}
    assert own, "the secret has no run of its own to look for"
    return secret in text or any(run in text for run in own)


def _has_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_has_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_has_key(item, key) for item in value)
    return False


# --- the checks ------------------------------------------------------------


def _check_lookup(case: dict[str, Any], world: World) -> None:
    expect = case["expect"]
    found = credentials.lookup(profile=world.profile, config=world.config)
    if "error" in expect:
        assert found.error is not None, "the lookup gave a credential"
        assert found.error.code == expect["error"]
        if "missing" in expect:
            assert sorted(found.error.missing) == sorted(expect["missing"])
        with pytest.raises(ConfigError):
            credentials.resolve(profile=world.profile, config=world.config)
        return
    assert found.error is None, f"the lookup failed: {found.error}"
    assert found.used is not None
    assert found.used.kind == expect["source"]
    wanted = _FIXTURES[expect["credential"]]
    got = credentials.resolve(profile=world.profile, config=world.config)
    assert {name: getattr(got, name) for name in wanted} == wanted


def _run_cli(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    capsys.readouterr()
    code = run(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _check_config_check(case: dict[str, Any], world: World, capsys: pytest.CaptureFixture[str]) -> None:
    expect = case["expect"]
    argv = ["--config-status", "--format", "json", *world.flags()]
    if "debug" in expect:
        argv += ["--log-level", "DEBUG"]
    code, out, err = _run_cli(argv, capsys)
    report = json.loads(out)
    check_shape(report, _shape("config-check-v1"))
    used = [source for source in report["sources"] if source["used"]]
    stderr_lines = err.splitlines()

    assert code == (0 if report["ok"] else 10)
    if "ok" in expect:
        assert report["ok"] is expect["ok"]
    if "source" in expect:
        assert [source["kind"] for source in used] == [expect["source"]]
    if "profile" in expect:
        assert report["profile"] == expect["profile"]
    if "client_id" in expect:
        assert report["credential"]["client_id"] == expect["client_id"]
    if "secret_set" in expect:
        assert report["credential"]["secret_set"] is expect["secret_set"]
    if expect.get("has_no_secret_field"):
        assert not _has_key(report, "secret")
    if "scopes" in expect:
        assert report["credential"]["scopes"] == expect["scopes"]
    if "skipped_source" in expect:
        skipped = [s for s in report["sources"] if s["kind"] == expect["skipped_source"]]
        assert len(skipped) == 1
        assert skipped[0]["skipped"] == "partial"
        assert skipped[0]["used"] is False
        assert sorted(skipped[0]["missing"]) == sorted(expect["missing"])
    if "problem" in expect:
        assert expect["problem"] in [problem["code"] for problem in report["problems"]]
    if "error" in expect:
        assert report["ok"] is False
        assert expect["error"] in [problem["code"] for problem in report["problems"]]
    notice_codes = [notice["code"] for notice in report["notices"]]
    if "notice" in expect:
        assert expect["notice"] in notice_codes
        notice = next(n for n in report["notices"] if n["code"] == expect["notice"])
        # The notice is also one line on stderr, and it does not change the exit code.
        assert f"notice: {notice['message']}" in stderr_lines
        assert code == 0
        if "missing" in expect:
            assert sorted(notice["missing"]) == sorted(expect["missing"])
    if "notice_one_of" in expect:
        assert set(expect["notice_one_of"]) & set(notice_codes)
    if "warning_count" in expect:
        assert len(report["warnings"]) == expect["warning_count"]
        assert len([line for line in stderr_lines if line.startswith("warning: ")]) == expect["warning_count"]
    if "warning" in expect:
        assert expect["warning"] in [warning["code"] for warning in report["warnings"]]
    if expect.get("debug") == "unknown_key":
        keys = [key for source in case["given"]["sources"].values() for key in source.get("extra_keys", {})]
        assert keys
        for key in keys:
            assert f"unknown_key key={key} " in err
    if "profile_folder" in expect:
        folder = Path(expect["profile_folder"].replace("~", str(world.home), 1))
        assert Path(used[0]["path"]) == folder / "config.json"
    if expect.get("output_excludes_secret"):
        _, text_out, text_err = _run_cli(["--config-status", *world.flags()], capsys)
        _, show_out, show_err = _run_cli(["--show-config", *world.flags()], capsys)
        everything = out + err + text_out + text_err + show_out + show_err
        for cred in _FIXTURES.values():
            assert not _shows_secret(cred["secret"], everything)
        assert "secret:    ****" in text_out


class _Answer:
    def __init__(self, status: int, body: Any) -> None:
        self.status_code = status
        self._body = body

    def json(self) -> Any:
        return self._body


def _check_live_test(
    case: dict[str, Any], world: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import requests

    given, expect = case["given"], case["expect"]
    # --profile-test tests a named profile, so the credential of the case becomes a profile.
    spec = next(iter(given.get("sources", {}).values()), {"credential": "A"})
    cred = _credential(spec)
    world.write_profile({"name": "prod", **spec})
    for name in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES"):
        monkeypatch.delenv(name, raising=False)

    posted: list[dict[str, str]] = []

    def fake_post(url: str, data: dict[str, str]) -> _Answer:
        posted.append({"url": url, **data})
        answer = given["sign_in_answer"]
        if answer == "connection_error":
            raise requests.ConnectionError("the network is down")
        return _Answer(answer["status"], answer["body"])

    monkeypatch.setattr(sign_in, "_post", fake_post)
    login = MagicMock()
    product_answer = given.get("product_answer")
    if product_answer == "has_access":
        login.getCompanyId.return_value = [{"globalCompanyId": "testco0"}]
    elif product_answer == "no_access":
        login.getCompanyId.return_value = []
    else:
        login.getCompanyId.side_effect = requests.ConnectionError("the network is down")

    argv = ["--profile-test", "prod", "--max-retries", "0"]
    with (
        patch("aanalytics2.configure"),
        patch("aanalytics2.Login", return_value=login) as login_class,
        patch("aanalytics2.Analytics"),
    ):
        code, out, err = _run_cli([*argv, "--format", "json"], capsys)
        product_calls = login_class.call_count
        _, text_out, text_err = _run_cli(argv, capsys)

    report = json.loads(out)
    check_shape(report, _shape("live-test-v1"))
    assert posted[0]["url"] == sign_in.IMS_SIGN_IN_URL
    assert posted[0]["grant_type"] == "client_credentials"
    assert posted[0]["client_id"] == cred["client_id"]
    assert report["ok"] is (report["sign_in"]["ok"] is True and report["product_access"]["ok"] is True)
    assert (code == 0) is report["ok"]
    assert report["source"] == {"kind": "flag_profile", "name": "profile prod"}
    if report["sign_in"]["ok"] is not True:
        assert product_calls == 0, "the product call ran after a failed sign-in"
        assert report["product_access"] == {"ok": None, "code": None, "message": None}

    for step in ("sign_in", "product_access"):
        wanted = expect.get(step, {})
        got = report[step]
        for key in ("ok", "code"):
            if key in wanted:
                assert got[key] == wanted[key], f"{step}.{key}"
        if "message_contains" in wanted:
            assert wanted["message_contains"] in got["message"]
        if "message_excludes" in wanted:
            assert wanted["message_excludes"] not in got["message"]
            assert len(got["message"]) <= 200
        if "message_contains_by_product" in wanted:
            assert wanted["message_contains_by_product"][PRODUCT] in got["message"]
        if got["ok"] is False:
            assert got["code"] in json.loads((_CASES_DIR / "codes-v1.json").read_text(encoding="utf-8"))["codes"]
            assert f"FAIL [{got['code']}]" in text_out
    if expect.get("output_excludes_secret"):
        assert not _shows_secret(cred["secret"], out + err + text_out + text_err)


def _mode(path: Path) -> str:
    return f"{stat.S_IMODE(path.stat().st_mode):04o}"


def _check_create_profile(case: dict[str, Any], world: World, capsys: pytest.CaptureFixture[str]) -> None:
    given, expect = case["given"], case["expect"]
    if "existing_folder_mode" in given:
        world.orgs.mkdir(parents=True)
        world.orgs.chmod(int(given["existing_folder_mode"], 8))
        world.orgs.parent.chmod(int(given["existing_folder_mode"], 8))
    source = world.work / "import.json"
    source.write_text(json.dumps(_FIXTURES[given["credential"]]), encoding="utf-8")
    code, _, _ = _run_cli(["--profile-import", given["profile_name"], str(source)], capsys)
    assert code == 0
    folder = world.orgs / given["profile_name"]
    assert _mode(folder) == "0700"
    if "folder_mode" in expect:
        assert _mode(folder) == expect["folder_mode"]
        assert _mode(world.orgs) == expect["folder_mode"]
        assert _mode(world.orgs.parent) == expect["folder_mode"]
    if "file_mode" in expect:
        assert _mode(folder / "config.json") == expect["file_mode"]
    if "existing_folder_mode" in expect:
        assert _mode(world.orgs) == expect["existing_folder_mode"]
        assert _mode(world.orgs.parent) == expect["existing_folder_mode"]


def _check_pure(case: dict[str, Any]) -> None:
    given, expect = case["given"], case["expect"]
    if "client_id" in given:
        assert credentials.mask_client_id(given["client_id"]) == expect["masked"]
    elif "secret" in given:
        assert credentials.mask_secret(given["secret"]) == expect["masked"]
    elif "profile_name" in given:
        if expect["valid"]:
            profiles.validate_profile_name(given["profile_name"])
        else:
            with pytest.raises(ConfigError) as caught:
                profiles.validate_profile_name(given["profile_name"])
            assert caught.value.code == "invalid_profile_name"
    else:
        raise AssertionError("the adapter does not know this case")


def _check(
    case: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    given = case["given"]
    command = given.get("command")
    if command is None and "sources" not in given and "action" not in given:
        _check_pure(case)
        return
    world = World(tmp_path, monkeypatch)
    if given.get("action") == "create_profile":
        _check_create_profile(case, world, capsys)
    elif command == "live_test":
        _check_live_test(case, world, capsys, monkeypatch)
    else:
        world.build(given.get("sources", {}))
        if command == "config_check":
            _check_config_check(case, world, capsys)
        else:
            assert command is None, f"command {command} is not handled by the adapter"
            _check_lookup(case, world)


@pytest.mark.parametrize("case", _CASES, ids=[case["id"] for case in _CASES])
def test_standard_case(
    case: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reason = _skip_reason(case)
    if reason:
        pytest.skip(reason)
    if case["id"] not in _EXPECTED_TO_FAIL:
        _check(case, tmp_path, monkeypatch, capsys)
        return
    try:
        _check(case, tmp_path, monkeypatch, capsys)
    except AssertionError:
        return  # the difference is listed in known-differences.json
    pytest.fail(f"{case['id']} passes now. Remove it from known-differences.json.")


def test_case_ids_are_unique() -> None:
    ids = [case["id"] for case in _CASES]
    assert len(ids) == len(set(ids))


def test_known_differences_file_has_the_shared_shape() -> None:
    schema = _shape("known-differences-v1")
    assert _KNOWN["spec"] == schema["properties"]["spec"]["const"]
    assert set(_KNOWN) <= set(schema["properties"])
    assert set(schema["required"]) <= set(_KNOWN)
    assert _KNOWN["tool"] == TOOL
    for entry in _KNOWN["not_applicable"]:
        assert set(entry) == {"rule", "reason"}
    for diff in _KNOWN["differences"]:
        assert {"rule", "summary"} <= set(diff) <= {"rule", "cases", "summary", "planned"}


def test_known_differences_name_real_cases_that_apply_to_this_tool() -> None:
    by_id = {case["id"]: case for case in _CASES}
    for diff in _KNOWN["differences"]:
        for case_id in diff.get("cases", []):
            assert case_id in by_id, f"{case_id} is not a shared case"
            assert _skip_reason(by_id[case_id]) is None, f"{case_id} is skipped by this tool"
            assert by_id[case_id]["rule"] == diff["rule"]


def test_every_level_1_and_level_2_case_is_expected_to_pass() -> None:
    low = {case["id"] for case in _CASES if case["level"] in (1, 2)}
    assert not low & _EXPECTED_TO_FAIL


def test_the_case_files_are_all_run() -> None:
    on_disk = {path.name for path in _CASES_DIR.glob("*.json")}
    not_cases = {"SOURCE.json", "fixtures.json", "codes-v1.json"} | {p.name for p in _CASES_DIR.glob("*.schema.json")}
    assert on_disk - not_cases == set(_CASE_FILES)
