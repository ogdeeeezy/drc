# PROGRESS-agentic-drc

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

---

## Session 1: 2026-03-02 — Architecture & plan

### Done
- **Requirements gathering** — Clarified scope: PVS-like DRC tool, DRC-only, SKY130, GDSII input, suggest-only MVP, commercial target
- **Landscape research** — Deep dive on KLayout (DRC engine, Python API, .lyrdb format), Magic VLSI, OpenROAD, gdstk, SKY130 PDK rule decks, Cadence PVS workflow
- **Architecture design** — PDK-agnostic engine with SKY130 as first config. Hybrid approach: KLayout batch DRC + gdstk for GDSII I/O + Python fix engine
- **Fix strategy research** — Documented deterministic fix algorithms for all 6 violation types (width, spacing, enclosure, area, off-grid, short) with priority ordering and pre-validation
- **Full implementation plan** — 4-phase, 19-story build plan with directory structure, PDK config schema, class hierarchy, API endpoints, testing strategy, and e2e workflows

### Decisions
- No LLM in MVP — deterministic rules-based expert system. LLM layer is future work (reads PDK docs, generates rule decks)
- KLayout as DRC engine (subprocess batch mode) — not building custom DRC from scratch
- gdstk for GDSII manipulation, klayout.db for Region operations, klayout.rdb for violation parsing
- ~80% of system is PDK-agnostic — new PDKs are JSON config, not code changes
- Web UI with WebGL viewer (earcut triangulation) + KLayout plugin later

### Next
- Set up Python project (`pyproject.toml`, venv, deps: gdstk, klayout, fastapi, pydantic)
- Implement Phase 1 Story 1: PDK config schema + SKY130 pdk.json
- Implement Phase 1 Story 2: GDSII layout manager
- Implement Phase 1 Story 3: KLayout DRC runner
- Implement Phase 1 Story 4: Violation parser
