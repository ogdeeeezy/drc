# PROGRESS-agentic-drc

> Sessions 1-2 archived → `docs/archive/archive-progress-agentic-drc.md`

---

## Session 5: 2026-03-02 — Phase 4 complete (Production Hardening)

### Done
- **P4-1: Fix apply + re-DRC loop** — `export/gdsii.py` (versioned GDS export), `api/routes/fix.py` (apply-and-recheck endpoint combining fix+DRC in one call), iteration tracking on jobs, fix cache clearing on re-run. Status flow: `fixes_applied` → `running_drc` → `drc_complete`/`complete`.
- **P4-2: SQLite job persistence** — `jobs/database.py` (thread-safe SQLite with WAL mode, thread-local connections), rewrote `jobs/manager.py` to use SQLite instead of JSON files. Schema includes `iteration` column. 8 database tests + 11 manager tests.
- **P4-3: Report export (JSON, CSV, HTML)** — `export/report.py` (3 formats with proper escaping, severity colors), `api/routes/export.py` (`GET /jobs/{id}/report/{format}`). 9 export tests.
- **P4-4: Docker + CI/CD** — Multi-stage `Dockerfile` (Python+KLayout+frontend), `docker-compose.yml` with health check, `.github/workflows/ci.yml` (lint+test+frontend build).
- **P4-5: Density fill strategy** — `fix/strategies/density.py` (grid-aligned fill polygons, spacing-aware placement, stops at target density), added `min_density` to `RuleType` enum, registered in engine with priority 7. 8 strategy tests.
- **Lint cleanup** — Fixed all pre-existing ruff errors (unused vars, long lines, import sorting) across entire codebase.
- **273 unit tests total**, all passing. Frontend builds clean.

### Decisions
- SQLite WAL mode for concurrent reads during DRC execution
- Job DB file lives at `data/jobs/jobs.db` alongside job directories
- `fixes_applied` new status allows re-DRC without going through upload again
- `apply-and-recheck` endpoint auto-sets `complete` if violations reach 0
- Density fill uses PDK spacing/width rules for fill sizing, 25% default target
- Versioned export: `_fixed.gds`, `_fixed_v2.gds`, etc.

### Next
- Install KLayout CLI for integration tests
- Vendor SKY130 DRC deck
- Write PDK authoring guide (`docs/pdk-authoring.md`)
- End-to-end integration test with real DRC run

---

## Session 4: 2026-03-02 — Phase 3 complete (Web API + Layout Viewer)

### Done
- **P3-1: FastAPI scaffold + upload/job** — `jobs/manager.py` (JSON-persisted job lifecycle), `api/routes/upload.py` (multipart GDSII upload), `api/deps.py` (singleton managers), CORS middleware. 18 tests.
- **P3-2: DRC + violation API** — `api/routes/drc.py` (sync DRC trigger, violation retrieval with PDK mapping). Mocked KLayout integration test.
- **P3-3: Fix suggestion + preview API** — `api/routes/fix.py` (suggest/preview/apply endpoints, in-memory fix cache, polygon delta application).
- **P3-4: Layout geometry API + WebGL viewer** — `api/routes/layout.py` (polygons by layer with PDK colors), `api/routes/pdk.py` (PDK listing/details). React+Vite+TypeScript frontend with `WebGLRenderer.ts` (earcut triangulation, pan/zoom/fit), `LayoutViewer.tsx`, `LayerPanel.tsx`.
- **P3-5: Violation overlay + fix panel UI** — `ViolationList.tsx` (sortable by severity/count/rule), `ViolationOverlay.tsx` (violation badge), `FixPanel.tsx` (checkbox selection, apply, preview modal), `FixPreview.tsx` (SVG before/after diff).
- **243 unit tests total**, all passing. Frontend builds clean (TypeScript + Vite).

### Decisions
- Job persistence via JSON files in `data/jobs/<id>/` (not SQLite yet — Phase 4)
- API deps use late-import config for test isolation
- WebGL renderer uses simple vertex/fragment shaders with camera transform, earcut for triangulation
- Fix preview uses SVG (not WebGL) for before/after polygon diff — simpler

### Next
- Phase 4: Production Hardening (fix-apply re-DRC loop, SQLite, report export, Docker, density fill)
- Install KLayout CLI for integration tests
- Vendor SKY130 DRC deck

---

## Session 3: 2026-03-02 — Phase 1 complete + Phase 2 complete

### Done
- **P1-3: KLayout DRC runner** — `backend/core/drc_runner.py`: subprocess wrapper, temp file management, timeout handling, DRCResult/DRCError. 20 tests (mocked subprocess).
- **P1-4: Violation parser + models** — `violation_models.py` + `violation_parser.py`: .lyrdb XML parser, edge-pair/polygon/edge/box support, PDK rule mapping. 48 tests + 3 .lyrdb fixtures.
- **P2-1: Spatial index + clustering** — `core/spatial_index.py` (R-tree), `fix/clustering.py` (union-find single-linkage). 24 tests.
- **P2-2: Width + spacing fixes** — `fix/strategies/base.py` (abstract FixStrategy), `fix/fix_models.py` (FixSuggestion, PolygonDelta), `width.py` (expand toward free space), `spacing.py` (move or shrink). 10 tests.
- **P2-3: Enclosure + area fixes** — `enclosure.py` (extend metal, never move via), `area.py` (extend in least-constrained direction). 4 tests.
- **P2-4: Short + offgrid fixes** — `short.py` (shrink smaller polygon + spacing buffer), `offgrid.py` (conservative snap to grid). 8 tests.
- **P2-5: Validator + engine** — `fix/validator.py` (grid/degenerate/width/spacing pre-checks), `fix/engine.py` (orchestrator with priority sorting). 21 tests.
- **214 unit tests total**, all passing in 0.22s

### Decisions
- Custom XML parser for .lyrdb instead of klayout.rdb Python bindings — simpler, no klayout import needed
- Violations grouped by category+cell — single Violation object with multiple geometries per rule/cell pair
- Fix strategies operate on individual ViolationGeometry markers, engine iterates all geometries
- Validator uses bbox-level spacing approximation (not exact polygon distance) — fast but conservative

### Next
- Phase 3: Web API + Layout Viewer (5 stories: FastAPI scaffold, DRC endpoints, fix endpoints, WebGL viewer, violation overlay)
- Install KLayout CLI for integration tests
- Vendor SKY130 DRC deck
