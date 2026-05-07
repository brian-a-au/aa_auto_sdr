"""v1.5 — core/profiles emits DEBUG records (paths/contents NOT logged)."""

from __future__ import annotations

import logging

import pytest

from aa_auto_sdr.core.profiles import list_profiles, read_profile, write_profile


@pytest.fixture(autouse=True)
def _isolate_package_logger():
    """Pattern B per disambiguation table — profiles functions don't call setup_logging."""
    pkg = logging.getLogger("aa_auto_sdr")
    saved_handlers = pkg.handlers[:]
    saved_level = pkg.level
    yield
    pkg.handlers.clear()
    for h in saved_handlers:
        pkg.addHandler(h)
    pkg.setLevel(saved_level)


def test_read_profile_emits_debug(caplog, tmp_path):
    base = tmp_path / "base"
    (base / "orgs" / "p1").mkdir(parents=True)
    (base / "orgs" / "p1" / "config.json").write_text('{"x": 1}')
    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.core.profiles")
    read_profile("p1", base=base)
    debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert len(debugs) >= 1


def test_write_profile_emits_debug(caplog, tmp_path):
    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.core.profiles")
    write_profile("p1", {"x": 1}, base=tmp_path)
    debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert len(debugs) >= 1


def test_list_profiles_emits_debug_with_count(caplog, tmp_path):
    (tmp_path / "orgs" / "a").mkdir(parents=True)
    (tmp_path / "orgs" / "b").mkdir(parents=True)
    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.core.profiles")
    list_profiles(base=tmp_path)
    debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert any(getattr(r, "count", None) == 2 for r in debugs)


def test_list_profiles_empty_root_emits_debug_count_zero(caplog, tmp_path):
    """Spec §7.6: list_profiles has TWO emit points — empty (root missing) and
    non-empty. Both must fire a DEBUG record so triagers can distinguish
    'no profile dir' from 'empty profile dir'."""
    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.core.profiles")
    list_profiles(base=tmp_path)  # tmp_path/orgs does not exist
    debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert any(getattr(r, "count", None) == 0 for r in debugs)
