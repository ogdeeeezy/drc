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

## 2026-03-04 — Session 13: MIM Cap + Auto-Fix Confidence

### DRC deck rule descriptions lie — always read the source
SKY130's `via2.5` rule description says "min. m3 enclosure of via2 of 2 adjacent edges" but the actual code checks `m2.enclosing(via2, 0.085, projection)` — **met2**, not met3. Session 11 added met3 margins thinking that was the fix; it wasn't. The real issue was the met2 pad using 0.040µm (via2.4) instead of 0.085µm (via2.5). **When a DRC violation persists after fixing what the description says, read the `.drc` deck source to see what the rule actually checks.** Open-source PDK decks have documentation bugs just like code.

## 2026-03-04 — Session 15: Fix Strategy Test Coverage

### Geometric test coverage requires matching violation bbox aspect ratios to code branches
In `short.py`, the `w >= h` check routes to horizontal vs vertical shrink. All initial tests used tall violation bboxes (edge pairs spanning full polygon height), so they all took the vertical path — leaving horizontal completely uncovered. The fix was designing edge pairs where the overlap region is explicitly wider than tall (e.g., two wide-and-short polygons overlapping along their width). **Same pattern applies to any geometry code with aspect-ratio branching — `area.py`, `width.py`, and `spacing.py` all have similar `w >= h` / `w < h` forks.** When writing geometric tests, always check both bbox orientations.

## 2026-03-05 — Session 18: LVS Deck Root Cause

### KLayout mos4 extraction requires pre-split SD layer
KLayout's `mos4` device extractor does NOT auto-split a continuous diffusion rectangle at gate edges. It expects the SD layer to already be two separate polygons (source and drain). A continuous diff rectangle triggers "Expected two polygons on diff interacting with one gate shape — ignored." **Fix: define SD as `(diff & nsdm) - gate_poly` in the LVS deck** so the boolean subtraction pre-splits it. Tested 6 hypotheses (T-pad shape, gate height, diff height, rotation, split diff, clipped gate) before isolating this. The geometry was always correct — the extraction recipe was wrong.

### Gate endcaps inflate L computation — clip gate to active area
KLayout computes gate L = gate_polygon_area / W. If the gate poly extends beyond diffusion (endcaps for contacts), that extra area inflates L. E.g., L=0.432 instead of L=0.15 for a gate with 0.395µm endcaps. **Fix: use `gate_in_active = gate_poly & active` for the "G" extraction terminal.** Then bridge back with `connect(gate_in_active, gate_poly)` for routing connectivity.

### Test hypotheses methodically — don't assume the first theory
The initial hypothesis was that T-shaped poly (widened for gate contacts) confused KLayout. Built a test with perfectly straight gate — same error. Then tried diff taller than gate, rotated layout, etc. Each test took ~2min via KLayout batch mode. The root cause (SD not pre-split) was only found on the 5th hypothesis. **Lesson: when debugging PDK tool interactions, create minimal test cases and vary one variable at a time.**

## 2026-03-05 — Session 19: LVS E2E Verification

### LVS device class names must be mapped explicitly
KLayout's `mos4("NMOS")` extracts devices with class name `NMOS`, but SPICE netlists use PDK model names like `sky130_fd_pr__nfet_01v8`. Without `same_device_classes("NMOS", "SKY130_FD_PR__NFET_01V8")` in the LVS deck, the comparator sees two completely different device types — all nets and devices show as mismatched even when the geometry is perfectly correct. **This is easy to miss because the LVS report shows net/device mismatches that look like connectivity problems, not naming problems.** Always check device class names in the LVSDB `K()` and `D()` entries first.

### Body terminal needs a physical tap — labels alone don't create pins
A `gdstk.Label("B", ...)` on `met1_lbl` only names a net; it doesn't create a pin or physical connection. For LVS body matching, the layout needs a complete physical path: `tap(65/44) → licon → li1 → mcon → met1`, where the tap connects to the well via `connect(pwell, ptap)` in the LVS deck. Without this, the body net is extracted (from the device's W terminal connecting to pwell) but has no pin — the schematic's B pin has nothing to match against. **Lesson: in LVS, every schematic pin needs a physical shape on a pinnable layer connected through the full extraction stack, not just a text label.**

### VPS deployment recon: 4 commands, 30 seconds
When deploying to a VPS, check `~/.ssh/known_hosts` to find the IP (saves asking the user to dig through provider dashboards). Then SSH in and run 4 checks: existing reverse proxy config (`cat /etc/caddy/Caddyfile` or nginx), running containers (`docker ps`), port conflicts (`ss -tlnp :80,:443,:8000`), and DNS resolution (`dig +short domain`). This gave a complete deployment picture instantly — discovered Caddy already running with auto-SSL, which eliminated the entire nginx/certbot setup. **Lesson: always recon existing infrastructure before planning deployment; the simplest path is often already half-built.**

---

## 2026-03-04 — Session 16: Error Hints Planning

### Untested error paths are a UX problem, not just a coverage metric
The 6% uncovered code wasn't "unimportant defensive code" — it was the exact code that runs when users hit problems. If error-handling code itself has bugs or writes cryptic messages (e.g., `"Failed to execute KLayout: [Errno 8] Exec format error"`), users get stuck with no guidance at the worst possible moment. **Coverage gaps in error paths should be evaluated by "what does the user see when this runs?" not just "is this line exercised?"** The fix isn't just adding tests — it's improving the messages themselves and adding actionable hints. A centralized hint mapping (`regex → user-friendly guidance`) is more maintainable than scattering hints across error classes.

---

## 2026-03-05 — Session 20: Production Deploy + Bugfixes

### Async backend + synchronous frontend = silent UX failure
The DRC endpoint returns immediately (async background task) but the frontend called `getViolations` right after — before DRC finished. The error wasn't obvious: it manifested as a confusing 409 on the *second* click, not a clear "not ready" on the first. LVS already had polling; DRC didn't. **Lesson: any async backend task needs a polling loop on the frontend. Audit all fire-and-forget POST endpoints for matching frontend poll logic.**

### python:3.12-slim has almost nothing
No `curl`, no `wget`. Docker healthchecks need `python -c "import urllib.request; urllib.request.urlopen(...)"` instead. Easy to miss because local dev always has these tools.

### Unconstrained pan/zoom = guaranteed user confusion
Every canvas-based viewer needs viewport clamping from day one. The fix was trivial (20 lines — clamp pan so 20% overlaps bbox, bound zoom 0.1x–100x, double-click reset) but the UX impact was major — users lose the layout and think the tool is broken. **Lesson: always add viewport bounds when building interactive canvas viewers. The cost is 20 lines; the cost of not doing it is users thinking the app is broken.**

## 2026-03-06 — Session 21: Multi-Finger Bus Routing

### New metal structures must update clearance references before dependent geometry
Adding met1 bus bars between S/D pads and gate contact pads creates a new "closest metal" for m1.2 spacing. The bus top edge (`src_bus_top`) replaces `sd_met1_top` as the clearance reference for gate contact Y positioning. Computing bus positions AFTER gate contact placement would require a second pass to fix clearance — instead, compute bus Y positions immediately after S/D met1 bounds, then feed into gate contact clearance. **This extends the Session 12 insight ("compute dependent geometry in correct order"): any new structure inserted between existing layers must be computed before anything that depends on clearance to those layers.**
