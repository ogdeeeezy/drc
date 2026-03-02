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
}

export function LayoutViewer({ layout, hiddenLayers, selectedViolation }: Props) {
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

  // Zoom to selected violation
  useEffect(() => {
    if (!selectedViolation || !rendererRef.current) return;
    const bbox = selectedViolation.bbox;
    const margin = Math.max(bbox[2] - bbox[0], bbox[3] - bbox[1]) * 2;
    rendererRef.current.zoomToBox([
      bbox[0] - margin,
      bbox[1] - margin,
      bbox[2] + margin,
      bbox[3] + margin,
    ]);
    rendererRef.current.render(hiddenLayers);
  }, [selectedViolation, hiddenLayers]);

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
      onWheel={onWheel}
    />
  );
}
