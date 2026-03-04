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
  iteration: number;
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

export interface ApplyResult {
  job_id: string;
  applied_count: number;
  total_requested: number;
  fixed_gds_path: string;
  iteration: number;
  status: string;
}

export interface RecheckResult {
  job_id: string;
  applied_count: number;
  iteration: number;
  status: string;
  total_violations: number;
  previous_violations: number;
  duration_seconds: number;
  is_clean: boolean;
  categories: { category: string; description: string; count: number }[];
}

export interface LVSMismatch {
  type: string;
  name: string;
  expected: string;
  actual: string;
  details: string;
}

export interface LVSResultsResponse {
  job_id: string;
  match: boolean;
  devices_matched: number;
  devices_mismatched: number;
  nets_matched: number;
  nets_mismatched: number;
  mismatches: LVSMismatch[];
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

  applyFixes(jobId: string, indices: number[]): Promise<ApplyResult> {
    return fetchJSON(`${BASE}/jobs/${jobId}/fix/apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ suggestion_indices: indices }),
    });
  },

  applyAndRecheck(jobId: string, indices: number[]): Promise<RecheckResult> {
    return fetchJSON(`${BASE}/jobs/${jobId}/fix/apply-and-recheck`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ suggestion_indices: indices }),
    });
  },

  downloadReport(jobId: string, format: "json" | "csv" | "html"): string {
    return `${BASE}/jobs/${jobId}/report/${format}`;
  },

  listPDKs(): Promise<{ pdks: string[] }> {
    return fetchJSON(`${BASE}/pdks`);
  },

  uploadNetlist(
    jobId: string,
    file: File
  ): Promise<{ job_id: string; netlist_filename: string }> {
    const form = new FormData();
    form.append("file", file);
    return fetchJSON(`${BASE}/jobs/${jobId}/lvs/upload`, {
      method: "POST",
      body: form,
    });
  },

  runLVS(jobId: string): Promise<{ job_id: string; status: string }> {
    return fetchJSON(`${BASE}/jobs/${jobId}/lvs/run`, { method: "POST" });
  },

  getLVSResults(jobId: string): Promise<LVSResultsResponse> {
    return fetchJSON(`${BASE}/jobs/${jobId}/lvs/results`);
  },
};
