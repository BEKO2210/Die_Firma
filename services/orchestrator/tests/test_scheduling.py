from datetime import UTC, datetime

from conftest import make_job

from die_firma.scheduling import (
    adaptive_worker_count,
    cpu_load,
    job_priority_key,
    order_jobs,
)


def test_idle_machine_keeps_baseline():
    # Lots of free cores but ceiling defaults to baseline -> stays at baseline.
    assert adaptive_worker_count(2, cpu_count=8, load1=0.0) == 2


def test_high_load_scales_down_to_min():
    assert adaptive_worker_count(4, cpu_count=4, load1=4.0, min_workers=1, ceiling=4) == 1


def test_scales_up_to_ceiling_when_idle():
    assert adaptive_worker_count(2, cpu_count=8, load1=0.0, ceiling=6) == 6


def test_tracks_free_cores_between_min_and_ceiling():
    # 8 cores, load 5 -> ~3 free cores -> 3 workers (within [1, 6]).
    assert adaptive_worker_count(2, cpu_count=8, load1=5.0, ceiling=6) == 3


def test_vram_caps_concurrency():
    # 5 free cores would allow 5, but only 2 models fit in free VRAM.
    count = adaptive_worker_count(
        2,
        cpu_count=8,
        load1=3.0,
        ceiling=8,
        vram_free_mb=5000,
        vram_per_worker_mb=2000,
    )
    assert count == 2


def test_min_workers_is_floored():
    assert adaptive_worker_count(2, cpu_count=1, load1=10.0, min_workers=1) == 1
    # min_workers below 1 is coerced to 1.
    assert adaptive_worker_count(2, cpu_count=1, load1=10.0, min_workers=0) == 1


def test_priority_key_orders_urgent_first():
    early = datetime(2026, 6, 3, tzinfo=UTC)
    late = datetime(2026, 6, 9, tzinfo=UTC)
    p1 = make_job(priority=1, deadline=late)
    p2_early = make_job(priority=2, deadline=early)
    p2_late = make_job(priority=2, deadline=late)
    ordered = order_jobs([p2_late, p2_early, p1])
    # priority 1 first; within priority 2, earlier deadline first.
    assert [job_priority_key(j)[0] for j in ordered] == [1, 2, 2]
    assert ordered[1] is p2_early and ordered[2] is p2_late


def test_cpu_load_returns_sane_values():
    cpu_count, load1 = cpu_load()
    assert cpu_count >= 1
    assert load1 >= 0.0
