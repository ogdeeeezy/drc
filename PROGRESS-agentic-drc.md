# PROGRESS-agentic-drc

> Sessions 1-8 archived → `docs/archive/archive-progress-agentic-drc.md`

---

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
- **Fix issues surfaced by E2E** (plan ready, not yet executed):
  1. LVS deck: replace `.inverted` with `extent.not(nwell)` (KLayout 0.30.6 compat)
  2. MOSFET: fix m1.2 spacing (met1 pads too close) + m1.7 area (gate contact pads too small)
  3. Poly resistor: fix licon.1 exact size (0.170×0.170)
  4. MIM cap: fix via2.5 enclosure (met3 enc of via2, need 0.085µm on adj edges)
  5. Auto-fix: promote spacing fixes to high confidence when conditions are clear
- **Monte Carlo optimization** — klayout.db in-process for 10k+ geometric variants
- **LLM-assisted DRC deck generator** — auto-generate rules from DRM tables
- **CI/CD** — GitHub Actions for test + lint on PR
- **More PDKs** — GF180, ASAP7 (last)

---

## Session 9: 2026-03-03 — Phase 5 complete: async DRC, auto-fix, LVS, PCell (Ralph)

### Done
- **3 modular PRDs created** — `prds/phase-5a-async-autofix/`, `prds/phase-5b-lvs/`, `prds/phase-5c-pcell/` (14 stories total)
- **Ralph orchestrator execution** — All 3 PRDs queued and executed autonomously. 5a first, then 5b+5c in parallel.
- **Phase 5a: Async DRC + Auto-Fix** (`8cc960f`..`be1ff76`) — 5 stories. Async subprocess, AutoFixRunner with confidence filtering, fix_provenance SQLite table, oscillation/regression detection, flagged fixes review endpoints.
- **Phase 5b: LVS Checker** (`d8c3032`..`31f3989`) — 5 stories. LVSRunner, .lvsdb S-expression parser, SKY130 LVS deck, API endpoints, React mismatch viewer.
- **Phase 5c: PCell Generator** (`3e2a620`..`af48c42`) — 4 stories. MOSFET/resistor/capacitor generators, PCell API with self-validation DRC.
- **Lint cleanup** (`7673d11`) — Fixed 20 lint errors from Ralph's output (unused imports, import ordering, ambiguous vars).
- **Merged to main** (`de899d2`) — All Phase 5 work merged, pushed to origin. 613 tests passing.

### Decisions
- .lvsdb format is S-expression text, not XML — Ralph discovered this and built a custom parser
- PCell generators encode full SKY130 design rules (poly pitch, contact spacing, metal routing)
- Modular PRDs split: 5a (5 stories, sequential), 5b+5c (5+4 stories, parallel at order 2)
