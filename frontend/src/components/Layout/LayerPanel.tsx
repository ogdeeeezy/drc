/**
 * Layer panel — toggle layer visibility with color swatches.
 */
import type { LayerData } from "../../api/client";

interface Props {
  layers: LayerData[];
  hiddenLayers: Set<string>;
  onToggle: (key: string) => void;
}

export function LayerPanel({ layers, hiddenLayers, onToggle }: Props) {
  return (
    <div style={{ padding: 8 }}>
      <h3
        style={{
          fontSize: 12,
          fontWeight: 600,
          color: "#888",
          textTransform: "uppercase",
          marginBottom: 8,
          letterSpacing: 1,
        }}
      >
        Layers
      </h3>
      {layers.map((layer) => {
        const key = `${layer.gds_layer}:${layer.gds_datatype}`;
        const hidden = hiddenLayers.has(key);
        return (
          <div
            key={key}
            onClick={() => onToggle(key)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "4px 6px",
              cursor: "pointer",
              borderRadius: 4,
              opacity: hidden ? 0.4 : 1,
              fontSize: 12,
            }}
          >
            <div
              style={{
                width: 14,
                height: 14,
                borderRadius: 3,
                background: layer.color,
                border: "1px solid rgba(255,255,255,0.2)",
                flexShrink: 0,
              }}
            />
            <span style={{ flex: 1 }}>{layer.name}</span>
            <span style={{ color: "#666", fontSize: 10 }}>
              {layer.polygons.length}
            </span>
          </div>
        );
      })}
    </div>
  );
}
