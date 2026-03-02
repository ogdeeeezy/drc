"""Spatial clustering of DRC violations.

Groups nearby violations so that fix strategies can consider interactions
between violations in the same region (e.g., fixing one spacing violation
might affect an adjacent width violation).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.core.geometry_utils import bboxes_overlap
from backend.core.violation_models import Violation, ViolationGeometry


@dataclass
class ViolationCluster:
    """A group of spatially-related violations."""

    violations: list[Violation] = field(default_factory=list)
    geometries: list[ViolationGeometry] = field(default_factory=list)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """Combined bounding box of all violations in the cluster."""
        if not self.violations:
            return (0.0, 0.0, 0.0, 0.0)
        bboxes = [v.bbox for v in self.violations]
        return (
            min(b[0] for b in bboxes),
            min(b[1] for b in bboxes),
            max(b[2] for b in bboxes),
            max(b[3] for b in bboxes),
        )

    @property
    def total_violations(self) -> int:
        return sum(v.violation_count for v in self.violations)

    @property
    def categories(self) -> set[str]:
        return {v.category for v in self.violations}


def _expand_bbox(
    bbox: tuple[float, float, float, float], margin: float
) -> tuple[float, float, float, float]:
    return (bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin)


def cluster_violations(
    violations: list[Violation],
    proximity_um: float = 1.0,
) -> list[ViolationCluster]:
    """Cluster violations by spatial proximity.

    Uses a single-linkage approach: violations whose bounding boxes
    (expanded by proximity_um) overlap are placed in the same cluster.

    Args:
        violations: List of violations to cluster.
        proximity_um: Maximum distance (in microns) for two violations
            to be considered in the same cluster.

    Returns:
        List of ViolationClusters, sorted by total violation count (descending).
    """
    if not violations:
        return []

    # Flatten to individual (violation, geometry) pairs with bboxes
    items: list[tuple[Violation, tuple[float, float, float, float]]] = []
    for v in violations:
        if v.geometries:
            items.append((v, v.bbox))
        else:
            # Violation with no geometry — still include it
            items.append((v, (0.0, 0.0, 0.0, 0.0)))

    n = len(items)
    # Union-Find for clustering
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Check pairwise proximity
    for i in range(n):
        bbox_i = _expand_bbox(items[i][1], proximity_um)
        for j in range(i + 1, n):
            bbox_j = items[j][1]
            if bboxes_overlap(bbox_i, bbox_j):
                union(i, j)

    # Group by cluster root
    groups: dict[int, list[Violation]] = {}
    for i in range(n):
        root = find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(items[i][0])

    clusters = []
    for group_violations in groups.values():
        cluster = ViolationCluster(violations=group_violations)
        # Collect all geometries
        for v in group_violations:
            cluster.geometries.extend(v.geometries)
        clusters.append(cluster)

    # Sort by total violations descending (biggest clusters first)
    clusters.sort(key=lambda c: c.total_violations, reverse=True)
    return clusters
