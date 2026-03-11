# Archive: PROGRESS — agentic-drc

---

## Archived: 2026-03-10 | Git: 40a5b7b

### Removed Session: Session 19

## Session 19: 2026-03-05 — Full LVS E2E verified

### Done
- **LVS E2E flow verified** — Generate PCell → upload GDS → DRC (0 violations) → upload SPICE netlist → run LVS → **match** (1 device, 4 nets). Both NMOS and PMOS single-finger pass clean.
- **Substrate taps added to PCells** — ptap for NMOS, ntap for PMOS. Full contact stack (tap → licon → li1 → mcon → met1 with "B" label). Placed left of diff with 0.130 µm implant clearance.
- **LVS deck device class mapping** — Added `same_device_classes("NMOS", "SKY130_FD_PR__NFET_01V8")` and PMOS equivalent.
- **Tests updated** — Implant assertions updated for tap presence. 730 tests, 95% coverage.

### Decisions
- Substrate tap placed LEFT of diffusion (not below) to avoid gate contact conflicts
- Implant gap = 0.130 µm between nsdm/psdm edges (matches difftap.10)

### Next
- Deploy to VPS (done in Session 20)

---

## Archived: 2026-03-06 | Git: 5494e34

### Session 18: 2026-03-05 — LVS deck fix + end-to-end testing

#### Done
- **PCell generation E2E** — Tested all 5 device types via API: NMOS, PMOS, poly resistor, MIM capacitor, minimum NMOS. All DRC-clean (0 violations).
- **SQLite migration fix** — Added migration for `netlist_path` and `lvs_report_path` columns in `database.py`.
- **LVS deck root cause found** — KLayout mos4 extraction requires SD layer pre-split at gate edges.
- **sky130A.lvs rewritten** — Pre-split SD, clip gate to active area, bridge connectivity. Device extracts with correct L=0.15, W=0.42.

#### Decisions
- Gate clipped to active area for extraction (not full poly) — prevents endcap area from inflating L computation

---

## Archived: 2026-03-05 | Git: 5b6888f

### Session 16: 2026-03-04 — Error hints plan + coverage gap analysis

#### Done
- **Coverage gap analysis** — Identified all untested error paths in the 6% gap: OSError subprocess failures, timeouts, missing DRC decks, OS-specific config detection, PCell validation guards. Mapped each to user-facing impact (cryptic vs actionable).
- **Error hints plan** (`docs/tmp-error-hints-plan.md`) — Full implementation plan for centralized `error_hints.py` module (regex→hint mapping), `hint` field on Job model/DB, API wiring, and amber tooltip UI in frontend. ~270 lines across 10 files.

#### Decisions
- Centralized hint mapping (single `error_hints.py`) over adding `hint` field to each error class — keeps presentation concerns separate, easier to maintain
- Always-visible hint box (amber below red error) over hover tooltip — more accessible, no hidden info

#### Next
- Implement error hints plan (done in Session 17)

---

## Archived: 2026-03-05 | Git: 9d1322c

### Session 15: 2026-03-04 — Fix strategy test coverage 91% → 94%

#### Done
- **Fix strategy tests** — 38 new tests covering all 4 strategy files: shrink-fix path, extension directions, collision branches, degenerate polygon handling, polygon-finding fallbacks, edge-pair geometry. 703 unit tests passing.
- **Coverage pushed** — spacing.py 62→98%, area.py 67→96%, width.py 71→95%, short.py 72→95%. Overall 91% → 94%.

#### Next
- Error hints + remaining coverage (done in Session 16 planning)

---

## Archived: 2026-03-04 | Git: affd54d

### Session 14: 2026-03-04 — CI/CD enhancement + API test coverage

#### Done
- **CI/CD enhanced** (`7881088`) — Split lint job, added pytest-cov, KLayout integration job (continue-on-error), concurrency group. `pytest-cov>=5.0` added to dev deps.
- **API route test coverage** (`01d1ef0`) — 69 new tests covering error paths across all API routes (drc, export, fix, layout, lvs, upload). Coverage 86% → 91%. 665 unit tests passing.
- **Coverage analysis documented** — Added practical limits note to `docs/tmp-cicd-plan.md`: 95% achievable, true 100% impractical due to KLayout subprocess paths and OS-specific config.

