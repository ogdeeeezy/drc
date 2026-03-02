/**
 * Fix preview — shows before/after polygon diff for a fix suggestion.
 */
import type { PreviewResult } from "../../api/client";

interface Props {
  preview: PreviewResult;
  onClose: () => void;
}

export function FixPreview({ preview, onClose }: Props) {
  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0,0,0,0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#16213e",
          borderRadius: 12,
          padding: 20,
          maxWidth: 700,
          maxHeight: "80vh",
          overflow: "auto",
          border: "1px solid #0f3460",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 16,
          }}
        >
          <h3 style={{ fontSize: 14, fontWeight: 600 }}>
            Fix Preview — Suggestion #{preview.suggestion_index}
          </h3>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "#888",
              fontSize: 18,
              cursor: "pointer",
            }}
          >
            x
          </button>
        </div>

        <div style={{ fontSize: 12, color: "#999", marginBottom: 12 }}>
          {preview.description} (confidence: {preview.confidence})
        </div>

        {preview.deltas.map((delta, i) => (
          <div
            key={i}
            style={{
              marginBottom: 12,
              padding: 12,
              background: "#1a1a2e",
              borderRadius: 8,
            }}
          >
            <div
              style={{
                fontSize: 11,
                color: "#888",
                marginBottom: 8,
              }}
            >
              Cell: {delta.cell_name} | Layer: {delta.gds_layer}:
              {delta.gds_datatype}
              {delta.is_removal && (
                <span style={{ color: "#e94560", marginLeft: 8 }}>REMOVE</span>
              )}
              {delta.is_addition && (
                <span style={{ color: "#4ecdc4", marginLeft: 8 }}>ADD</span>
              )}
            </div>

            <div style={{ display: "flex", gap: 16 }}>
              {/* Before */}
              <div style={{ flex: 1 }}>
                <div
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    color: "#e94560",
                    marginBottom: 4,
                  }}
                >
                  BEFORE
                </div>
                <PointsSVG
                  points={delta.original_points}
                  color="#e94560"
                  otherPoints={delta.modified_points}
                />
              </div>

              {/* After */}
              <div style={{ flex: 1 }}>
                <div
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    color: "#4ecdc4",
                    marginBottom: 4,
                  }}
                >
                  AFTER
                </div>
                <PointsSVG
                  points={delta.modified_points}
                  color="#4ecdc4"
                  otherPoints={delta.original_points}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PointsSVG({
  points,
  color,
  otherPoints,
}: {
  points: number[][];
  color: string;
  otherPoints: number[][];
}) {
  if (points.length === 0 && otherPoints.length === 0) {
    return (
      <div style={{ fontSize: 11, color: "#666", padding: 8 }}>
        No polygon
      </div>
    );
  }

  // Compute bounds from both sets for consistent scaling
  const allPts = [...points, ...otherPoints];
  const xs = allPts.map((p) => p[0]);
  const ys = allPts.map((p) => p[1]);
  const xmin = Math.min(...xs);
  const xmax = Math.max(...xs);
  const ymin = Math.min(...ys);
  const ymax = Math.max(...ys);
  const w = xmax - xmin || 0.1;
  const h = ymax - ymin || 0.1;
  const padding = Math.max(w, h) * 0.15;

  const svgW = 200;
  const svgH = 150;
  const scaleX = svgW / (w + padding * 2);
  const scaleY = svgH / (h + padding * 2);
  const scale = Math.min(scaleX, scaleY);

  const toSVG = (pt: number[]) => {
    const x = (pt[0] - xmin + padding) * scale;
    const y = svgH - (pt[1] - ymin + padding) * scale;
    return `${x},${y}`;
  };

  const pathData =
    points.length > 0
      ? `M ${points.map(toSVG).join(" L ")} Z`
      : "";

  return (
    <svg
      width={svgW}
      height={svgH}
      style={{ background: "#0d0d1a", borderRadius: 4 }}
    >
      {pathData && (
        <path
          d={pathData}
          fill={`${color}33`}
          stroke={color}
          strokeWidth={1.5}
        />
      )}
    </svg>
  );
}
