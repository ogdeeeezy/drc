/**
 * WebGL renderer for GDSII layout polygons.
 * Uses earcut for polygon triangulation.
 */
import earcut from "earcut";
import type { LayerData, ViolationGeometry } from "../../api/client";

interface Camera {
  x: number;
  y: number;
  zoom: number;
}

interface LayerBuffer {
  vertexBuffer: WebGLBuffer;
  vertexCount: number;
  color: [number, number, number, number];
  key: string;
}

interface MarkerBuffer {
  vertexBuffer: WebGLBuffer;
  vertexCount: number;
  color: [number, number, number, number];
}

const VERTEX_SHADER = `
  attribute vec2 a_position;
  uniform vec2 u_resolution;
  uniform vec2 u_pan;
  uniform float u_zoom;

  void main() {
    vec2 pos = (a_position - u_pan) * u_zoom;
    vec2 clipSpace = (pos / u_resolution) * 2.0 - 1.0;
    gl_Position = vec4(clipSpace.x, clipSpace.y, 0, 1);
  }
`;

const FRAGMENT_SHADER = `
  precision mediump float;
  uniform vec4 u_color;

  void main() {
    gl_FragColor = u_color;
  }
`;

function hexToRGBA(hex: string, alpha = 0.6): [number, number, number, number] {
  const h = hex.replace("#", "");
  const r = parseInt(h.substring(0, 2), 16) / 255;
  const g = parseInt(h.substring(2, 4), 16) / 255;
  const b = parseInt(h.substring(4, 6), 16) / 255;
  return [r, g, b, alpha];
}

function createShader(
  gl: WebGLRenderingContext,
  type: number,
  source: string
): WebGLShader {
  const shader = gl.createShader(type)!;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const info = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`Shader compile error: ${info}`);
  }
  return shader;
}

function createProgram(
  gl: WebGLRenderingContext,
  vs: WebGLShader,
  fs: WebGLShader
): WebGLProgram {
  const program = gl.createProgram()!;
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const info = gl.getProgramInfoLog(program);
    gl.deleteProgram(program);
    throw new Error(`Program link error: ${info}`);
  }
  return program;
}

export class WebGLRenderer {
  private gl: WebGLRenderingContext;
  private program: WebGLProgram;
  private layerBuffers: LayerBuffer[] = [];
  private markerBuffers: MarkerBuffer[] = [];
  private camera: Camera = { x: 0, y: 0, zoom: 1 };
  private bbox: number[] = [0, 0, 1, 1];
  private width: number;
  private height: number;

  // Shader locations
  private aPosition: number;
  private uResolution: WebGLUniformLocation;
  private uPan: WebGLUniformLocation;
  private uZoom: WebGLUniformLocation;
  private uColor: WebGLUniformLocation;

