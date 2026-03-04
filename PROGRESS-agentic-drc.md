# PROGRESS-agentic-drc

> Sessions 1-8 archived → `docs/archive/archive-progress-agentic-drc.md`

---

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
- **MOSFET m1.2 Y-direction gap** — S/D met1 top edge too close to gate contact met1 bottom edge (0.095µm gap, need ≥0.140µm). Needs dynamic gate contact Y positioning. See detailed analysis in HANDOFF.
- **MOSFET m1.6 area** — S/D met1 pad area 0.0667µm² < 0.083µm² for narrow W. Need Y extension.
- **MIM cap investigation** — 4 violations remain despite via2.5 margin fix. May be a different rule or the margin isn't being applied correctly.
- **Stream C: Auto-fix confidence** — Not started. `backend/fix/strategies/spacing.py`

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
- Continue MOSFET met1 fix (see Session 11)

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
