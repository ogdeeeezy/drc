# HANDOFF — agentic-drc

## What This Is
Open-source DRC tool — PVS alternative for semiconductor layout verification. Checks GDSII layouts against PDK design rules, triages violations, suggests geometric fixes, auto-applies high-confidence fixes, runs LVS, and generates parameterized cells.

## Current State
- **Phases 1-5**: ALL COMPLETE (33/33 stories)
- **625 tests passing** (595 unit + 30 integration), frontend builds clean
- **GitHub**: https://github.com/ogdeeeezy/drc — all pushed to main
- **4 uncommitted files** with partial E2E fixes (see below)

## How to Run
- Backend: `make run` (uvicorn on port 8000)
- Frontend: `make frontend` (Vite dev on 5173, proxies /api)
- Tests: `make test` (unit) | `make test-all` (all)
- E2E: `pytest tests/integration/test_e2e_phase5.py -v -s` (requires KLayout)

## Immediate Next: MOSFET met1 Fix (IN PROGRESS)

### Uncommitted Changes (4 files, all working)
All changes are uncommitted — DO NOT discard them. They represent completed fixes.

| File | Change | Status |
|------|--------|--------|
| `backend/pdk/configs/sky130/sky130A.lvs` | Line 62: `.inverted` → `extent.not(nwell)` | DONE - LVS works |
| `backend/pcell/capacitor.py` | Added `via2_enc_by_met3_adj = 0.085`, used as via2 margin | DONE but still 4 violations |
| `backend/pcell/resistor.py` | Added `licon_offset`, repositioned terminal contacts outside RPM | DONE - 0 violations |
| `backend/pcell/mosfet.py` | `internal_sd` 0.280→0.370, narrower S/D met1, gate met1 min area | PARTIAL - see below |

### E2E Results After Current Changes
```
PMOS 4-finger (W=1.0 L=0.15 F=4): 0 violations ✓
Poly resistor (W=0.35 L=2.0 S=2):  0 violations ✓
NMOS minimum (W=0.30 L=0.15 F=1):  0 violations ✓
LVS NMOS:                          match=True ✓
NMOS basic (W=0.5 L=0.15 F=1):     6 violations ✗ (m1.2)
MIM capacitor (W=5.0 L=5.0):       4 violations ✗ (unknown rule)
Pipeline (W=0.42 L=0.15 F=2):      11 violations ✗ (m1.2: 8, m1.6: 3)
```

### MOSFET m1.2 Root Cause (Y-direction gap)

The remaining m1.2 violations are between S/D met1 pads and gate contact met1 pads **in the Y direction** (not X — the X-direction spacing was fixed by widening `internal_sd`).

**Exact geometry for NMOS basic (W=0.5, L=0.15, F=1, gate_contact="both"):**
```
S/D met1 Y extent:         [0.105, 0.395]   (single mcon at 0.250, ±0.060 adj enc, ±0.085 half-width)
Gate met1 (top) Y extent:  [0.490, 0.780]   (gc_cy=0.635, half_y=0.145)
Gate met1 (bot) Y extent:  [-0.280, 0.010]

Gap (SD top → gate-top bottom): 0.490 - 0.395 = 0.095 µm  ← VIOLATION (need ≥ 0.140)
Gap (gate-bot top → SD bottom): 0.105 - 0.010 = 0.095 µm  ← VIOLATION (need ≥ 0.140)
```

### Planned Solution (NOT YET IMPLEMENTED)

**Dynamic gate contact Y positioning**: After computing `contact_y_positions` (the S/D mcon Y array), compute the actual S/D met1 extent, then push gate contacts far enough away to maintain m1.2 clearance.