#### Decisions
- Target 95% coverage floor, not 100% — remaining 9% is defensive error handling best verified by integration tests
- CI integration job uses `continue-on-error: true` — KLayout apt install may not work on all GitHub runners

---

## Archived: 2026-03-04 | Git: 88a7d06

### Session 12: 2026-03-04 — MOSFET met1 DRC-clean (m1.2 + m1.6)

#### Done
- **MOSFET m1.2 Y-direction fix** — Dynamic gate contact Y positioning: compute S/D met1 bounds first, push gate contacts far enough for ≥0.140µm clearance. Cascaded through sections 2 (poly), 4 (licon), 5 (li1), 6 (mcon), 7 (met1). **NMOS basic: 6→0 violations. Pipeline: 11→0 violations.**
- **MOSFET m1.6 min area fix** — S/D met1 pads extended vertically when area < 0.083µm² (affects narrow W devices like W=0.42). Extension computed before gate contact positioning so clearances account for it.
- **All MOSFET variants DRC-clean** — PMOS 4-finger (0), NMOS basic (0), NMOS minimum (0), Pipeline 2-finger (0). LVS match=True. 595 unit + 12 E2E all passing.

#### Decisions
- Gate contact Y computed dynamically from actual S/D met1 extent (not hardcoded from diff edge), ensuring m1.2 clearance regardless of W or contact count
- m1.6 enforcement on S/D met1 done BEFORE gate contact positioning so the extended bounds are used for clearance calculation

---

## Archived: 2026-03-03 | Git: de899d2

### Session 8: 2026-03-03 — CPU throttling, GitHub repo, PDK guide, Phase 5 plan

#### Done
- **CPU throttling** (`1ef1730`) — Triple-layer: taskpolicy -b (macOS efficiency cores) + nice -n 10 + cpulimit -l 60%. Switched subprocess.run → Popen for PID access. Tested on 142MB ESD file.
- **DRC timeout bumped** — 300s → 2700s (45 min) for throttled large file runs.
- **E2E validated** — Full flow: upload 142MB SKY130 ESD → DRC (19 min throttled, tiled mode) → 11 violations found. All stages working.
- **PDK authoring guide** — `docs/pdk-authoring.md`: schema reference, DRC deck template, validation steps, checklist.
- **GitHub repo** — Created ogdeeeezy/drc, all commits pushed.
- **Phase 5 plan** — `docs/plan-phase5.md`: auto-fix loop, PCell generator, LVS checker. 3 features, 13 stories.
- **KLayout Python API research** — `pip install klayout` provides in-process DRC via Region API. 100-1000x faster than subprocess.

#### Decisions
- cpulimit alone ineffective on Apple Silicon — needs taskpolicy -b alongside it
- DRC blocks API thread — async execution is prerequisite for Phase 5
- Monte Carlo feasible via `klayout.db` Region.*_check() methods (no subprocess per sample)

### Session 7: 2026-03-03 — KLayout integration, e2e tests, memory profiling, DRC flag fix

#### Done
- **KLayout CLI confirmed** — Already installed at macOS app bundle, `_find_klayout()` auto-detects.
- **Latent DRC bug fixed** — SKY130 deck defaults all rule groups to disabled. Added `DEFAULT_DRC_FLAGS`.
- **E2E integration tests** — 8 tests. All pass against real KLayout.
- **Memory profiling tests** — 9 tests. ~64 bytes/poly scaling.
- **Vendored SKY130 DRC deck** — now tracked.
- **303 total tests** (286 unit + 17 integration), all passing.

---

## Archived: 2026-03-02 | Git: 438df94

### Removed Section: Session 1

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

---

## Archived: 2026-03-02 | Git: afd7d76

### Removed Section: Session 2

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

## Archived: 2026-03-03 | Git: a9b21b5

### Removed Section: Session 3

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

## Archived: 2026-03-03 | Git: a9b21b5

### Removed Section: Session 4

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

## Archived: 2026-03-03 | Git: 1ef1730

### Session 6: 2026-03-03 — Adaptive DRC for resource-constrained environments

