# PROGRESS-agentic-drc

> Sessions 1-9 archived → `docs/archive/archive-progress-agentic-drc.md`

---

## Session 12: 2026-03-04 — MOSFET met1 DRC-clean (m1.2 + m1.6)

### Done
- **MOSFET m1.2 Y-direction fix** — Dynamic gate contact Y positioning: compute S/D met1 bounds first, push gate contacts far enough for ≥0.140µm clearance. Cascaded through sections 2 (poly), 4 (licon), 5 (li1), 6 (mcon), 7 (met1). **NMOS basic: 6→0 violations. Pipeline: 11→0 violations.**
- **MOSFET m1.6 min area fix** — S/D met1 pads extended vertically when area < 0.083µm² (affects narrow W devices like W=0.42). Extension computed before gate contact positioning so clearances account for it.
- **All MOSFET variants DRC-clean** — PMOS 4-finger (0), NMOS basic (0), NMOS minimum (0), Pipeline 2-finger (0). LVS match=True. 595 unit + 12 E2E all passing.

### Decisions
- Gate contact Y computed dynamically from actual S/D met1 extent (not hardcoded from diff edge), ensuring m1.2 clearance regardless of W or contact count
- m1.6 enforcement on S/D met1 done BEFORE gate contact positioning so the extended bounds are used for clearance calculation
- `gc_ext` split into `gc_ext_top`/`gc_ext_bot` since dynamic positioning makes them asymmetric in principle (symmetric in practice for gate_contact="both")

### Next
- **MIM capacitor** — 4 violations remain (rule unknown). Need to run E2E with `-s` and examine violation categories, or read DRC report XML
- **Stream C: Auto-fix confidence** — Promote `MinSpacingFix` to high confidence when safe. `backend/fix/strategies/spacing.py`
- **Monte Carlo optimization** — klayout.db in-process for 10k+ geometric variants

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
- Continue with MIM cap and auto-fix confidence (see Session 12)

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
- MIM capacitor investigation + auto-fix confidence tuning
