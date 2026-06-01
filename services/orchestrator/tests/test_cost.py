from die_firma.cost import evaluate


def test_disabled_limit_always_allows():
    d = evaluate(100.0, 0.0)
    assert d.allowed is True
    assert d.remaining_usd == 0.0


def test_under_limit_allows_and_reports_remaining():
    d = evaluate(3.0, 10.0)
    assert d.allowed is True
    assert d.remaining_usd == 7.0


def test_at_or_over_limit_blocks():
    assert evaluate(10.0, 10.0).allowed is False
    over = evaluate(12.0, 10.0)
    assert over.allowed is False
    assert over.remaining_usd == 0.0  # clamped
