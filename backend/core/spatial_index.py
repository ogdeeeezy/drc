"""Spatial index for fast polygon lookups using R-tree."""

from __future__ import annotations

from dataclasses import dataclass

from rtree import index

from backend.core.geometry_utils import polygon_bbox
from backend.core.layout import PolygonInfo


@dataclass
class IndexedPolygon:
    """A polygon with its spatial index ID and metadata."""

    index_id: int
    polygon: PolygonInfo
    bbox: tuple[float, float, float, float]


class SpatialIndex:
    """R-tree spatial index over layout polygons.

    Enables fast queries like:
    - Find all polygons near a violation
    - Find polygons on a specific layer within a bounding box
    - Find nearest neighbors to a point or region
    """

    def __init__(self):
        self._idx = index.Index()
        self._polygons: dict[int, IndexedPolygon] = {}
        self._next_id = 0

    @property
    def count(self) -> int:
        return len(self._polygons)

    def insert(self, polygon: PolygonInfo) -> int:
        """Insert a polygon into the index. Returns its index ID."""
        bbox = polygon_bbox(polygon.points)
        idx_id = self._next_id
        self._next_id += 1
        self._idx.insert(idx_id, bbox)
        self._polygons[idx_id] = IndexedPolygon(index_id=idx_id, polygon=polygon, bbox=bbox)
        return idx_id

    def insert_many(self, polygons: list[PolygonInfo]) -> list[int]:
        """Insert multiple polygons. Returns list of index IDs."""
        return [self.insert(p) for p in polygons]

    def query_bbox(
        self,
        bbox: tuple[float, float, float, float],
        layer: int | None = None,
        datatype: int | None = None,
    ) -> list[IndexedPolygon]:
        """Find all polygons whose bounding boxes intersect the given bbox.

        Optionally filter by GDS layer and/or datatype.
        """
        hits = self._idx.intersection(bbox)
        results = []
        for idx_id in hits:
            ip = self._polygons[idx_id]
            if layer is not None and ip.polygon.gds_layer != layer:
                continue
            if datatype is not None and ip.polygon.gds_datatype != datatype:
                continue
            results.append(ip)
        return results

    def query_point(
        self,
        x: float,
        y: float,
        layer: int | None = None,
    ) -> list[IndexedPolygon]:
        """Find all polygons whose bounding boxes contain the given point."""
        return self.query_bbox((x, y, x, y), layer=layer)

    def query_nearby(
        self,
        bbox: tuple[float, float, float, float],
        margin: float,
        layer: int | None = None,
        datatype: int | None = None,
    ) -> list[IndexedPolygon]:
        """Find polygons within `margin` distance of a bounding box."""
        expanded = (
            bbox[0] - margin,
            bbox[1] - margin,
            bbox[2] + margin,
            bbox[3] + margin,
        )
        return self.query_bbox(expanded, layer=layer, datatype=datatype)

    def nearest(
        self,
        bbox: tuple[float, float, float, float],
        num_results: int = 1,
        layer: int | None = None,
    ) -> list[IndexedPolygon]:
        """Find the N nearest polygons to a bounding box."""
        # Request extra to allow filtering
        candidates = list(self._idx.nearest(bbox, num_results=num_results * 3))
        results = []
        for idx_id in candidates:
            if idx_id not in self._polygons:
                continue
            ip = self._polygons[idx_id]
            if layer is not None and ip.polygon.gds_layer != layer:
                continue
            results.append(ip)
            if len(results) >= num_results:
                break
        return results

    def get(self, index_id: int) -> IndexedPolygon:
        """Get a polygon by its index ID."""
        if index_id not in self._polygons:
            raise KeyError(f"Index ID {index_id} not found")
        return self._polygons[index_id]

    def remove(self, index_id: int) -> None:
        """Remove a polygon from the index."""
        if index_id not in self._polygons:
            raise KeyError(f"Index ID {index_id} not found")
        ip = self._polygons.pop(index_id)
        self._idx.delete(index_id, ip.bbox)

    @classmethod
    def from_polygons(cls, polygons: list[PolygonInfo]) -> "SpatialIndex":
        """Create a spatial index from a list of polygons."""
        si = cls()
        si.insert_many(polygons)
        return si
