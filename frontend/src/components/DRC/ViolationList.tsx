/**
 * Violation list — sortable list of DRC violations with severity indicators.
 */
import { useState } from "react";
import type { Violation } from "../../api/client";

interface Props {
  violations: Violation[];
  selected: Violation | null;
  onSelect: (v: Violation | null) => void;
  selectedMarkerIndex: number | null;
  onSelectMarker: (idx: number | null) => void;
}

type SortKey = "severity" | "count" | "category";

export function ViolationList({ violations, selected, onSelect, selectedMarkerIndex, onSelectMarker }: Props) {
  const [sortBy, setSortBy] = useState<SortKey>("severity");

  const sorted = [...violations].sort((a, b) => {
    if (sortBy === "severity") return b.severity - a.severity;
    if (sortBy === "count") return b.count - a.count;
    return a.category.localeCompare(b.category);
  });

  const total = violations.reduce((sum, v) => sum + v.count, 0);

  return (
    <div style={{ padding: 8 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 8,
        }}
      >
        <h3
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: "#888",
            textTransform: "uppercase",
            letterSpacing: 1,
          }}
        >
          Violations ({total})
        </h3>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as SortKey)}
          style={{
            background: "#1a1a2e",
            color: "#ccc",
            border: "1px solid #333",
            borderRadius: 4,
            padding: "2px 4px",
            fontSize: 11,
          }}
        >
          <option value="severity">Severity</option>
          <option value="count">Count</option>
          <option value="category">Rule</option>
        </select>
      </div>

      {sorted.map((v) => {
        const isSelected = selected === v;
        return (
          <div
            key={`${v.category}-${v.cell_name}`}
            onClick={() => onSelect(isSelected ? null : v)}
            style={{
              padding: "8px 10px",
              marginBottom: 4,
              borderRadius: 6,
              cursor: "pointer",
              background: isSelected ? "#0f3460" : "#1a1a2e",
              border: isSelected
                ? "1px solid #e94560"
                : "1px solid transparent",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <span style={{ fontWeight: 600, fontSize: 13 }}>
                {v.category}
              </span>
              <SeverityBadge severity={v.severity} />
            </div>
            <div style={{ fontSize: 11, color: "#999", marginTop: 2 }}>
              {v.description}
            </div>
            <div
              style={{
                display: "flex",
                gap: 12,
                fontSize: 10,
                color: "#666",
                marginTop: 4,
              }}
            >
              <span>{v.count} markers</span>
              {v.rule_type && <span>{v.rule_type}</span>}
              {v.value_um != null && <span>{v.value_um} um</span>}
            </div>
            {isSelected && v.geometries.length > 1 && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginTop: 6,
                  paddingTop: 6,
                  borderTop: "1px solid #333",
                }}
              >
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    const idx = selectedMarkerIndex ?? 0;
                    onSelectMarker(idx > 0 ? idx - 1 : v.geometries.length - 1);
                  }}
                  style={{
                    background: "#0f3460",
                    color: "#ccc",
                    border: "1px solid #333",
                    borderRadius: 4,
                    padding: "2px 8px",
                    fontSize: 11,
                    cursor: "pointer",
                  }}
                >
                  Prev
                </button>
                <span style={{ fontSize: 11, color: "#999" }}>
                  Marker {(selectedMarkerIndex ?? 0) + 1} of {v.geometries.length}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    const idx = selectedMarkerIndex ?? 0;
                    onSelectMarker(idx < v.geometries.length - 1 ? idx + 1 : 0);
                  }}
                  style={{
                    background: "#0f3460",
                    color: "#ccc",
                    border: "1px solid #333",
                    borderRadius: 4,
                    padding: "2px 8px",
                    fontSize: 11,
                    cursor: "pointer",
                  }}
                >
                  Next
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function SeverityBadge({ severity }: { severity: number }) {
  const color =
    severity >= 8
      ? "#e94560"
      : severity >= 5
        ? "#f5a623"
        : "#4ecdc4";
  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 700,
        color,
        background: `${color}22`,
        padding: "1px 6px",
        borderRadius: 10,
      }}
    >
      S{severity}
    </span>
  );
}
