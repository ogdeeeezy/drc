/**
 * Layout viewer — WebGL canvas with pan/zoom for GDSII layout display.
 */
import { useCallback, useEffect, useRef } from "react";
import type { LayoutData, Violation } from "../../api/client";
import { WebGLRenderer } from "./WebGLRenderer";

interface Props {
  layout: LayoutData;
  hiddenLayers: Set<string>;
  selectedViolation: Violation | null;
  selectedMarkerIndex: number | null;
}

export function LayoutViewer({ layout, hiddenLayers, selectedViolation, selectedMarkerIndex }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<WebGLRenderer | null>(null);
  const isDragging = useRef(false);
  const lastPos = useRef({ x: 0, y: 0 });

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

    const margin = Math.max(targetBbox[2] - targetBbox[0], targetBbox[3] - targetBbox[1]) * 2;
    renderer.zoomToBox([
      targetBbox[0] - margin,
      targetBbox[1] - margin,
      targetBbox[2] + margin,
      targetBbox[3] + margin,
    ]);

    if (geometries.length > 0) {
      renderer.setMarkers(geometries, selectedMarkerIndex ?? 0);
    }
    renderer.render(hiddenLayers);
  }, [selectedViolation, selectedMarkerIndex, hiddenLayers]);

  // Handle resize
  useEffect(() => {
    const handleResize = () => {
      const canvas = canvasRef.current;
      if (!canvas || !rendererRef.current) return;
      const rect = canvas.parentElement!.getBoundingClientRect();
      rendererRef.current.resize(rect.width, rect.height);
      rendererRef.current.render(hiddenLayers);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [hiddenLayers]);

  // Mouse handlers for pan
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    isDragging.current = true;
    lastPos.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isDragging.current || !rendererRef.current) return;
      const dx = e.clientX - lastPos.current.x;
      const dy = -(e.clientY - lastPos.current.y); // flip Y for WebGL
      lastPos.current = { x: e.clientX, y: e.clientY };
      rendererRef.current.pan(dx, dy);
      rendererRef.current.render(hiddenLayers);
    },
    [hiddenLayers]
  );

  const onMouseUp = useCallback(() => {
    isDragging.current = false;
  }, []);

  // Double-click to reset view
  const onDoubleClick = useCallback(() => {
    if (!rendererRef.current) return;
    rendererRef.current.fitView();
    rendererRef.current.render(hiddenLayers);
  }, [hiddenLayers]);

  // Scroll wheel for zoom
  const onWheel = useCallback(
    (e: React.WheelEvent) => {
      if (!rendererRef.current || !canvasRef.current) return;
      e.preventDefault();
      const rect = canvasRef.current.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = rect.height - (e.clientY - rect.top); // flip Y
      const factor = e.deltaY > 0 ? 0.9 : 1.1;
      rendererRef.current.zoom(factor, cx, cy);
      rendererRef.current.render(hiddenLayers);
    },
    [hiddenLayers]
  );

  return (
    <canvas
      ref={canvasRef}
      style={{ width: "100%", height: "100%", cursor: "grab" }}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
      onDoubleClick={onDoubleClick}
      onWheel={onWheel}
    />
  );
}
