/**
 * MismatchList — LVS mismatch viewer with match/nomatch banner,
 * summary stats, and sortable mismatch table.
 */
import { useState } from "react";
import type { LVSMismatch, LVSResultsResponse } from "../../api/client";

interface Props {
  results: LVSResultsResponse;
  selected: LVSMismatch | null;
  onSelect: (m: LVSMismatch | null) => void;
}

type SortKey = "type" | "name";

const TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  missing_device: { label: "Missing Device", color: "#e94560" },
  extra_device: { label: "Extra Device", color: "#f5a623" },
  net_mismatch: { label: "Net Mismatch", color: "#f7dc6f" },
  pin_mismatch: { label: "Pin Mismatch", color: "#5dade2" },
  parameter_mismatch: { label: "Param Mismatch", color: "#888" },
};

function getTypeConfig(type: string) {
  return TYPE_CONFIG[type] ?? { label: type, color: "#888" };
}

export function MismatchList({ results, selected, onSelect }: Props) {
  const [sortBy, setSortBy] = useState<SortKey>("type");
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  const sorted = [...results.mismatches].sort((a, b) => {
    if (sortBy === "type") return a.type.localeCompare(b.type);
    return a.name.localeCompare(b.name);
  });

  return (
    <div style={{ padding: 8 }}>
      {/* Match / Nomatch banner */}
      <div
        style={{
          padding: "10px 12px",
          borderRadius: 6,
          marginBottom: 8,
          background: results.match ? "#1a4a3a" : "#4a1a2a",
          border: results.match
            ? "1px solid #4ecdc4"
            : "1px solid #e94560",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <span style={{ fontSize: 18 }}>
          {results.match ? "\u2714" : "\u2718"}
        </span>
        <span
          style={{
            fontSize: 14,
            fontWeight: 700,
            color: results.match ? "#4ecdc4" : "#e94560",
          }}
        >
          {results.match ? "LVS Clean — Layout matches schematic" : "LVS Mismatch"}
        </span>
      </div>

      {/* Summary stats */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 6,
          marginBottom: 10,
        }}
      >
        <StatBox
          label="Devices Matched"
          value={results.devices_matched}
          color="#4ecdc4"
        />
        <StatBox
          label="Devices Mismatched"
          value={results.devices_mismatched}
          color={results.devices_mismatched > 0 ? "#e94560" : "#4ecdc4"}
        />
        <StatBox
          label="Nets Matched"
          value={results.nets_matched}
          color="#4ecdc4"
        />
        <StatBox
          label="Nets Mismatched"
          value={results.nets_mismatched}
          color={results.nets_mismatched > 0 ? "#e94560" : "#4ecdc4"}
        />
      </div>

      {/* Mismatch list header */}
      {results.mismatches.length > 0 && (
        <>
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
              Mismatches ({results.mismatches.length})
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
              <option value="type">Type</option>
              <option value="name">Name</option>
            </select>
          </div>

          {/* Mismatch items */}
          {sorted.map((m, idx) => {
            const isSelected = selected === m;
            const isExpanded = expandedIdx === idx;
            const cfg = getTypeConfig(m.type);

            return (
              <div
                key={`${m.type}-${m.name}-${idx}`}
                onClick={() => onSelect(isSelected ? null : m)}
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
                    {m.name}
                  </span>
                  <TypeBadge type={m.type} />
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
                  <span>{cfg.label}</span>
                </div>

                {/* Expected vs Actual row */}
                <div
                  style={{
                    display: "flex",
                    gap: 8,
                    fontSize: 11,
                    marginTop: 6,
                  }}
                >
                  {m.expected && (
                    <span style={{ color: "#4ecdc4" }}>
                      Exp: {m.expected}
                    </span>
                  )}
                  {m.actual && (
                    <span style={{ color: "#e94560" }}>
                      Act: {m.actual}
                    </span>
                  )}
                </div>

                {/* Collapsible details */}
                {m.details && (
                  <>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandedIdx(isExpanded ? null : idx);
                      }}
                      style={{
                        background: "none",
                        border: "none",
                        color: "#5dade2",
                        fontSize: 10,
                        cursor: "pointer",
                        padding: "2px 0",
                        marginTop: 4,
                      }}
                    >
                      {isExpanded ? "Hide details" : "Show details"}
                    </button>
                    {isExpanded && (
                      <div
                        style={{
                          fontSize: 11,
                          color: "#999",
                          marginTop: 4,
                          padding: "6px 8px",
                          background: "#16213e",
                          borderRadius: 4,
                          whiteSpace: "pre-wrap",
                          overflowX: "auto",
                        }}
                      >
                        {m.details}
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}

function StatBox({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div
      style={{
        padding: "6px 8px",
        background: "#1a1a2e",
        borderRadius: 4,
        textAlign: "center",
      }}
    >
      <div style={{ fontSize: 18, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 10, color: "#888" }}>{label}</div>
    </div>
  );
}

function TypeBadge({ type }: { type: string }) {
  const cfg = getTypeConfig(type);
  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 700,
        color: cfg.color,
        background: `${cfg.color}22`,
        padding: "1px 6px",
        borderRadius: 10,
        whiteSpace: "nowrap",
      }}
    >
      {cfg.label}
    </span>
  );
}
