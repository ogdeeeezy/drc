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
}

/** Minimum zoom box size in microns — keeps markers visible in context */
const MIN_ZOOM_SPAN = 3;

/** Zoom multiplier for double-click zoom-in */
const DBLCLICK_ZOOM_FACTOR = 3;

export function LayoutViewer({ layout, hiddenLayers, selectedViolation, selectedMarkerIndex }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<WebGLRenderer | null>(null);
  const isDragging = useRef(false);
  const lastPos = useRef({ x: 0, y: 0 });
  const hiddenLayersRef = useRef(hiddenLayers);
  hiddenLayersRef.current = hiddenLayers;

  const [cursorCoords, setCursorCoords] = useState<{ x: number; y: number } | null>(null);
  const [markerScreen, setMarkerScreen] = useState<{ x: number; y: number } | null>(null);
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

  // Zoom to selected violation/marker and render marker rectangles
  useEffect(() => {
    const renderer = rendererRef.current;
    if (!renderer) return;

    if (!selectedViolation) {
      renderer.clearMarkers();
      renderer.render(hiddenLayers);
      return;
    }

    const geometries = selectedViolation.geometries;
    const idx = selectedMarkerIndex ?? 0;
    const targetBbox = geometries.length > 0 ? geometries[idx]?.bbox ?? selectedViolation.bbox : selectedViolation.bbox;

    // Ensure minimum zoom span so tiny markers are visible in context
    const cx = (targetBbox[0] + targetBbox[2]) / 2;
    const cy = (targetBbox[1] + targetBbox[3]) / 2;
    const halfW = Math.max((targetBbox[2] - targetBbox[0]) / 2, MIN_ZOOM_SPAN / 2);
    const halfH = Math.max((targetBbox[3] - targetBbox[1]) / 2, MIN_ZOOM_SPAN / 2);
    renderer.zoomToBox([cx - halfW, cy - halfH, cx + halfW, cy + halfH]);

    if (geometries.length > 0) {
      renderer.setMarkers(geometries, selectedMarkerIndex ?? 0);
    }
    renderer.render(hiddenLayers);

    // Update crosshair screen position
    const markerCx = (targetBbox[0] + targetBbox[2]) / 2;
    const markerCy = (targetBbox[1] + targetBbox[3]) / 2;
    const screen = renderer.worldToScreen(markerCx, markerCy);
    const size = renderer.getSize();
    setMarkerScreen({ x: screen.x, y: size.height - screen.y }); // flip Y for CSS
  }, [selectedViolation, selectedMarkerIndex, hiddenLayers]);

  // Handle resize
  useEffect(() => {
    const handleResize = () => {
      const canvas = canvasRef.current;
      if (!canvas || !rendererRef.current) return;
      const rect = canvas.parentElement!.getBoundingClientRect();
      rendererRef.current.resize(rect.width, rect.height);
      rendererRef.current.render(hiddenLayersRef.current);
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
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Update crosshair screen position from current selected marker
  const updateCrosshair = useCallback(() => {
    const renderer = rendererRef.current;
    if (!renderer || !selectedViolation) {
      setMarkerScreen(null);
      return;
    }
    const geoms = selectedViolation.geometries;
    const idx = selectedMarkerIndex ?? 0;
    const bbox = geoms.length > 0 ? geoms[idx]?.bbox ?? selectedViolation.bbox : selectedViolation.bbox;
    const cx = (bbox[0] + bbox[2]) / 2;
    const cy = (bbox[1] + bbox[3]) / 2;
    const screen = renderer.worldToScreen(cx, cy);
    const size = renderer.getSize();
    setMarkerScreen({ x: screen.x, y: size.height - screen.y });
  }, [selectedViolation, selectedMarkerIndex]);

  // Keep ref in sync for use in non-reactive event handlers
  updateCrosshairRef.current = updateCrosshair;

  // Mouse handlers for pan
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    isDragging.current = true;
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
      lastPos.current = { x: e.clientX, y: e.clientY };
      renderer.pan(dx, dy);
      renderer.render(hiddenLayers);
      updateCrosshair();
    },
    [hiddenLayers]
  );

  const onMouseUp = useCallback(() => {
    isDragging.current = false;
  }, []);

  const onMouseLeave = useCallback(() => {
    isDragging.current = false;
    setCursorCoords(null);
  }, []);

  // Double-click to zoom in 3x at cursor position
  const onDoubleClick = useCallback((e: React.MouseEvent) => {
    if (!rendererRef.current) return;
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = rect.height - (e.clientY - rect.top); // flip Y
    rendererRef.current.zoom(DBLCLICK_ZOOM_FACTOR, cx, cy);
    rendererRef.current.render(hiddenLayersRef.current);
    updateCrosshair();
  }, [updateCrosshair]);

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

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <canvas
        ref={canvasRef}
        style={{ width: "100%", height: "100%", cursor: "grab" }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseLeave}
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
      {/* Pulsing crosshair at selected marker */}
      {markerScreen && (
        <div
          style={{
            position: "absolute",
            left: markerScreen.x,
            top: markerScreen.y,
            transform: "translate(-50%, -50%)",
            pointerEvents: "none",
            zIndex: 10,
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
