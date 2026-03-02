/** API client for the Agentic DRC backend. */

const BASE = "/api";

export interface JobSummary {
  job_id: string;
  filename: string;
  pdk_name: string;
  status: string;
  created_at: number;
  total_violations: number;
  error: string | null;
}

export interface UploadResult {
  job_id: string;
  filename: string;
  pdk_name: string;
  status: string;
}

export interface DRCCategory {
  category: string;
  description: string;
  count: number;
  severity: number;
  rule_type: string | null;
}

export interface DRCResult {
  job_id: string;
  status: string;
  total_violations: number;
  duration_seconds: number;
  categories: DRCCategory[];
}

export interface ViolationGeometry {
  type: string;
  bbox: number[];
  edge_pair: { edge1: number[][]; edge2: number[][] } | null;
  points: number[][] | null;
}

export interface Violation {
  category: string;
  description: string;
  cell_name: string;
  rule_id: string | null;
  rule_type: string | null;
  severity: number;
  value_um: number | null;
  count: number;
  bbox: number[];
  geometries: ViolationGeometry[];
}

export interface ViolationsResponse {
  job_id: string;
  total_violations: number;
  violations: Violation[];
}

export interface LayerData {
  gds_layer: number;
  gds_datatype: number;
  name: string;
  color: string;
  polygons: number[][][];
}

export interface LayoutData {
  job_id: string;
  cells: { name: string; polygon_count: number; bbox: number[] | null }[];
  bbox: number[];
  layers: LayerData[];
  total_polygons: number;
}

export interface FixSuggestion {
  index: number;
  violation_category: string;
  rule_type: string;
  description: string;
  confidence: string;
  priority: number;
  creates_new_violations: boolean;
  validation_notes: string;
  delta_count: number;
  affected_layers: number[][];
}

export interface SuggestResult {
  job_id: string;
  total_suggestions: number;
  fixable_count: number;
  unfixable_count: number;
  suggestions: FixSuggestion[];
}

export interface FixDelta {
  cell_name: string;
  gds_layer: number;
  gds_datatype: number;
  original_points: number[][];
  modified_points: number[][];
  is_removal: boolean;
  is_addition: boolean;
}

export interface PreviewResult {
  job_id: string;
  suggestion_index: number;
  description: string;
  confidence: string;
  deltas: FixDelta[];
}

async function fetchJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  upload(file: File, pdkName = "sky130"): Promise<UploadResult> {
    const form = new FormData();
    form.append("file", file);
    return fetchJSON(`${BASE}/upload?pdk_name=${pdkName}`, {
      method: "POST",
      body: form,
    });
  },

  listJobs(): Promise<{ jobs: JobSummary[] }> {
    return fetchJSON(`${BASE}/jobs`);
  },

  getJob(jobId: string): Promise<JobSummary> {
    return fetchJSON(`${BASE}/jobs/${jobId}`);
  },

  runDRC(jobId: string): Promise<DRCResult> {
    return fetchJSON(`${BASE}/jobs/${jobId}/drc`, { method: "POST" });
  },

  getViolations(jobId: string): Promise<ViolationsResponse> {
    return fetchJSON(`${BASE}/jobs/${jobId}/violations`);
  },

  getLayout(jobId: string): Promise<LayoutData> {
    return fetchJSON(`${BASE}/jobs/${jobId}/layout`);
  },

  suggestFixes(jobId: string): Promise<SuggestResult> {
    return fetchJSON(`${BASE}/jobs/${jobId}/fix/suggest`, { method: "POST" });
  },

  previewFix(jobId: string, index: number): Promise<PreviewResult> {
    return fetchJSON(`${BASE}/jobs/${jobId}/fix/preview/${index}`);
  },

  applyFixes(
    jobId: string,
    indices: number[]
  ): Promise<{ applied_count: number; status: string }> {
    return fetchJSON(`${BASE}/jobs/${jobId}/fix/apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ suggestion_indices: indices }),
    });
  },

  listPDKs(): Promise<{ pdks: string[] }> {
    return fetchJSON(`${BASE}/pdks`);
  },
};
