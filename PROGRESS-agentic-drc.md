# PROGRESS-agentic-drc

> Session 1 archived → `docs/archive/archive-progress-agentic-drc.md`

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

---

## Session 2: 2026-03-02 — Phase 1 implementation (P1-1, P1-2)

### Done
- **Project scaffold** — pyproject.toml, venv (Python 3.12), all deps installed (gdstk, klayout, fastapi, pydantic, rtree), Makefile, directory structure, .gitignore
- **P1-1: PDK config schema + SKY130 config** — Pydantic models (GDSLayer, DesignRule, ConnectivityRule, FixStrategyWeight, PDKConfig), PDKRegistry with caching, SKY130 pdk.json with 22 layers + 51 rules from official SkyWater docs. 30 tests.
- **P1-2: GDSII layout manager** — LayoutManager (gdstk load/save/flatten/add/remove/replace), geometry_utils (grid snap, bbox, area, distance). 45 tests.
- **75 unit tests total**, all passing

### Decisions
- KLayout CLI not installed yet — Python klayout bindings work fine for parsing, CLI needed in P1-3 for batch DRC
- SKY130 rules sourced from official SkyWater PDK readthedocs + periphery.csv, 5nm manufacturing grid confirmed

### Next
- P1-3: KLayout DRC runner (install `klayout` CLI, implement subprocess batch execution, temp file management)
- P1-4: Violation parser (.lyrdb XML → Violation objects, map to PDK rules)
- Vendor SKY130 DRC deck (`sky130A_mr.drc`) from efabless/mpw_precheck
- Then Phase 2: Fix suggestion engine

