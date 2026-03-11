/**
 * Violation overlay — renders violation markers on top of the layout viewer.
 * Uses CSS-based overlay (simpler than integrating into WebGL pipeline).
 */
import type { Violation } from "../../api/client";

interface Props {
  violations: Violation[];
  layoutBbox: number[];
  selectedViolation: Violation | null;
  selectedMarkerIndex: number | null;
}

export function ViolationOverlay({
  violations,
  layoutBbox: _layoutBbox,
  selectedViolation,
  selectedMarkerIndex,
}: Props) {
  // Render summary badge in top-right of the viewer
  const total = violations.reduce((sum, v) => sum + v.count, 0);
  const categories = violations.length;

  return (
    <div
      style={{
        position: "absolute",
        top: 8,
        right: 8,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          background: "rgba(26, 26, 46, 0.9)",
          padding: "8px 12px",
          borderRadius: 8,
          border: "1px solid #0f3460",
          fontSize: 12,
        }}
      >
        <div style={{ fontWeight: 600, color: "#e94560" }}>
          {total} violations
        </div>
        <div style={{ color: "#888", fontSize: 10 }}>
          {categories} rule categories
        </div>
        {selectedViolation && (
          <div
            style={{
              marginTop: 6,
              paddingTop: 6,
              borderTop: "1px solid #333",
              color: "#ccc",
            }}
          >
            <div style={{ fontWeight: 600 }}>{selectedViolation.category}</div>
            <div style={{ fontSize: 10, color: "#888" }}>
              {selectedViolation.description}
            </div>
            {selectedMarkerIndex != null && selectedViolation.geometries.length > 0 && (
              <div style={{ fontSize: 10, color: "#e94560", marginTop: 4, fontWeight: 600 }}>
                Marker {selectedMarkerIndex + 1} of {selectedViolation.geometries.length}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
