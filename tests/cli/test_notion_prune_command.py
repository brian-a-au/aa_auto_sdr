from pathlib import Path
from unittest.mock import patch

from aa_auto_sdr.cli.commands.notion_prune import run_notion_prune_orphans
from aa_auto_sdr.output import notion_registry as reg


def _seed(tmp_path: Path) -> Path:
    p = tmp_path / reg.REGISTRY_FILENAME
    reg.store_page_id(p, "rs1", "a")
    reg.store_page_id(p, "rs1", "b")  # tombstone a
    return p


class _FakePages:
    def __init__(self):
        self.archived = []

    def update(self, *, page_id, archived):
        self.archived.append((page_id, archived))


class _FakeClient:
    def __init__(self, *, auth):
        self.pages = _FakePages()


def _patch_notion(fake_client_cls=_FakeClient):
    return (
        patch(
            "aa_auto_sdr.cli.commands.notion_prune._require_notion_client",
            return_value=fake_client_cls,
        ),
        patch(
            "aa_auto_sdr.cli.commands.notion_prune.resolve_notion_token",
            return_value="fake-token",
        ),
    )


def test_empty_registry_prints_no_orphans(tmp_path, capsys):
    exit_code = run_notion_prune_orphans(str(tmp_path), dry_run=True)
    out = capsys.readouterr().out
    assert "No orphaned Notion pages found." in out
    assert exit_code == 0


def test_dry_run_prints_preview_and_leaves_tombstones(tmp_path, capsys):
    p = _seed(tmp_path)
    exit_code = run_notion_prune_orphans(str(tmp_path), dry_run=True)
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "rs1" in out
    assert "a" in out
    assert exit_code == 0
    # tombstone must still be there
    assert reg.load_registry(p)["rs1"]["superseded"] == ["a"]


def test_apply_archives_and_clears_tombstones(tmp_path, capsys):
    p = _seed(tmp_path)
    req_patch, creds_patch = _patch_notion()
    with req_patch, creds_patch:
        exit_code = run_notion_prune_orphans(str(tmp_path), dry_run=False)
    out = capsys.readouterr().out
    assert "Archived 1 page(s)" in out
    assert exit_code == 0
    assert reg.load_registry(p)["rs1"]["superseded"] == []