  constructor(private canvas: HTMLCanvasElement) {
    const gl = canvas.getContext("webgl", { antialias: true, alpha: false })!;
    this.gl = gl;
    this.width = canvas.width;
    this.height = canvas.height;

    // Build shader program
    const vs = createShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER);
    const fs = createShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER);
    this.program = createProgram(gl, vs, fs);

    this.aPosition = gl.getAttribLocation(this.program, "a_position");
    this.uResolution = gl.getUniformLocation(this.program, "u_resolution")!;
    this.uPan = gl.getUniformLocation(this.program, "u_pan")!;
    this.uZoom = gl.getUniformLocation(this.program, "u_zoom")!;
    this.uColor = gl.getUniformLocation(this.program, "u_color")!;

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  }

  setLayers(layers: LayerData[], bbox: number[]) {
    this.bbox = bbox;
    this.layerBuffers = [];

    const gl = this.gl;

    for (const layer of layers) {
      const key = `${layer.gds_layer}:${layer.gds_datatype}`;
      const triangles: number[] = [];

      for (const polygon of layer.polygons) {
        const flat: number[] = [];
        for (const pt of polygon) {
          flat.push(pt[0], pt[1]);
        }
        const indices = earcut(flat);
        for (const idx of indices) {
          triangles.push(flat[idx * 2], flat[idx * 2 + 1]);
        }
      }

      if (triangles.length === 0) continue;

      const buffer = gl.createBuffer()!;
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(
        gl.ARRAY_BUFFER,
        new Float32Array(triangles),
        gl.STATIC_DRAW
      );

      this.layerBuffers.push({
        vertexBuffer: buffer,
        vertexCount: triangles.length / 2,
        color: hexToRGBA(layer.color),
        key,
      });
    }

    this.fitView();
  }

  fitView() {
    const [xmin, ymin, xmax, ymax] = this.bbox;
    const w = xmax - xmin || 1;
    const h = ymax - ymin || 1;
    const scaleX = this.width / w;
    const scaleY = this.height / h;
    this.camera.zoom = Math.min(scaleX, scaleY) * 0.9;
    this.camera.x = xmin - (this.width / this.camera.zoom - w) / 2;
    this.camera.y = ymin - (this.height / this.camera.zoom - h) / 2;
  }

  resize(width: number, height: number) {
    this.width = width;
    this.height = height;
    this.canvas.width = width;
    this.canvas.height = height;
    this.gl.viewport(0, 0, width, height);
    this.fitView();
  }

  pan(dx: number, dy: number) {
    this.camera.x -= dx / this.camera.zoom;
    this.camera.y -= dy / this.camera.zoom;
    this.clampCamera();
  }

  zoom(factor: number, cx: number, cy: number) {
    const worldX = this.camera.x + cx / this.camera.zoom;
    const worldY = this.camera.y + cy / this.camera.zoom;
    this.camera.zoom *= factor;
    this.clampZoom();
    this.camera.x = worldX - cx / this.camera.zoom;
    this.camera.y = worldY - cy / this.camera.zoom;
    this.clampCamera();
  }

  private clampZoom() {
    const [xmin, ymin, xmax, ymax] = this.bbox;
    const w = xmax - xmin || 1;
    const h = ymax - ymin || 1;
    const fitZoom = Math.min(this.width / w, this.height / h);
    this.camera.zoom = Math.max(fitZoom * 0.1, Math.min(fitZoom * 100, this.camera.zoom));
  }

  private clampCamera() {
    const [xmin, ymin, xmax, ymax] = this.bbox;
    const viewW = this.width / this.camera.zoom;
    const viewH = this.height / this.camera.zoom;
    // Keep at least 20% of viewport overlapping with the layout bbox
    const margin = 0.2;
    this.camera.x = Math.max(xmin - viewW * (1 - margin), Math.min(xmax - viewW * margin, this.camera.x));
    this.camera.y = Math.max(ymin - viewH * (1 - margin), Math.min(ymax - viewH * margin, this.camera.y));
  }

  zoomToBox(bbox: number[]) {
    const [xmin, ymin, xmax, ymax] = bbox;
    const w = xmax - xmin || 0.1;
    const h = ymax - ymin || 0.1;
    const scaleX = this.width / w;
    const scaleY = this.height / h;
    this.camera.zoom = Math.min(scaleX, scaleY) * 0.7;
    this.camera.x = xmin - (this.width / this.camera.zoom - w) / 2;
    this.camera.y = ymin - (this.height / this.camera.zoom - h) / 2;
  }

  setMarkers(geometries: ViolationGeometry[], selectedIdx: number | null) {
    this.clearMarkers();
    const gl = this.gl;

    for (let i = 0; i < geometries.length; i++) {
      const [xmin, ymin, xmax, ymax] = geometries[i].bbox;
      // Two triangles forming a filled rectangle
      const vertices = new Float32Array([
        xmin, ymin, xmax, ymin, xmax, ymax,
        xmin, ymin, xmax, ymax, xmin, ymax,
      ]);

      const buffer = gl.createBuffer()!;
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);

      const color: [number, number, number, number] =
        i === selectedIdx
          ? [233 / 255, 69 / 255, 96 / 255, 0.6]
          : [233 / 255, 69 / 255, 96 / 255, 0.25];

      this.markerBuffers.push({ vertexBuffer: buffer, vertexCount: 6, color });
    }
  }

  clearMarkers() {
    const gl = this.gl;
    for (const mb of this.markerBuffers) {
      gl.deleteBuffer(mb.vertexBuffer);
    }
    this.markerBuffers = [];
  }

  render(hiddenLayers: Set<string>) {
    const gl = this.gl;
    gl.viewport(0, 0, this.width, this.height);
    gl.clearColor(0.05, 0.05, 0.12, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);

    gl.useProgram(this.program);
    gl.uniform2f(this.uResolution, this.width / 2, this.height / 2);
    gl.uniform2f(this.uPan, this.camera.x, this.camera.y);
    gl.uniform1f(this.uZoom, this.camera.zoom);

    for (const lb of this.layerBuffers) {
      if (hiddenLayers.has(lb.key)) continue;

      gl.bindBuffer(gl.ARRAY_BUFFER, lb.vertexBuffer);
      gl.enableVertexAttribArray(this.aPosition);
      gl.vertexAttribPointer(this.aPosition, 2, gl.FLOAT, false, 0, 0);
      gl.uniform4fv(this.uColor, lb.color);
      gl.drawArrays(gl.TRIANGLES, 0, lb.vertexCount);
    }

    // Draw marker rectangles on top
    for (const mb of this.markerBuffers) {
      gl.bindBuffer(gl.ARRAY_BUFFER, mb.vertexBuffer);
      gl.enableVertexAttribArray(this.aPosition);
      gl.vertexAttribPointer(this.aPosition, 2, gl.FLOAT, false, 0, 0);
      gl.uniform4fv(this.uColor, mb.color);
      gl.drawArrays(gl.TRIANGLES, 0, mb.vertexCount);
    }
  }

  getCamera(): Camera {
    return { ...this.camera };
  }

  destroy() {
    this.clearMarkers();
    const gl = this.gl;
    for (const lb of this.layerBuffers) {
      gl.deleteBuffer(lb.vertexBuffer);
    }
    gl.deleteProgram(this.program);
  }
}
