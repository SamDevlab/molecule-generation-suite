import pytest

from research_os.backup import create_backup
from research_os.cache import CacheKey, ResearchCache
from research_os.execution import LocalExecutor, SlurmExecutor
from research_os.storage import InMemoryPersistence


def test_cache_key_changes_when_protocol_changes():
    base = CacheKey("i", "c", "commit", "engine-1", "protocol-1")
    changed = CacheKey("i", "c", "commit", "engine-1", "protocol-2")
    assert base.digest != changed.digest
    cache = ResearchCache()
    cache.put(base, {"value": 1})
    assert cache.get(changed) is None


def test_local_executor_is_typed_and_slurm_fails_closed():
    assert LocalExecutor().submit(lambda: 2).value == 2
    with pytest.raises(Exception):
        SlurmExecutor().submit(lambda: 2)


def test_backup_is_hash_indexed_and_non_destructive(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "research-ledger").mkdir()
    (source / "research-ledger" / "index.json").write_text("{}", encoding="utf-8")
    manifest = create_backup(source, tmp_path / "backup")
    assert manifest.files["research-ledger/index.json"]
    assert (source / "research-ledger" / "index.json").is_file()


def test_in_memory_persistence_round_trip():
    store = InMemoryPersistence()
    store.save("plan", {"status": "VALIDATED"})
    assert store.load("plan") == {"status": "VALIDATED"}

