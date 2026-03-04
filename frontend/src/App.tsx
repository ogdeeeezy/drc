import { useCallback, useRef, useState } from "react";
import {
  api,
  type DRCResult,
  type LayoutData,
  type LVSMismatch,
  type LVSResultsResponse,
  type SuggestResult,
  type Violation,
  type ViolationsResponse,
} from "./api/client";
import { LayoutViewer } from "./components/Layout/LayoutViewer";
import { LayerPanel } from "./components/Layout/LayerPanel";
import { ViolationList } from "./components/DRC/ViolationList";
import { ViolationOverlay } from "./components/DRC/ViolationOverlay";
import { FixPanel } from "./components/Fix/FixPanel";
import { MismatchList } from "./components/LVS/MismatchList";

type Stage = "upload" | "layout" | "drc" | "fix" | "lvs";

export function App() {
  const [stage, setStage] = useState<Stage>("upload");
  const [jobId, setJobId] = useState<string | null>(null);
  const [layout, setLayout] = useState<LayoutData | null>(null);
  const [drcResult, setDrcResult] = useState<DRCResult | null>(null);
  const [violations, setViolations] = useState<ViolationsResponse | null>(null);
  const [fixResult, setFixResult] = useState<SuggestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hiddenLayers, setHiddenLayers] = useState<Set<string>>(new Set());
  const [selectedViolation, setSelectedViolation] = useState<Violation | null>(
    null
  );
  const [lvsResults, setLvsResults] = useState<LVSResultsResponse | null>(null);
  const [selectedMismatch, setSelectedMismatch] = useState<LVSMismatch | null>(
    null
  );
  const [netlistUploaded, setNetlistUploaded] = useState(false);
  const [lvsRunning, setLvsRunning] = useState(false);

  const fileRef = useRef<HTMLInputElement>(null);
  const netlistRef = useRef<HTMLInputElement>(null);

  const handleUpload = useCallback(async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.upload(file);
      setJobId(result.job_id);
      const layoutData = await api.getLayout(result.job_id);
      setLayout(layoutData);
      setStage("layout");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const handleRunDRC = useCallback(async () => {
    if (!jobId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.runDRC(jobId);
      setDrcResult(result);
      const viols = await api.getViolations(jobId);
      setViolations(viols);
      setStage("drc");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  const handleSuggestFixes = useCallback(async () => {
    if (!jobId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.suggestFixes(jobId);
      setFixResult(result);
      setStage("fix");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  const handleUploadNetlist = useCallback(async () => {
    const file = netlistRef.current?.files?.[0];
    if (!file || !jobId) return;
    setLoading(true);
    setError(null);
    try {
      await api.uploadNetlist(jobId, file);
      setNetlistUploaded(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  const handleRunLVS = useCallback(async () => {
    if (!jobId) return;
    setLvsRunning(true);
    setError(null);
    try {
      await api.runLVS(jobId);
      // Poll for completion
      const poll = async () => {
        for (let i = 0; i < 120; i++) {
          await new Promise((r) => setTimeout(r, 2000));
          const job = await api.getJob(jobId);
          if (job.status === "lvs_complete") {
            const results = await api.getLVSResults(jobId);
            setLvsResults(results);
            setStage("lvs");
            return;
          }
          if (job.status === "lvs_failed") {
            throw new Error(job.error ?? "LVS failed");
          }
        }
        throw new Error("LVS timed out");
      };
      await poll();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLvsRunning(false);
    }
  }, [jobId]);

  const toggleLayer = useCallback((key: string) => {
    setHiddenLayers((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      {/* Header */}
      <header
        style={{
          padding: "12px 20px",
          background: "#16213e",
          borderBottom: "1px solid #0f3460",
          display: "flex",
          alignItems: "center",
          gap: 16,
        }}
      >
        <h1 style={{ fontSize: 18, fontWeight: 700, color: "#e94560" }}>
          Agentic DRC
        </h1>

        {stage === "upload" && (
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input ref={fileRef} type="file" accept=".gds,.gds2,.gdsii" />
            <button onClick={handleUpload} disabled={loading}>
              {loading ? "Uploading..." : "Upload GDSII"}
            </button>
          </div>
        )}

        {stage !== "upload" && (
          <div style={{ display: "flex", gap: 8 }}>
            <span style={{ color: "#888", fontSize: 13 }}>
              Job: {jobId}
            </span>
            {stage === "layout" && (
              <button onClick={handleRunDRC} disabled={loading}>
                {loading ? "Running DRC..." : "Run DRC"}
              </button>
            )}
            {stage === "drc" && (
              <>
                <button onClick={handleSuggestFixes} disabled={loading}>
                  {loading ? "Analyzing..." : "Suggest Fixes"}
                </button>
                <span
                  style={{
                    width: 1,
                    height: 20,
                    background: "#0f3460",
                    margin: "0 4px",
                  }}
                />
                <input
                  ref={netlistRef}
                  type="file"
                  accept=".spice,.sp,.cir,.net,.cdl"
                  style={{ maxWidth: 160, fontSize: 11 }}
                />
                <button
                  onClick={handleUploadNetlist}
                  disabled={loading || !netlistRef.current?.files?.length}
                >
                  Upload Netlist
                </button>
                {netlistUploaded && (
                  <button onClick={handleRunLVS} disabled={lvsRunning}>
                    {lvsRunning ? "Running LVS..." : "Run LVS"}
                  </button>
                )}
              </>
            )}
            {stage === "lvs" && (
              <span
                style={{
                  fontSize: 12,
                  color: lvsResults?.match ? "#4ecdc4" : "#e94560",
                  fontWeight: 600,
                }}
              >
                LVS: {lvsResults?.match ? "Clean" : "Mismatches found"}
              </span>
            )}
          </div>
        )}

        {error && (
          <span style={{ color: "#e94560", fontSize: 13, marginLeft: "auto" }}>
            {error}
          </span>
        )}
      </header>

      {/* Main content */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Left sidebar — layers */}
        {layout && (
          <div
            style={{
              width: 200,
              borderRight: "1px solid #0f3460",
              overflow: "auto",
              background: "#16213e",
            }}
          >
            <LayerPanel
              layers={layout.layers}
              hiddenLayers={hiddenLayers}
              onToggle={toggleLayer}
            />
          </div>
        )}

        {/* Center — layout viewer */}
        <div style={{ flex: 1, position: "relative" }}>
          {layout ? (
            <>
              <LayoutViewer
                layout={layout}
                hiddenLayers={hiddenLayers}
                selectedViolation={selectedViolation}
              />
              {violations && (
                <ViolationOverlay
                  violations={violations.violations}
                  layoutBbox={layout.bbox}
                  selectedViolation={selectedViolation}
                />
              )}
            </>
          ) : (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
                color: "#666",
              }}
            >
              Upload a GDSII file to begin
            </div>
          )}
        </div>

        {/* Right sidebar — violations / fixes / LVS */}
        {(violations || fixResult || lvsResults) && (
          <div
            style={{
              width: 320,
              borderLeft: "1px solid #0f3460",
              overflow: "auto",
              background: "#16213e",
            }}
          >
            {lvsResults ? (
              <MismatchList
                results={lvsResults}
                selected={selectedMismatch}
                onSelect={setSelectedMismatch}
              />
            ) : fixResult && jobId ? (
              <FixPanel jobId={jobId} result={fixResult} />
            ) : violations ? (
              <ViolationList
                violations={violations.violations}
                selected={selectedViolation}
                onSelect={setSelectedViolation}
              />
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
