# INSIGHTS — agentic-drc

## 2026-03-03 — Session 10: E2E Validation

### E2E-first validation catches real bugs fast
Running PCell generators against the *actual* KLayout DRC deck immediately surfaced 5 specific rule violations that unit tests (with mocked DRC) never caught. Writing E2E tests before fixing is more efficient than guessing what's wrong.

### KLayout version fragility
The SKY130 LVS deck uses `.inverted` which doesn't exist in KLayout 0.30.6 but does in newer versions. Vendored PDK decks need version pinning or compatibility checks. Always test vendored scripts against the actual installed KLayout version.

### Confidence threshold design tension
The auto-fix stall isn't a bug — it's the safety system working correctly. Medium-confidence spacing fixes *should* be flagged with a high threshold. The real fix is teaching the engine to identify conditions where spacing fixes deserve high confidence (single-layer, small move, clear polygon identification).

### Floating-point boundary gotcha in design rules
`0.25 - 2*0.04` doesn't equal `0.17` in IEEE 754. PCell generators working at nanometer precision need `snap_to_grid()` applied to *every* intermediate calculation, not just final coordinates. The MOSFET minimum contactable width boundary (`licon_size + 2*licon_enc_by_diff`) fails at the exact threshold due to this.

## 2026-03-03 — Session 11: PCell DRC Fixes

### DRC subtraction rules invalidate naive contact placement
The SKY130 DRC deck uses `licon.not(prec_resistor)` which **subtracts** licons that overlap the RPM region before checking licon.1 (exact 0.170×0.170). This means a correctly-sized licon that partially overlaps RPM becomes a clipped, non-square shape → licon.1 violation. Fix: compute contact center offset using `rpm_enc_poly + contact_to_rpm + licon_size/2` to guarantee licons are fully outside RPM. **Lesson: always read the actual DRC deck source to understand geometric operations, not just the rule name.**

### Plans can have wrong root causes — verify before implementing
The Session 10 triage plan attributed poly resistor licon.1 to "floating-point in snap calculation." The real cause was RPM overlap clipping (a geometric/layout issue, not numeric). Blindly following the plan would have wasted time debugging snap arithmetic. **Always verify the hypothesized root cause** by reading the DRC deck and computing actual coordinates before coding the fix.

### MOSFET met1 spacing is multi-dimensional
Fixing m1.2 in the X direction (widening `internal_sd` for S/D pad spacing) exposed m1.2 violations in the Y direction (S/D pads vs gate contact pads). Metal spacing must be checked against ALL neighboring shapes, not just same-type neighbors. The fix requires **dynamic gate contact positioning** — computing gate contact Y from actual S/D met1 extent rather than fixed poly endcap geometry.

### m1.5 (adjacent enclosure) creates asymmetric pad constraints
m1.5 requires 0.060µm enclosure on BOTH edges of ONE pair of adjacent sides. For S/D met1 pads, using 0.060 in Y (adj pair) and 0.030 in X (regular enc) satisfies m1.5 while keeping pads narrow enough for m1.2 spacing. But this means the pad is taller than wide, which affects area calculations (m1.6) differently than expected.

## 2026-03-04 — Session 12: MOSFET DRC-Clean

### DRC overlap-merge masks spacing violations
When two met1 pads overlap by even 1nm, the DRC engine sees a single merged polygon — no spacing violation. When they're 5nm apart (below the 140nm min), it's a violation. This means PCells can accidentally pass DRC when geometry is "wrong in the right direction" (overlap = merge = pass). The PMOS 4-finger and NMOS minimum previously passed with 0 violations because their gate contact met1 slightly overlapped S/D met1 (merging into one shape). Proper fix: compute explicit clearance, don't rely on accidental overlap.

### Compute dependent geometry in correct order
m1.6 (min area) enforcement extends S/D met1 pads vertically, making them taller. m1.2 (spacing) clearance between S/D and gate met1 depends on S/D met1 bounds. If you compute gate contact Y *before* m1.6 extension, the clearance is wrong. **Order: (1) compute met1 bounds → (2) enforce min area → (3) compute gate contact positions from extended bounds.** This is a general pattern: constraint enforcement must happen before dependent geometry is derived.

### Split symmetric variables when they can diverge
`gc_ext` was a single value for poly extension above and below diffusion. With dynamic gate contact positioning, top and bottom extensions can differ (e.g., different natural vs forced positions). Splitting to `gc_ext_top`/`gc_ext_bot` prevents bugs even though they're numerically equal for `gate_contact="both"`. **When a variable represents two independent geometric quantities that happen to be equal, split it proactively.**
