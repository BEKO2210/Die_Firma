from pathlib import Path

from die_firma.cache import ResultCache, subtask_cache_key


def test_key_is_stable_and_order_independent():
    a = subtask_cache_key(
        job_type="code_gen",
        task_text="build x",
        action="implement",
        model="m",
        context={"a.txt": "1", "b.txt": "2"},
    )
    b = subtask_cache_key(
        job_type="code_gen",
        task_text="build x",
        action="implement",
        model="m",
        context={"b.txt": "2", "a.txt": "1"},  # different order -> same key
    )
    assert a == b


def test_key_changes_with_model_and_context():
    base = dict(job_type="code_gen", task_text="t", action="implement", context={})
    k1 = subtask_cache_key(model="m1", **base)  # type: ignore[arg-type]
    k2 = subtask_cache_key(model="m2", **base)  # type: ignore[arg-type]
    k3 = subtask_cache_key(model="m1", **{**base, "context": {"f": "x"}})  # type: ignore[arg-type]
    assert len({k1, k2, k3}) == 3


def test_put_then_get_roundtrip(tmp_path: Path):
    cache = ResultCache(tmp_path)
    cache.put("k" * 64, artifacts={"index.html": "<h1>hi</h1>"}, model="m", output="done")
    hit = cache.get("k" * 64)
    assert hit is not None
    assert hit.artifacts == {"index.html": "<h1>hi</h1>"}
    assert hit.model == "m"
    assert hit.output == "done"


def test_get_miss_returns_none(tmp_path: Path):
    assert ResultCache(tmp_path).get("nope") is None


def test_disabled_cache_is_inert(tmp_path: Path):
    cache = ResultCache(tmp_path, enabled=False)
    cache.put("k", artifacts={"a": "b"}, model="m", output="o")
    assert cache.get("k") is None
    assert not any(tmp_path.iterdir())


def test_empty_artifacts_not_stored(tmp_path: Path):
    cache = ResultCache(tmp_path)
    cache.put("k" * 64, artifacts={}, model="m", output="o")
    assert cache.get("k" * 64) is None


def test_corrupt_entry_reads_as_miss(tmp_path: Path):
    cache = ResultCache(tmp_path)
    key = "a" * 64
    entry = tmp_path / key[:2] / key
    entry.mkdir(parents=True)
    (entry / "meta.json").write_text("{ not json", encoding="utf-8")
    assert cache.get(key) is None
