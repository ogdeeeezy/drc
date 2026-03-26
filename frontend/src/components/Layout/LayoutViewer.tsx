/**
 * Layout viewer — WebGL canvas with pan/zoom for GDSII layout display.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { LayoutData, Violation } from "../../api/client";
import { WebGLRenderer } from "./WebGLRenderer";

interface Props {
  layout: LayoutData;
  hiddenLayers: Set<string>;
  selectedViolation: Violation | null;
  selectedMarkerIndex: number | null;
  onMarkerClick?: (idx: number) => void;
}

/** Minimum zoom box size in microns — keeps markers visible in context */
const MIN_ZOOM_SPAN = 3;

/** Zoom multiplier for double-click zoom-in */
const DBLCLICK_ZOOM_FACTOR = 3;

export function LayoutViewer({ layout, hiddenLayers, selectedViolation, selectedMarkerIndex, onMarkerClick }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<WebGLRenderer | null>(null);
  const isDragging = useRef(false);
  const dragMoved = useRef(false);
  const lastPos = useRef({ x: 0, y: 0 });
  const hiddenLayersRef = useRef(hiddenLayers);
  hiddenLayersRef.current = hiddenLayers;

  const [cursorCoords, setCursorCoords] = useState<{ x: number; y: number } | null>(null);
  const [markerScreenPositions, setMarkerScreenPositions] = useState<{ x: number; y: number }[]>([]);
  const updateCrosshairRef = useRef<() => void>(() => {});

  // Initialize renderer
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.parentElement!.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;

    const renderer = new WebGLRenderer(canvas);
    renderer.setLayers(layout.layers, layout.bbox);
    renderer.render(hiddenLayers);
    rendererRef.current = renderer;

    return () => {
      renderer.destroy();
      rendererRef.current = null;
    };
  }, [layout]);

  // Re-render on layer visibility change
  useEffect(() => {
    rendererRef.current?.render(hiddenLayers);
  }, [hiddenLayers]);

  // Update all marker screen positions
  const updateMarkerPositions = useCallback(() => {
    const renderer = rendererRef.current;
    if (!renderer || !selectedViolation) {
      setMarkerScreenPositions([]);
      return;
    }
    const geoms = selectedViolation.geometries;
    const size = renderer.getSize();
    const positions = geoms.map((g) => {
      const cx = (g.bbox[0] + g.bbox[2]) / 2;
      const cy = (g.bbox[1] + g.bbox[3]) / 2;
      const screen = renderer.worldToScreen(cx, cy);
      return { x: screen.x, y: size.height - screen.y }; // flip Y for CSS
    });
    setMarkerScreenPositions(positions);
  }, [selectedViolation]);

  // Keep ref in sync for use in non-reactive event handlers
  updateCrosshairRef.current = updateMarkerPositions;

  // Zoom to selected violation/marker and render marker rectangles
  useEffect(() => {
    const renderer = rendererRef.current;
    if (!renderer) return;

    if (!selectedViolation) {
      renderer.clearMarkers();
      renderer.render(hiddenLayers);
      setMarkerScreenPositions([]);
      return;
    }

    const geometries = selectedViolation.geometries;

    if (selectedMarkerIndex != null && geometries.length > 0) {
      // Zoom to specific marker
      const targetBbox = geometries[selectedMarkerIndex]?.bbox ?? selectedViolation.bbox;
      const cx = (targetBbox[0] + targetBbox[2]) / 2;
      const cy = (targetBbox[1] + targetBbox[3]) / 2;
      const halfW = Math.max((targetBbox[2] - targetBbox[0]) / 2, MIN_ZOOM_SPAN / 2);
      const halfH = Math.max((targetBbox[3] - targetBbox[1]) / 2, MIN_ZOOM_SPAN / 2);
      renderer.zoomToBox([cx - halfW, cy - halfH, cx + halfW, cy + halfH]);
    } else {
      // Zoom to fit ALL markers for the category
      const allBbox = selectedViolation.bbox;
      const cx = (allBbox[0] + allBbox[2]) / 2;
      const cy = (allBbox[1] + allBbox[3]) / 2;
      const halfW = Math.max((allBbox[2] - allBbox[0]) / 2, MIN_ZOOM_SPAN / 2);
      const halfH = Math.max((allBbox[3] - allBbox[1]) / 2, MIN_ZOOM_SPAN / 2);
      renderer.zoomToBox([cx - halfW, cy - halfH, cx + halfW, cy + halfH]);
    }

    if (geometries.length > 0) {
      renderer.setMarkers(geometries, selectedMarkerIndex);
    }
    renderer.render(hiddenLayers);

    updateMarkerPositions();
  }, [selectedViolation, selectedMarkerIndex, hiddenLayers, updateMarkerPositions]);

  // Handle resize
  useEffect(() => {
    const handleResize = () => {
      const canvas = canvasRef.current;
      if (!canvas || !rendererRef.current) return;
      const rect = canvas.parentElement!.getBoundingClientRect();
      rendererRef.current.resize(rect.width, rect.height);
      rendererRef.current.render(hiddenLayersRef.current);
      updateCrosshairRef.current();
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Keyboard shortcut: R to reset view
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "r" || e.key === "R") {
        // Don't trigger if user is typing in an input
        if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
        if (!rendererRef.current) return;
        rendererRef.current.fitView();
        rendererRef.current.render(hiddenLayersRef.current);
        updateCrosshairRef.current();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Mouse handlers for pan
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    isDragging.current = true;
    dragMoved.current = false;
    lastPos.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const renderer = rendererRef.current;
      if (!renderer) return;

      // Update coordinate readout
      const canvas = canvasRef.current!;
      const rect = canvas.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = rect.height - (e.clientY - rect.top); // flip Y for WebGL
      const world = renderer.screenToWorld(sx, sy);
      setCursorCoords(world);

      if (!isDragging.current) return;
      const dx = e.clientX - lastPos.current.x;
      const dy = -(e.clientY - lastPos.current.y); // flip Y for WebGL
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) dragMoved.current = true;
      lastPos.current = { x: e.clientX, y: e.clientY };
      renderer.pan(dx, dy);
      renderer.render(hiddenLayers);
      updateMarkerPositions();
    },
    [hiddenLayers, updateMarkerPositions]
  );

  const onMouseUp = useCallback(() => {
    isDragging.current = false;
  }, []);

  const onMouseLeave = useCallback(() => {
    isDragging.current = false;
    setCursorCoords(null);
  }, []);

  // Click to select a marker on canvas
  const onClick = useCallback((e: React.MouseEvent) => {
    if (dragMoved.current) return; // was a pan, not a click
    if (!rendererRef.current || !selectedViolation || !onMarkerClick) return;

    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = rect.height - (e.clientY - rect.top);
    const world = rendererRef.current.screenToWorld(sx, sy);
    const hitIdx = rendererRef.current.hitTestMarker(world.x, world.y);
    if (hitIdx >= 0) {
      onMarkerClick(hitIdx);
    }
  }, [selectedViolation, onMarkerClick]);

  // Double-click to zoom in 3x at cursor position
  const onDoubleClick = useCallback((e: React.MouseEvent) => {
    if (!rendererRef.current) return;
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = rect.height - (e.clientY - rect.top); // flip Y
    rendererRef.current.zoom(DBLCLICK_ZOOM_FACTOR, cx, cy);
    rendererRef.current.render(hiddenLayersRef.current);
    updateMarkerPositions();
  }, [updateMarkerPositions]);

  // Scroll/pinch wheel for zoom — must be non-passive to prevent browser zoom
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const handleWheel = (e: WheelEvent) => {
      if (!rendererRef.current) return;
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = rect.height - (e.clientY - rect.top); // flip Y
      const factor = e.deltaY > 0 ? 0.9 : 1.1;
      rendererRef.current.zoom(factor, cx, cy);
      rendererRef.current.render(hiddenLayersRef.current);
      updateCrosshairRef.current();
    };

    canvas.addEventListener("wheel", handleWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", handleWheel);
  }, []);

  const formatCoord = (v: number): string => {
    if (Math.abs(v) >= 100) return v.toFixed(1);
    if (Math.abs(v) >= 1) return v.toFixed(2);
    return v.toFixed(3);
  };

  const selectedPos = selectedMarkerIndex != null ? markerScreenPositions[selectedMarkerIndex] : null;
  const selectedGeom = selectedMarkerIndex != null ? selectedViolation?.geometries[selectedMarkerIndex] : null;

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <canvas
        ref={canvasRef}
        style={{ width: "100%", height: "100%", cursor: "grab" }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseLeave}
        onClick={onClick}
        onDoubleClick={onDoubleClick}
      />
      {/* Coordinate readout */}
      {cursorCoords && (
        <div
          style={{
            position: "absolute",
            bottom: 8,
            left: 8,
            background: "rgba(0,0,0,0.7)",
            color: "#ccc",
            padding: "4px 8px",
            borderRadius: 4,
            fontSize: 12,
            fontFamily: "monospace",
            pointerEvents: "none",
            userSelect: "none",
          }}
        >
          X: {formatCoord(cursorCoords.x)} µm &nbsp; Y: {formatCoord(cursorCoords.y)} µm
        </div>
      )}
      {/* Numbered labels at each marker position */}
      {selectedViolation && markerScreenPositions.map((pos, i) => {
        const isActive = i === selectedMarkerIndex;
        return (
          <div
            key={i}
            onClick={(e) => {
              e.stopPropagation();
              onMarkerClick?.(i);
            }}
            style={{
              position: "absolute",
              left: pos.x,
              top: pos.y,
              transform: "translate(-50%, -50%)",
              zIndex: isActive ? 12 : 10,
              cursor: "pointer",
              pointerEvents: "auto",
            }}
          >
            {/* Number badge */}
            <div
              style={{
                width: isActive ? 24 : 20,
                height: isActive ? 24 : 20,
                borderRadius: "50%",
                background: isActive ? "#e94560" : "rgba(233, 69, 96, 0.7)",
                border: isActive ? "2px solid #fff" : "1px solid rgba(255,255,255,0.4)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: isActive ? 11 : 10,
                fontWeight: 700,
                color: "#fff",
                boxShadow: isActive
                  ? "0 0 12px rgba(233, 69, 96, 0.8)"
                  : "0 0 4px rgba(0,0,0,0.5)",
                transition: "all 0.15s ease",
              }}
            >
              {i + 1}
            </div>
          </div>
        );
      })}
      {/* Tooltip at selected marker */}
      {selectedPos && selectedViolation && selectedGeom && (
        <div
          style={{
            position: "absolute",
            left: selectedPos.x,
            top: selectedPos.y - 20,
            transform: "translate(-50%, -100%)",
            zIndex: 20,
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              background: "rgba(26, 26, 46, 0.95)",
              border: "1px solid #e94560",
              borderRadius: 6,
              padding: "6px 10px",
              fontSize: 11,
              minWidth: 140,
              textAlign: "center",
              boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
            }}
          >
            <div style={{ fontWeight: 600, color: "#e94560", fontSize: 12 }}>
              #{(selectedMarkerIndex ?? 0) + 1} — {selectedViolation.category}
            </div>
            <div style={{ color: "#00cccc", fontFamily: "monospace", marginTop: 3, fontSize: 10 }}>
              ({((selectedGeom.bbox[0] + selectedGeom.bbox[2]) / 2).toFixed(2)},{" "}
              {((selectedGeom.bbox[1] + selectedGeom.bbox[3]) / 2).toFixed(2)}) µm
            </div>
            {selectedGeom.edge_pair && (
              <div style={{ color: "#888", fontSize: 9, marginTop: 2 }}>
                Edge pair: {selectedGeom.type}
              </div>
            )}
            {selectedViolation.value_um != null && (
              <div style={{ color: "#f5a623", fontSize: 9, marginTop: 2 }}>
                Rule: {selectedViolation.rule_type} ≥ {selectedViolation.value_um} µm
              </div>
            )}
          </div>
          {/* Tooltip arrow */}
          <div
            style={{
              width: 0,
              height: 0,
              borderLeft: "6px solid transparent",
              borderRight: "6px solid transparent",
              borderTop: "6px solid #e94560",
              margin: "0 auto",
            }}
          />
        </div>
      )}
      {/* Pulsing crosshair at selected marker */}
      {selectedPos && (
        <div
          style={{
            position: "absolute",
            left: selectedPos.x,
            top: selectedPos.y,
            transform: "translate(-50%, -50%)",
            pointerEvents: "none",
            zIndex: 11,
          }}
        >
          {/* Horizontal line */}
          <div style={{
            position: "absolute",
            width: 28,
            height: 2,
            background: "#00ffff",
            left: -14,
            top: -1,
            boxShadow: "0 0 6px #00ffff",
            animation: "pulse-crosshair 1.2s ease-in-out infinite",
          }} />
          {/* Vertical line */}
          <div style={{
            position: "absolute",
            width: 2,
            height: 28,
            background: "#00ffff",
            left: -1,
            top: -14,
            boxShadow: "0 0 6px #00ffff",
            animation: "pulse-crosshair 1.2s ease-in-out infinite",
          }} />
          {/* Outer ring */}
          <div style={{
            position: "absolute",
            width: 24,
            height: 24,
            border: "2px solid #00ffff",
            borderRadius: "50%",
            left: -12,
            top: -12,
            boxShadow: "0 0 8px #00ffff, inset 0 0 4px rgba(0,255,255,0.2)",
            animation: "pulse-crosshair 1.2s ease-in-out infinite",
          }} />
          <style>{`
            @keyframes pulse-crosshair {
              0%, 100% { opacity: 1; }
              50% { opacity: 0.4; }
            }
          `}</style>
        </div>
      )}
      {/* Reset view hint */}
      <div
        style={{
          position: "absolute",
          bottom: 8,
          right: 8,
          background: "rgba(0,0,0,0.5)",
          color: "#888",
          padding: "3px 7px",
          borderRadius: 4,
          fontSize: 11,
          fontFamily: "sans-serif",
          pointerEvents: "none",
          userSelect: "none",
        }}
      >
        R = reset view
      </div>
    </div>
  );
}