#### Done
- **Adaptive DRC strategy** — Auto-selects thread count and DRC mode (deep vs tiled) based on GDS file size. Three tiers: <20MB (4 threads, deep), 20-80MB (2 threads, deep), >80MB (1 thread, tiled 1000µm).
- **DRC deck updated** — Conditional tiling in `sky130A_mr.drc` reads `$drc_mode` param.
- **API response** — Includes `strategy` block with mode/threads/tile_size_um.
- **12 new tests** — `TestAdaptiveStrategy` (7), `TestBuildCommandWithStrategy` (4), `TestRunIncludesStrategy` (1).

#### Decisions
- Strategy computed from `gds_path.stat().st_size` — no user input needed
- DRC deck backward-compatible (defaults to deep if `$drc_mode` not set)

### Session 5: 2026-03-02 — Phase 4 complete (Production Hardening)

#### Done
- **P4-1 through P4-5** — Fix-apply re-DRC loop, SQLite persistence (WAL), report export (JSON/CSV/HTML), Docker+CI/CD, density fill strategy.
- **273 unit tests total**, all passing.

#### Decisions
- SQLite WAL mode for concurrent reads during DRC
- `apply-and-recheck` endpoint auto-sets `complete` if violations reach 0
- Density fill uses PDK spacing/width rules, 25% default target

---

## Archived: 2026-03-04 | Git: 1579dfe

### Session 9: 2026-03-03 — Phase 5 complete: async DRC, auto-fix, LVS, PCell (Ralph)

#### Done
- **3 modular PRDs created** — `prds/phase-5a-async-autofix/`, `prds/phase-5b-lvs/`, `prds/phase-5c-pcell/` (14 stories total)
- **Ralph orchestrator execution** — All 3 PRDs queued and executed autonomously. 5a first, then 5b+5c in parallel.
- **Phase 5a: Async DRC + Auto-Fix** (`8cc960f`..`be1ff76`) — 5 stories. Async subprocess, AutoFixRunner with confidence filtering, fix_provenance SQLite table, oscillation/regression detection, flagged fixes review endpoints.
- **Phase 5b: LVS Checker** (`d8c3032`..`31f3989`) — 5 stories. LVSRunner, .lvsdb S-expression parser, SKY130 LVS deck, API endpoints, React mismatch viewer.
- **Phase 5c: PCell Generator** (`3e2a620`..`af48c42`) — 4 stories. MOSFET/resistor/capacitor generators, PCell API with self-validation DRC.
- **Lint cleanup** (`7673d11`) — Fixed 20 lint errors from Ralph's output (unused imports, import ordering, ambiguous vars).
- **Merged to main** (`de899d2`) — All Phase 5 work merged, pushed to origin. 613 tests passing.

#### Decisions
- .lvsdb format is S-expression text, not XML — Ralph discovered this and built a custom parser
- PCell generators encode full SKY130 design rules (poly pitch, contact spacing, metal routing)
- Modular PRDs split: 5a (5 stories, sequential), 5b+5c (5+4 stories, parallel at order 2)

---

## Archived: 2026-03-04 | Git: ebaa65a

## Session 10: 2026-03-03 — E2E validation + issue triage

### Done
- **E2E integration test suite** — `tests/integration/test_e2e_phase5.py` (12 tests). PCell→DRC, auto-fix loop, LVS runner, full pipeline. All 12 passing, 625 total tests.
- **Exact DRC violations captured** per PCell type against real KLayout + SKY130 deck
- **Triage plan created** — 3 streams: LVS deck fix, PCell generator fixes, auto-fix confidence tuning. Plan at `~/.claude/plans/idempotent-sniffing-beaver.md`
- **Priority reorder** — More PDKs moved to last; solidify SKY130 framework first

### Decisions
- E2E tests skip gracefully if KLayout not installed (CI-friendly)
- Auto-fix test uses `confidence_threshold="medium"` — "high" flags all spacing fixes causing stall (by design)
- PCell DRC violations are real bugs, not test issues — need generator fixes

### Next
- MIM capacitor investigation + auto-fix confidence tuning

---

## Archived: 2026-03-04 | Git: 01d1ef0

## Session 11: 2026-03-03 — PCell DRC fixes (partial)

