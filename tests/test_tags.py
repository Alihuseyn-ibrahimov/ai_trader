import pytest

from signals.tags import make_tag, parse_stop_dist


def test_roundtrip():
    tag = make_tag("trend", 1234.5678)
    assert tag.startswith("trend|sd=")
    assert parse_stop_dist(tag) == pytest.approx(1234.5678, rel=1e-6)


@pytest.mark.parametrize("tag", [None, "", "trend", "trend|x=1", "trend|sd=abc"])
def test_missing_or_bad_returns_none(tag):
    assert parse_stop_dist(tag) is None


@pytest.mark.parametrize("dist", [0, -1, float("nan")])
def test_make_tag_rejects_non_positive(dist):
    with pytest.raises(ValueError):
        make_tag("trend", dist)
