# tests/test_metrics.py
import pytest
from rlcoach.metrics import (
    METRIC_CATALOG,
    get_metric,
    get_metrics_by_category,
    is_valid_metric,
    MetricDirection,
)


def test_metric_catalog_has_bcpm():
    """Catalog should contain boost metrics."""
    assert "bcpm" in METRIC_CATALOG
    metric = METRIC_CATALOG["bcpm"]
    assert metric.display_name == "Boost/Min"
    assert metric.direction == MetricDirection.HIGHER_BETTER


def test_get_metric_returns_none_for_invalid():
    assert get_metric("invalid_metric_xyz") is None


def test_is_valid_metric():
    assert is_valid_metric("bcpm") is True
    assert is_valid_metric("goals") is True
    assert is_valid_metric("fake_metric") is False


def test_get_metrics_by_category():
    boost_metrics = get_metrics_by_category("boost")
    assert "bcpm" in boost_metrics
    assert "avg_boost" in boost_metrics
    assert "goals" not in boost_metrics
