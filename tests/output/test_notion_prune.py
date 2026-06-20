from pathlib import Path

from aa_auto_sdr.output import notion_prune as prune
from aa_auto_sdr.output import notion_registry as reg


class _ArchiveClient:
    def __init__(self, not_found=()):
        self.archived = []
        self._not_found = set(not_found)
        outer = self

        class _Pages:
            def update(self, *, page_id, archived):
                if page_id in outer._not_found:
                    raise _NotFound("object not found")
                outer.archived.append((page_id, archived))

        self.pages = _Pages()


class _NotFound(Exception):
    pass


def _seed(tmp_path: Path) -> Path:
    p = tmp_path / reg.REGISTRY_FILENAME
    reg.store_page_id(p, "rs1", "a")
    reg.store_page_id(p, "rs1", "b")  # tombstone a
    return p


def test_dry_run_archives_nothing(tmp_path):
    p = _seed(tmp_path)
    client = _ArchiveClient()
    result = prune.archive_orphans(client, p, prune.collect_orphans(reg.load_registry(p)), dry_run=True)
    assert result.planned == [("rs1", "a")]
    assert client.archived == []
    assert reg.load_registry(p)["rs1"]["superseded"] == ["a"]


def test_apply_archives_and_drops(tmp_path):
    p = _seed(tmp_path)
    client = _ArchiveClient()
    result = prune.archive_orphans(client, p, prune.collect_orphans(reg.load_registry(p)), dry_run=False)
    assert ("a", True) in client.archived
    assert result.archived == [("rs1", "a")]
    assert reg.load_registry(p)["rs1"]["superseded"] == []


def test_not_found_drops_tombstone(tmp_path):
    p = _seed(tmp_path)
    client = _ArchiveClient(not_found={"a"})
    result = prune.archive_orphans(
        client, p, prune.collect_orphans(reg.load_registry(p)), dry_run=False,
        not_found_types=(_NotFound,),
    )
    assert reg.load_registry(p)["rs1"]["superseded"] == []
    assert result.failed == []  # not-found is treated as success
    assert result.archived == [("rs1", "a")]  # not-found page is recorded as archived


class _ErrorClient:
    """Fake client whose pages.update always raises the given exception."""

    def __init__(self, exc):
        outer = self

        class _Pages:
            def update(self, *, page_id, archived):
                raise outer._exc

        self._exc = exc
        self.pages = _Pages()


def test_generic_exception_records_failure_preserves_tombstone(tmp_path):
    p = _seed(tmp_path)
    client = _ErrorClient(RuntimeError("boom"))
    result = prune.archive_orphans(
        client, p, prune.collect_orphans(reg.load_registry(p)), dry_run=False,
        not_found_types=(_NotFound,),
    )
    # page lands in failed with (rsid, page_id, exc_type_name)
    assert result.failed == [("rs1", "a", "RuntimeError")]
    # tombstone is preserved — drop_superseded was NOT called
    assert reg.load_registry(p)["rs1"]["superseded"] == ["a"]
    # page is NOT counted as archived
    assert result.archived == []
