"""OAuth Server-to-Server credentials and resolution.

`lookup()` walks the sources in order and reports what it found. `resolve()`
is the same lookup for a normal run: it prints the notices and warnings, then
returns the credential or raises ConfigError.

Order (highest first): `--config <path>` or `--profile <name>`, the
`AA_PROFILE` variable, the environment variables, `.env` in the working
folder, `config.json` in the working folder. The four fields always come from
one source.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aa_auto_sdr.core import notices
from aa_auto_sdr.core.exceptions import ConfigError

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = ("org_id", "client_id", "secret", "scopes")
# Keys a credential file may hold. `sandbox` is accepted and ignored.
_KNOWN_FILE_KEYS = (*_REQUIRED_FIELDS, "sandbox")

MASK = "****"


def mask_client_id(client_id: str) -> str:
    """The one way this tool shows a client ID: first 4 characters, `****`, last 4.

    A client ID of 8 characters or fewer is shown as `****`."""
    if len(client_id) <= 8:
        return MASK
    return f"{client_id[:4]}{MASK}{client_id[-4:]}"


def mask_secret(secret: str) -> str:
    """`****` for a secret that is set, and an empty string for one that is not.

    The stars have a fixed length, so they do not show how long the secret is."""
    return MASK if secret else ""


@dataclass(frozen=True, slots=True)
class Credentials:
    """OAuth S2S credentials plus diagnostic source label."""

    org_id: str
    client_id: str
    secret: str
    scopes: str
    source: str  # 'profile:<name>' | 'env' | '.env' | 'config.json' | 'config:<path>'

    def validate(self) -> None:
        """Raise ConfigError if any required field is missing or whitespace-only."""
        missing = _missing_fields(self)
        if missing:
            error = ConfigError(f"Missing required credential fields: {', '.join(missing)} (loaded from {self.source})")
            error.code = "partial_source"
            error.missing = tuple(missing)
            raise error

    def shown(self) -> ShownCredential:
        """The parts of this credential that a command may print."""
        return ShownCredential(
            source=self.source,
            org_id=self.org_id,
            client_id=mask_client_id(self.client_id),
            secret=mask_secret(self.secret),
            scopes=self.scopes,
        )


@dataclass(frozen=True, slots=True)
class ShownCredential:
    """A credential as a command prints it. It never holds the secret.

    `client_id` is masked, and `secret` is `****` or an empty string."""

    source: str
    org_id: str
    client_id: str
    secret: str
    scopes: str


def _missing_fields(c: Credentials) -> list[str]:
    return [f for f in _REQUIRED_FIELDS if not getattr(c, f).strip()]


def _from_dict(d: dict, source: str) -> Credentials:
    def text(key: str) -> str:
        # JSON null, or a bare `KEY` line in .env, is missing, not the text "None".
        value = d.get(key)
        return "" if value is None else str(value).strip()

    return Credentials(
        org_id=text("org_id"),
        client_id=text("client_id"),
        secret=text("secret"),
        scopes=text("scopes"),
        source=source,
    )


def _is_complete(c: Credentials) -> bool:
    return not _missing_fields(c)


def _from_env() -> Credentials:
    return _from_dict(
        {
            "org_id": os.environ.get("ORG_ID", ""),
            "client_id": os.environ.get("CLIENT_ID", ""),
            "secret": os.environ.get("SECRET", ""),
            "scopes": os.environ.get("SCOPES", ""),
        },
        source="env",
    )


def _from_dotenv(working_dir: Path) -> Credentials | None:
    """Read `.env` in the working folder as a source of its own.

    The file is not loaded into the environment, and parent folders are not
    searched. Returns None when there is no file. Raises ConfigError when the
    file cannot be read; `lookup()` turns that into a warning and goes on."""
    from dotenv import dotenv_values

    path = working_dir / ".env"
    if not os.path.exists(path):
        return None
    # .env files use the UPPERCASE env-var contract (ORG_ID, ...) per .env.example;
    # normalize to the lowercase keys `_from_dict` expects, mirroring `_from_env`.
    try:
        values = {k.lower(): v for k, v in dotenv_values(path).items()}
    except OSError as exc:
        raise ConfigError(f".env: could not read {path}: {exc.strerror or exc}") from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(f".env: {path} is not valid UTF-8: {exc}") from exc
    return _from_dict(values, source=".env")


def _read_json_source(path: Path, label: str, source: str) -> tuple[Credentials, bool]:
    """Read one JSON credential file. Returns the credential and whether the file holds `sandbox`.

    Logs one debug line for each key the tool does not know."""
    from aa_auto_sdr.core.profiles import read_config_object

    data = read_config_object(path, label)
    for key in data:
        if key not in _KNOWN_FILE_KEYS:
            logger.debug("unknown_key key=%s path=%s (ignored)", key, path, extra={"path": str(path)})
    return _from_dict(data, source=source), "sandbox" in data


@dataclass(frozen=True, slots=True)
class Message:
    """One problem, notice or warning. `code` is from the Adobe credentials standard."""

    code: str | None
    message: str
    missing: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.missing:
            out["missing"] = list(self.missing)
        return out


@dataclass(slots=True)
class SourceReport:
    """What the lookup saw in one source. It never holds a value."""

    kind: str  # flag_profile | flag_config | profile_variable | environment | dotenv | default_config
    name: str
    path: str | None
    fields: list[str]
    missing: list[str]
    used: bool = False
    skipped: str | None = None  # 'partial' | 'lower_priority' | None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": self.kind,
            "name": self.name,
            "path": self.path,
            "used": self.used,
            "fields": list(self.fields),
            "skipped": self.skipped,
        }
        if self.skipped == "partial":
            out["missing"] = list(self.missing)
        return out


@dataclass(slots=True)
class Lookup:
    """The result of one credential lookup, for a run and for the config check."""

    creds: Credentials | None = None
    profile: str | None = None
    sources: list[SourceReport] = field(default_factory=list)
    problems: list[Message] = field(default_factory=list)
    notices: list[Message] = field(default_factory=list)
    warnings: list[Message] = field(default_factory=list)
    error: ConfigError | None = None

    @property
    def used(self) -> SourceReport | None:
        """The source the credential came from, or None."""
        return next((s for s in self.sources if s.used), None)

    def announce(self) -> None:
        """Print each warning and notice as one line on stderr, once per run."""
        for warning in self.warnings:
            notices.say("warning", warning.message)
        for notice in self.notices:
            notices.say("notice", notice.message)


_config_path: Path | None = None


def set_config_path(path: str | Path | None) -> None:
    """Set the `--config <path>` of this run. The CLI calls it once, before any lookup.

    Every lookup that is not given a `config` argument uses this path."""
    global _config_path  # noqa: PLW0603 - one run has one --config value
    _config_path = Path(path).expanduser() if path else None


def _error(message: str, code: str, missing: list[str] | None = None) -> ConfigError:
    error = ConfigError(message)
    error.code = code
    error.missing = tuple(missing or ())
    return error


def _fail(out: Lookup, error: ConfigError) -> Lookup:
    out.error = error
    # A file that is damaged has no code of its own in the standard.
    out.problems.append(Message(error.code or "no_credential", str(error), error.missing))
    return out


def _present_fields(c: Credentials, *, sandbox: bool = False) -> list[str]:
    present = [f for f in _REQUIRED_FIELDS if getattr(c, f).strip()]
    return [*present, "sandbox"] if sandbox else present


def _check_file_mode(out: Lookup, path: Path) -> None:
    from aa_auto_sdr.core import profiles

    if profiles.readable_by_others(path):
        out.warnings.append(
            Message(
                "file_readable_by_others",
                f"{path} holds a credential and other users of this computer can read it. "
                f'To fix this, run: chmod 600 "{path}"',
            )
        )


def _report(
    out: Lookup, kind: str, name: str, path: Path | None, creds: Credentials, *, sandbox: bool = False
) -> SourceReport:
    report = SourceReport(
        kind=kind,
        name=name,
        path=None if path is None else str(path),
        fields=_present_fields(creds, sandbox=sandbox),
        missing=_missing_fields(creds),
    )
    if report.fields:
        out.sources.append(report)
        if path is not None and [f for f in report.fields if f != "sandbox"]:
            _check_file_mode(out, path)
    return report


def _use(out: Lookup, report: SourceReport, creds: Credentials) -> None:
    report.used = True
    out.creds = creds
    logger.info("creds_resolved source=%s", creds.source, extra={"creds_source": creds.source})


_PARTIAL_NAMES = {
    "environment": "The environment variables",
    "dotenv": "The .env file",
    "default_config": "The config.json file",
}


def _skip_partial(out: Lookup, report: SourceReport) -> None:
    """Record a source that holds some of the four fields and not all of them."""
    report.skipped = "partial"
    upper = report.kind in ("environment", "dotenv")
    names = ", ".join(f.upper() if upper else f for f in report.missing)
    out.notices.append(
        Message(
            "partial_source_skipped",
            f"{_PARTIAL_NAMES[report.kind]} set some credential fields and not {names}, so this source "
            "was skipped. A later release will stop with an error in this situation.",
            tuple(report.missing),
        )
    )


def _lookup_explicit_file(out: Lookup, kind: str, name: str, path: Path, label: str, source: str) -> None:
    """A profile or a --config file. It must hold all four fields, and there is no fall back."""
    try:
        creds, sandbox = _read_json_source(path, label, source)
    except ConfigError as exc:
        _fail(out, exc)
        return
    report = _report(out, kind, name, path, creds, sandbox=sandbox)
    try:
        creds.validate()
    except ConfigError as exc:
        report.skipped = "partial"
        _fail(out, exc)
        return
    _use(out, report, creds)


def _lookup_profile(out: Lookup, name: str, kind: str, profiles_base: Path | None) -> None:
    from aa_auto_sdr.core import profiles

    logger.debug("resolve attempt source=profile:%s", name)
    out.profile = name
    try:
        profiles.check_profile_name(name, base=profiles_base)
    except ConfigError as exc:
        _fail(out, exc)
        return
    path = profiles.profile_config_path(name, base=profiles_base)
    if not os.path.exists(path):
        _fail(out, _error(f"Profile '{name}' not found at {path}", "profile_not_found"))
        return
    _lookup_explicit_file(out, kind, f"profile {name}", path, f"Profile '{name}'", f"profile:{name}")


def _lookup_config_flag(out: Lookup, path: Path) -> None:
    logger.debug("resolve attempt source=config")
    if not os.path.isfile(path):
        _fail(out, _error(f"--config: no file at {path}", "no_credential"))
        return
    _lookup_explicit_file(out, "flag_config", "config file", path, "--config", f"config:{path}")


def _read_dotenv(out: Lookup, working_dir: Path, *, quiet: bool = False) -> tuple[SourceReport, Credentials] | None:
    """The .env report and credential, or None when there is no usable file.

    A file that cannot be read is skipped with a warning."""
    path = working_dir / ".env"
    try:
        creds = _from_dotenv(working_dir)
    except ConfigError as exc:
        if not quiet:
            out.warnings.append(Message(None, f"{exc}. The file was skipped."))
        return None
    if creds is None:
        return None
    report = _report(out, "dotenv", ".env", path, creds)
    return (report, creds)


def _read_default_config(out: Lookup, working_dir: Path, *, tolerant: bool) -> tuple[SourceReport, Credentials] | None:
    """The config.json report and credential, or None when there is no file.

    `tolerant` is for a file that is read only for comparison or for the
    config check: a damaged file is then left out instead of raising."""
    path = working_dir / "config.json"
    if not os.path.exists(path):
        return None
    try:
        creds, sandbox = _read_json_source(path, "config.json", "config.json")
    except ConfigError:
        if tolerant:
            return None
        raise
    return _report(out, "default_config", "config.json", path, creds, sandbox=sandbox), creds


def _same_credential(a: Credentials, b: Credentials) -> bool:
    return all(getattr(a, f) == getattr(b, f) for f in _REQUIRED_FIELDS)


def _lookup_ambient(out: Lookup, working_dir: Path, *, scan_all: bool, explicit_won: bool) -> None:
    """The environment variables, then .env, then config.json.

    The first complete source wins. A partial source is skipped with a notice.
    When `explicit_won` is true a profile or a --config file already gave the
    credential, and these sources are only listed for the config check."""
    found = explicit_won

    if not found:
        logger.debug("resolve attempt source=env")
    env_creds = _from_env()
    env_report = _report(out, "environment", "environment variables", None, env_creds)
    if found:
        env_report.skipped = "lower_priority"
    elif _is_complete(env_creds):
        _use(out, env_report, env_creds)
        found = True
    elif env_report.fields:
        _skip_partial(out, env_report)
    if found and not scan_all:
        return

    if not found:
        logger.debug("resolve attempt source=.env")
    dotenv = _read_dotenv(out, working_dir, quiet=found)
    dotenv_won = False
    if dotenv is not None:
        report, creds = dotenv
        if found:
            report.skipped = "lower_priority"
        elif _is_complete(creds):
            _use(out, report, creds)
            found = dotenv_won = True
        elif report.fields:
            _skip_partial(out, report)

    # Reached when nothing won yet, when .env won (config.json is read to
    # compare the two), or for the config check.
    if not found:
        logger.debug("resolve attempt source=config.json")
    try:
        config = _read_default_config(out, working_dir, tolerant=found)
    except ConfigError as exc:
        _fail(out, exc)
        return
    if config is not None:
        report, creds = config
        if found:
            report.skipped = "lower_priority"
            if dotenv_won and _is_complete(creds) and not _same_credential(out.creds, creds):
                out.notices.append(
                    Message(
                        "dotenv_and_config_differ",
                        f"The .env file and the config.json file in {working_dir} hold different "
                        "credentials. This run uses the .env file.",
                    )
                )
        elif _is_complete(creds):
            _use(out, report, creds)
            found = True
        elif report.fields:
            _skip_partial(out, report)

    if not found:
        logger.error("creds_not_found", extra={"error_class": "ConfigError"})
        partial = [s for s in out.sources if s.skipped == "partial"]
        message = (
            "No credentials found. Set ORG_ID/CLIENT_ID/SECRET/SCOPES env vars, "
            "create a profile (--profile-add), or place a config.json in the working directory."
        )
        if partial:
            # The run stops here, so the missing fields go in the error and
            # the "a later release will stop" notices are dropped.
            out.notices = [n for n in out.notices if n.code != "partial_source_skipped"]
            details = "; ".join(f"{s.name} has no {', '.join(s.missing)}" for s in partial)
            missing = [f for f in _REQUIRED_FIELDS if any(f in s.missing for s in partial)]
            _fail(out, _error(f"{message} Incomplete sources: {details}.", "partial_source", missing))
        else:
            _fail(out, _error(message, "no_credential"))


def lookup(
    *,
    profile: str | None = None,
    config: str | Path | None = None,
    profiles_base: Path | None = None,
    working_dir: Path | None = None,
    scan_all: bool = False,
) -> Lookup:
    """Find the credential and report every source that was looked at.

    Never raises ConfigError: a failed lookup has `creds` None and the error in
    `error`. `scan_all` also lists the sources below the winner, which a
    normal run does not read. It is for the config check."""
    working_dir = working_dir or Path.cwd()
    config_path = Path(config).expanduser() if config else _config_path
    out = Lookup()
    logger.debug("resolve start chosen_profile_set=%s", bool(profile or os.environ.get("AA_PROFILE")))

    if profile and config_path:
        out.profile = profile
        return _fail(
            out,
            _error(
                "--profile and --config cannot be used together. Give one of them.",
                "profile_and_config_both_given",
            ),
        )
    explicit = True
    if config_path:
        _lookup_config_flag(out, config_path)
    elif profile:
        _lookup_profile(out, profile, "flag_profile", profiles_base)
    elif os.environ.get("AA_PROFILE"):
        _lookup_profile(out, os.environ["AA_PROFILE"], "profile_variable", profiles_base)
    else:
        explicit = False
    if explicit and (out.error is not None or not scan_all):
        return out
    _lookup_ambient(out, working_dir, scan_all=scan_all, explicit_won=explicit)
    return out


def resolve(
    *,
    profile: str | None = None,
    config: str | Path | None = None,
    profiles_base: Path | None = None,
    working_dir: Path | None = None,
) -> Credentials:
    """Resolve credentials by precedence: --config or profile > env > .env > config.json.

    Prints the notices and warnings of the lookup on stderr, once per run.
    `profiles_base` and `working_dir` are injection points for testability.
    """
    found = lookup(profile=profile, config=config, profiles_base=profiles_base, working_dir=working_dir)
    found.announce()
    if found.error is not None:
        raise found.error
    assert found.creds is not None  # a lookup without an error has a credential
    return found.creds


@dataclass(frozen=True, slots=True)
class ResolutionEntry:
    """One step in the credential resolution chain — used by --config-status."""

    priority: int  # 1 (highest) → N (lowest)
    source: str  # human label
    matched: bool  # True if this source produced the resolved value
    missing: tuple[str, ...] = ()  # for a source skipped as partial, the fields it lacks


def validate_only(
    *,
    profile: str | None = None,
    config: str | Path | None = None,
    working_dir: Path | None = None,
) -> Credentials:
    """Resolve credentials and validate shape WITHOUT calling Adobe.

    Raises ConfigError for missing fields or malformed `org_id`."""
    creds = resolve(profile=profile, config=config, working_dir=working_dir)  # raises ConfigError on missing fields
    if not creds.org_id.endswith("@AdobeOrg"):
        raise ConfigError(
            f"org_id '{creds.org_id}' does not match Adobe shape (expected `<id>@AdobeOrg`)",
        )
    return creds


def chain_of(found: Lookup, *, profile: str | None = None, config: str | Path | None = None) -> list[ResolutionEntry]:
    """The four chain entries of a lookup made with `scan_all=True`."""
    by_kind = {s.kind: s for s in found.sources}

    def entry(priority: int, label: str, *kinds: str) -> ResolutionEntry:
        report = next((by_kind[k] for k in kinds if k in by_kind), None)
        partial = report is not None and report.skipped == "partial"
        return ResolutionEntry(
            priority=priority,
            source=label,
            matched=bool(report and report.used),
            missing=tuple(report.missing) if partial else (),
        )

    config_path = Path(config).expanduser() if config else _config_path
    if config_path and not profile:
        first = f"--config={config_path}"
    elif found.profile:
        first = f"--profile={found.profile}"
    else:
        first = "--profile (not set)"
    return [
        entry(1, first, "flag_config", "flag_profile", "profile_variable"),
        entry(2, "env vars", "environment"),
        entry(3, ".env (cwd)", "dotenv"),
        entry(4, "config.json (cwd)", "default_config"),
    ]


def resolution_chain(
    *,
    profile: str | None = None,
    config: str | Path | None = None,
    profiles_base: Path | None = None,
    working_dir: Path | None = None,
) -> list[ResolutionEntry]:
    """Walk every credential source in priority order; report which matched.

    Order (highest precedence first, mirroring `resolve()`):
      1. --config=<path> or --profile=<name> (or the AA_PROFILE variable)
      2. env vars           (ORG_ID + CLIENT_ID + SECRET + SCOPES all present)
      3. .env (cwd)         (when .env exists in cwd AND fills the four vars)
      4. config.json (cwd)  (when ./config.json exists and fills the four fields)

    The first source that fully populates the four required fields wins.
    Subsequent entries are reported with `matched=False`. A profile or a
    --config file halts the lookup, so no later source matches even when the
    profile itself cannot resolve."""
    found = lookup(profile=profile, config=config, profiles_base=profiles_base, working_dir=working_dir, scan_all=True)
    return chain_of(found, profile=profile, config=config)
