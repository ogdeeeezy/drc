# PROGRESS-agentic-drc

> Sessions 1-11 archived → `docs/archive/archive-progress-agentic-drc.md`

---

## Session 14: 2026-03-04 — CI/CD enhancement + API test coverage

### Done
- **CI/CD enhanced** (`7881088`) — Split lint job, added pytest-cov, KLayout integration job (continue-on-error), concurrency group. `pytest-cov>=5.0` added to dev deps.
- **API route test coverage** (`01d1ef0`) — 69 new tests covering error paths across all API routes (drc, export, fix, layout, lvs, upload). Coverage 86% → 91%. 665 unit tests passing.
- **Coverage analysis documented** — Added practical limits note to `docs/tmp-cicd-plan.md`: 95% achievable, true 100% impractical due to KLayout subprocess paths and OS-specific config.

### Decisions
- Target 95% coverage floor, not 100% — remaining 9% is defensive error handling best verified by integration tests
- CI integration job uses `continue-on-error: true` — KLayout apt install may not work on all GitHub runners

### Next
- **Fix strategy tests** — Cover `spacing.py` (48 lines), `area.py` (33), `width.py` (29), `short.py` (23) for ~95% total
- **Branch protection** — Enable in GitHub repo settings: require `lint`, `test`, `frontend` to pass
- Monte Carlo optimization — klayout.db in-process for 10k+ geometric variants
- LLM-assisted DRC deck generator — auto-generate rules from DRM tables

---

## Session 13: 2026-03-04 — MIM cap DRC-clean + auto-fix confidence

### Done
- **MIM capacitor DRC-clean** (`b63629b`) — Root cause: via2.5 in SKY130 DRC deck checks `m2.enclosing(via2, 0.085)` (met2, not met3 as description says). Met2 pad margin was 0.040 (via2.4) instead of 0.085 (via2.5). Added `via2_enc_by_met2_adj` constant. **All PCells now 0 violations.**
- **Stream C: MinSpacingFix confidence promotion** (`ebaa65a`) — Move fixes promoted to `FixConfidence.high` when: (1) deficit <= rule value, (2) no same-layer polygon collision within min_spacing of moved position. Collision check uses `SpatialIndex.query_nearby()`. Shrink fixes stay at medium. 596 unit + 12 E2E passing.
- **CI/CD plan drafted** — `docs/tmp-cicd-plan.md` with full enhancement plan for `.github/workflows/ci.yml`. Was interrupted before implementation.

### Decisions
- via2.5 DRC deck bug: description says "m3 enclosure" but code checks m2. Documented in HANDOFF gotchas.
- Shrink fixes intentionally kept at medium confidence — shrinking polygons risks width/area violations

### Next
- CI/CD implementation (done in Session 14)

---

## Session 12: 2026-03-04 — MOSFET met1 DRC-clean (m1.2 + m1.6)

### Done
- **MOSFET m1.2 Y-direction fix** — Dynamic gate contact Y positioning: compute S/D met1 bounds first, push gate contacts far enough for ≥0.140µm clearance. Cascaded through sections 2 (poly), 4 (licon), 5 (li1), 6 (mcon), 7 (met1). **NMOS basic: 6→0 violations. Pipeline: 11→0 violations.**
- **MOSFET m1.6 min area fix** — S/D met1 pads extended vertically when area < 0.083µm² (affects narrow W devices like W=0.42). Extension computed before gate contact positioning so clearances account for it.
- **All MOSFET variants DRC-clean** — PMOS 4-finger (0), NMOS basic (0), NMOS minimum (0), Pipeline 2-finger (0). LVS match=True. 595 unit + 12 E2E all passing.

### Decisions
- Gate contact Y computed dynamically from actual S/D met1 extent (not hardcoded from diff edge), ensuring m1.2 clearance regardless of W or contact count
- m1.6 enforcement on S/D met1 done BEFORE gate contact positioning so the extended bounds are used for clearance calculation

### Next
- MIM capacitor + auto-fix confidence (done in Session 13)
