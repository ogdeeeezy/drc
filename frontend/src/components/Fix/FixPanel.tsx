/**
 * Fix panel — displays fix suggestions with preview and apply actions.
 */
import { useCallback, useState } from "react";
import { api, type SuggestResult, type PreviewResult } from "../../api/client";
import { FixPreview } from "./FixPreview";

interface Props {
  jobId: string;
  result: SuggestResult;
}

export function FixPanel({ jobId, result }: Props) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);

  const toggleSelect = useCallback((idx: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }, []);

  const handlePreview = useCallback(
    async (idx: number) => {
      try {
        const p = await api.previewFix(jobId, idx);
        setPreview(p);
      } catch {
        setPreview(null);
      }
    },
    [jobId]
  );

  const handleApply = useCallback(async () => {
    if (selected.size === 0) return;
    setApplying(true);
    try {
      await api.applyFixes(jobId, [...selected]);
      setApplied(true);
    } catch {
      // error handling
    } finally {
      setApplying(false);
    }
  }, [jobId, selected]);

  const confidenceColor: Record<string, string> = {
    high: "#4ecdc4",
    medium: "#f5a623",
    low: "#e94560",
  };

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
          Fix Suggestions ({result.total_suggestions})
        </h3>
        <button
          onClick={handleApply}
          disabled={selected.size === 0 || applying || applied}
          style={{
            fontSize: 11,
            padding: "4px 10px",
            background: applied ? "#4ecdc4" : "#e94560",
            color: "#fff",
            border: "none",
            borderRadius: 4,
            cursor: selected.size === 0 || applying ? "not-allowed" : "pointer",
            opacity: selected.size === 0 ? 0.5 : 1,
          }}
        >
          {applied
            ? "Applied!"
            : applying
              ? "Applying..."
              : `Apply ${selected.size} fixes`}
        </button>
      </div>

      <div
        style={{
          fontSize: 10,
          color: "#666",
          marginBottom: 8,
          display: "flex",
          gap: 12,
        }}
      >
        <span>Fixable: {result.fixable_count}</span>
        <span>Unfixable: {result.unfixable_count}</span>
      </div>

      {result.suggestions.map((s) => {
        const isSelected = selected.has(s.index);
        return (
          <div
            key={s.index}
            style={{
              padding: "8px 10px",
              marginBottom: 4,
              borderRadius: 6,
              background: isSelected ? "#0f3460" : "#1a1a2e",
              border: isSelected
                ? "1px solid #4ecdc4"
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
              <label
                style={{
                  display: "flex",
                  gap: 6,
                  alignItems: "center",
                  cursor: "pointer",
                  fontSize: 13,
                  fontWeight: 600,
                }}
              >
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => toggleSelect(s.index)}
                  disabled={s.creates_new_violations}
                />
                {s.violation_category}
              </label>
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  color: confidenceColor[s.confidence] ?? "#888",
                  background: `${confidenceColor[s.confidence] ?? "#888"}22`,
                  padding: "1px 6px",
                  borderRadius: 10,
                }}
              >
                {s.confidence}
              </span>
            </div>
            <div style={{ fontSize: 11, color: "#999", marginTop: 2 }}>
              {s.description}
            </div>
            <div
              style={{
                display: "flex",
                gap: 8,
                marginTop: 4,
                alignItems: "center",
              }}
            >
              <span style={{ fontSize: 10, color: "#666" }}>
                P{s.priority} | {s.delta_count} changes | {s.rule_type}
              </span>
              <button
                onClick={() => handlePreview(s.index)}
                style={{
                  fontSize: 10,
                  padding: "1px 6px",
                  background: "transparent",
                  color: "#4ecdc4",
                  border: "1px solid #4ecdc4",
                  borderRadius: 3,
                  cursor: "pointer",
                  marginLeft: "auto",
                }}
              >
                Preview
              </button>
            </div>
            {s.creates_new_violations && (
              <div
                style={{ fontSize: 10, color: "#e94560", marginTop: 4 }}
              >
                Warning: may create new violations
              </div>
            )}
            {s.validation_notes && (
              <div style={{ fontSize: 10, color: "#888", marginTop: 2 }}>
                {s.validation_notes}
              </div>
            )}
          </div>
        );
      })}

      {preview && <FixPreview preview={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}