### Done
- **Stream A: LVS deck fix** — `sky130A.lvs` line 62: `.inverted` → `extent.not(nwell)`. LVS now runs and matches (match=True).
- **Stream B4: MIM cap via2.5** — Added `via2_enc_by_met3_adj = 0.085` to rules, used as via2 array margin in `capacitor.py`. (**Still 4 violations in E2E — needs investigation**)
- **Stream B3: Poly resistor licon.1** — Root cause was NOT floating-point (as plan suggested). Licons at terminal contacts overlap RPM region; DRC rule `licon.not(prec_resistor)` clips them. Fix: added `licon_offset` calculation using `rpm_enc_poly + contact_to_rpm + licon_size/2`, repositioned contact centers. **0 violations**.
- **Stream B1+B2: MOSFET met1 (partial)** — Added `met1_min_spacing = 0.140` to rules. Increased `internal_sd` from 0.280→0.370 (met1 pad + spacing). Narrowed S/D met1 pads (use `met1_enc_mcon` 0.030 in X, `met1_enc_mcon_adj` 0.060 in Y for m1.5). Added m1.6 min area enforcement on gate met1 pads. **PMOS 4-finger: 0 violations. NMOS minimum: 0 violations. NMOS basic: 6 violations (still failing). Pipeline 2-finger: 11 violations.**

### Decisions
- Poly resistor licon fix: plan was wrong about floating-point — real root cause was RPM overlap clipping licons via DRC subtraction
- MOSFET internal_sd widened to 0.370 to accommodate met1 pads + m1.2 spacing (was 0.280, only fit licons)
- m1.5 rule (0.060 on adj edges) satisfied by using met1_enc_mcon_adj in Y direction of S/D pads

### Next
- Continue with MIM cap and auto-fix confidence (see Session 12)

---

## Archived: 2026-03-04 | Git: 6436668

### Session 13: 2026-03-04 — MIM cap DRC-clean + auto-fix confidence

#### Done
- **MIM capacitor DRC-clean** (`b63629b`) — Root cause: via2.5 in SKY130 DRC deck checks `m2.enclosing(via2, 0.085)` (met2, not met3 as description says). Met2 pad margin was 0.040 (via2.4) instead of 0.085 (via2.5). Added `via2_enc_by_met2_adj` constant. **All PCells now 0 violations.**
- **Stream C: MinSpacingFix confidence promotion** (`ebaa65a`) — Move fixes promoted to `FixConfidence.high` when: (1) deficit <= rule value, (2) no same-layer polygon collision within min_spacing of moved position. Collision check uses `SpatialIndex.query_nearby()`. Shrink fixes stay at medium. 596 unit + 12 E2E passing.
- **CI/CD plan drafted** — `docs/tmp-cicd-plan.md` with full enhancement plan for `.github/workflows/ci.yml`. Was interrupted before implementation.

#### Decisions
- via2.5 DRC deck bug: description says "m3 enclosure" but code checks m2. Documented in HANDOFF gotchas.
- Shrink fixes intentionally kept at medium confidence — shrinking polygons risks width/area violations

#### Next
- CI/CD implementation (done in Session 14)

---

## Archived: 2026-03-05 | Git: 2b2edd9

## Session 17: 2026-03-04 — Error hints implementation + branch protection

### Done
- **Error hints implemented** (`affd54d`) — Centralized `error_hints.py` with 14 regex→hint rules, `hint` field on Job model + DB schema (with ALTER TABLE migration), route wiring in drc.py/lvs.py, amber hint box UI in frontend. 730 tests, 95% coverage.
- **OSError runner tests** — 4 new tests each for DRC/LVS runners covering exec format error and permission denied paths (sync + async).
- **Error hints test suite** — 19 tests covering all regex patterns, edge cases, first-match-wins behavior.
- **Branch protection enabled** — GitHub API: `lint`, `test`, `frontend` required checks on `main`, strict mode, force push blocked.
- **Tagged release** — `pre-llm-deck-gen-pre-mc` tag on `affd54d`.

### Decisions
- Branch protection enforce_admins left OFF so owner can push directly when needed
- `integration` check excluded from required checks (uses continue-on-error due to KLayout availability)

### Next
- Monte Carlo optimization — klayout.db in-process for 10k+ geometric variants
- LLM-assisted DRC deck generator — auto-generate rules from DRM tables
- More PDKs — GF180, ASAP7 (solidify SKY130 framework first)
