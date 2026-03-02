"""Geometry utilities — grid snap, measurements, polygon operations."""

from __future__ import annotations

import math


def snap_to_grid(value: float, grid: float = 0.005) -> float:
    """Snap a coordinate value to the nearest grid point."""
    return round(value / grid) * grid


def snap_point_to_grid(x: float, y: float, grid: float = 0.005) -> tuple[float, float]:
    """Snap a point (x, y) to the nearest grid point."""
    return (snap_to_grid(x, grid), snap_to_grid(y, grid))


def polygon_area(points: list[tuple[float, float]]) -> float:
    """Compute area of a simple polygon using the shoelace formula. Returns positive value."""
    n = len(points)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    return abs(area) / 2.0


def polygon_bbox(
    points: list[tuple[float, float]],
) -> tuple[float, float, float, float]:
    """Return (xmin, ymin, xmax, ymax) bounding box of a polygon."""
    if not points:
        raise ValueError("Cannot compute bbox of empty polygon")
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_width(bbox: tuple[float, float, float, float]) -> float:
    """Width (x-extent) of a bounding box."""
    return bbox[2] - bbox[0]


def bbox_height(bbox: tuple[float, float, float, float]) -> float:
    """Height (y-extent) of a bounding box."""
    return bbox[3] - bbox[1]


def bboxes_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    """Check if two bounding boxes overlap (touching counts as overlap)."""
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def point_distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """Euclidean distance between two points."""
    return math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)


def min_edge_width(points: list[tuple[float, float]]) -> float:
    """Estimate the minimum width of a polygon from its bounding box.

    For rectilinear polygons, this is min(width, height) of the bbox.
    A more accurate measurement would use medial axis, but bbox is sufficient
    for DRC-level checks.
    """
    bbox = polygon_bbox(points)
    return min(bbox_width(bbox), bbox_height(bbox))


def is_on_grid(value: float, grid: float = 0.005) -> bool:
    """Check if a value is on the manufacturing grid."""
    remainder = abs(value / grid - round(value / grid))
    return remainder < 1e-9