```python
# After line 266 (contact_y_positions computed):
sd_met1_top = snap(contact_y_positions[-1] + mcon_size/2 + met1_enc_mcon_adj)
sd_met1_bot = snap(contact_y_positions[0] - mcon_size/2 - met1_enc_mcon_adj)

# Minimum gate contact center Y (top side):
min_gc_cy_top = snap(sd_met1_top + met1_min_spacing + mcon_size/2 + met1_enc_mcon_adj)
gc_cy_top_natural = snap(diff_h + licon_enc_by_poly + licon_size/2)
gc_cy_top = snap(max(gc_cy_top_natural, min_gc_cy_top))

# Minimum gate contact center Y (bottom side):
max_gc_cy_bot = snap(sd_met1_bot - met1_min_spacing - mcon_size/2 - met1_enc_mcon_adj)
gc_cy_bot_natural = snap(-(licon_enc_by_poly + licon_size/2))
gc_cy_bot = snap(min(gc_cy_bot_natural, max_gc_cy_bot))
```

**Cascading changes needed** when gate contacts move:
1. **Poly extension** (section 2): `gc_ext` must increase — use `abs(gc_cy) + licon_size/2 + licon_enc_by_poly` instead of fixed 0.270
2. **Gate licon** (section 4): Use dynamic `gc_cy_top`/`gc_cy_bot` instead of hardcoded formula
3. **Li1 pads** (section 5): Same — reference dynamic Y positions
4. **Mcon** (section 6): Same
5. **Met1 gate pads** (section 7): Same

**Also needed**: m1.6 (min area 0.083µm²) for S/D met1 pads. Current area for W=0.42: 0.230 × 0.290 = 0.0667µm². Fix: extend S/D met1 Y extent to `snap(min_area / (2 * met1_sd_half_x))`.

### MIM Cap Investigation Needed
4 violations remain despite using `via2_enc_by_met3_adj = 0.085` as margin. Possible causes:
- The rule being violated may not be via2.5 (could be a different rule)
- Need to run E2E with `-s` and examine actual violation categories in output
- May need to read the DRC report XML to identify the exact rule

### Stream C: Auto-Fix Confidence (NOT STARTED)
- `backend/fix/strategies/spacing.py`: Promote `MinSpacingFix` to `FixConfidence.high` when conditions are safe
- `backend/fix/autofix.py`: Current filter logic at lines 70-99
- Conditions for high confidence: single-layer, move ≤ 2× grid, no neighbor collision, clear polygon IDs

## Hot Files
- `backend/pcell/mosfet.py` — **ACTIVE**: sections 2,4,5,6,7 all need dynamic gate contact Y
- `backend/pcell/capacitor.py` — needs investigation (4 remaining violations)
- `backend/fix/strategies/spacing.py` — Stream C (not started)
- `tests/integration/test_e2e_phase5.py` — E2E validation (12 tests)

## Gotchas
- SKY130 DRC deck defaults ALL rule groups to disabled — `DEFAULT_DRC_FLAGS` fixes this
- KLayout macOS needs Gatekeeper bypass: `sudo xattr -r -d com.apple.quarantine /Applications/KLayout/klayout.app`
- cpulimit alone doesn't work on Apple Silicon — needs taskpolicy -b alongside
- .lvsdb format is NOT XML — it's S-expression text (custom parser in lvs_parser.py)
- MOSFET min contactable W is ~0.26µm (licon_size + 2*licon_enc_by_diff), not 0.15µm (diff_min_width)
- m1.5 rule: 0.060µm on BOTH edges of ONE adjacent pair (not all 4 sides)
- Poly resistor licon.1: RPM layer extends beyond poly body → licons that overlap RPM get clipped by `licon.not(prec_resistor)` in DRC deck
- Plan at `~/.claude/plans/idempotent-sniffing-beaver.md` was partially wrong about root causes (B3 was RPM overlap, not FP)

## Verification Command
```bash
pytest tests/integration/test_e2e_phase5.py -v -s 2>&1 | grep -E "(violations|match=)"
```
Target: 0 violations on all PCells, LVS match=True, auto-fix produces applied fixes.

## What's Next (After E2E Fixes)
1. **Monte Carlo optimization** — klayout.db in-process for 10k+ geometric variants
2. **LLM-assisted DRC deck generator** — auto-generate rules from DRM tables
3. **CI/CD** — GitHub Actions for test + lint on PR
4. **More PDKs** — GF180, ASAP7 (last — solidify SKY130 framework first)
