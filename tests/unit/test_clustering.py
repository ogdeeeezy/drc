"""Tests for violation clustering."""

from backend.core.violation_models import (
    EdgePair,
    GeometryType,
    Violation,
    ViolationGeometry,
)
from backend.fix.clustering import ViolationCluster, cluster_violations


def _violation(category, x, y, w=0.1, h=0.5):
    """Create a violation at (x,y) with edge pair of given size."""
    return Violation(
        category=category,
        description=f"{category} violation",
        cell_name="TOP",
        geometries=[
            ViolationGeometry(
                geometry_type=GeometryType.edge_pair,
                edge_pair=EdgePair(
                    edge1_start=(x, y),
                    edge1_end=(x, y + h),
                    edge2_start=(x + w, y),
                    edge2_end=(x + w, y + h),
                ),
            )
        ],
    )


class TestClusterViolations:
    def test_empty(self):
        assert cluster_violations([]) == []

    def test_single_violation(self):
        v = _violation("m1.1", 0, 0)
        clusters = cluster_violations([v])
        assert len(clusters) == 1
        assert clusters[0].total_violations == 1

    def test_nearby_violations_cluster(self):
        v1 = _violation("m1.1", 0, 0)
        v2 = _violation("m1.2", 0.5, 0)  # 0.5um away
        clusters = cluster_violations([v1, v2], proximity_um=1.0)
        assert len(clusters) == 1
        assert clusters[0].total_violations == 2

    def test_distant_violations_separate(self):
        v1 = _violation("m1.1", 0, 0)
        v2 = _violation("m1.2", 10, 10)  # far away
        clusters = cluster_violations([v1, v2], proximity_um=1.0)
        assert len(clusters) == 2

    def test_chain_clustering(self):
        # v1 near v2, v2 near v3, but v1 far from v3
        # Single-linkage should put all in one cluster
        v1 = _violation("m1.1", 0, 0)
        v2 = _violation("m1.1", 0.8, 0)  # near v1
        v3 = _violation("m1.1", 1.6, 0)  # near v2, far from v1
        clusters = cluster_violations([v1, v2, v3], proximity_um=1.0)
        assert len(clusters) == 1
        assert clusters[0].total_violations == 3

    def test_sorted_by_count(self):
        # Create one big cluster and one small
        v1 = _violation("m1.1", 0, 0)
        v2 = _violation("m1.1", 0.2, 0)
        v3 = _violation("m1.1", 0.4, 0)
        v4 = _violation("m1.2", 20, 20)  # solo
        clusters = cluster_violations([v1, v2, v3, v4], proximity_um=1.0)
        assert len(clusters) == 2
        assert clusters[0].total_violations >= clusters[1].total_violations

    def test_cluster_bbox(self):
        v1 = _violation("m1.1", 0, 0, w=0.1, h=1.0)
        v2 = _violation("m1.2", 0.5, 0, w=0.1, h=1.0)
        clusters = cluster_violations([v1, v2], proximity_um=1.0)
        bbox = clusters[0].bbox
        assert bbox[0] == 0.0
        assert bbox[2] == 0.6  # 0.5 + 0.1

    def test_cluster_categories(self):
        v1 = _violation("m1.1", 0, 0)
        v2 = _violation("m1.2", 0.5, 0)
        clusters = cluster_violations([v1, v2], proximity_um=1.0)
        assert clusters[0].categories == {"m1.1", "m1.2"}

    def test_custom_proximity(self):
        v1 = _violation("m1.1", 0, 0)
        v2 = _violation("m1.2", 3, 0)
        # With small proximity, separate
        clusters = cluster_violations([v1, v2], proximity_um=1.0)
        assert len(clusters) == 2
        # With large proximity, together
        clusters = cluster_violations([v1, v2], proximity_um=5.0)
        assert len(clusters) == 1


class TestViolationCluster:
    def test_empty_cluster(self):
        c = ViolationCluster()
        assert c.total_violations == 0
        assert c.categories == set()
        assert c.bbox == (0.0, 0.0, 0.0, 0.0)
