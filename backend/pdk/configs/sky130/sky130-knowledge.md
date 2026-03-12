# SKY130 PDK Knowledge

Process-specific insights for SkyWater SKY130 (130nm).

## DRC Deck Flag Defaults

The community SKY130 DRC deck (`sky130A_mr.drc`) defaults ALL rule groups to `false`:
- `$feol` — Front-end-of-line checks (transistors, diffusion, poly, implants)
- `$beol` — Back-end-of-line checks (metals, vias)
- `$offgrid` — Grid alignment checks
- `$seal` — Seal ring checks (usually not needed for digital blocks)
- `$floating_met` — Floating metal antenna checks

The system overrides these to `true` (except `seal` historically) so all checks run.
With the `drc_flags` field in `pdk.json`, the PDK itself declares which flags should be enabled.

## Known DRM Errata

### via2.5 Description Lie
- **DRM says**: "Min enclosure of via2 by met2"
- **Deck actually checks**: Min enclosure of via2 by **met3**
- **Impact**: Rule mapping must use deck code as source of truth, not description
- The `pdk.json` rule entries have been corrected to reflect actual deck behavior

### Contact/Via Naming Inconsistency
- The DRM uses "contact" generically, but SKY130 has distinct contact types:
  - `licon1` — local interconnect contact (diff/poly to li1)
  - `mcon` — metal contact (li1 to met1)
  - `via` through `via4` — inter-metal vias
- Rule IDs in the deck use abbreviated prefixes: `ct.` for mcon, `licon.` for licon1

## LVS Device Class Mappings

| Extraction Class | Schematic Model | Notes |
|-----------------|-----------------|-------|
| NMOS | `sky130_fd_pr__nfet_01v8` | Standard 1.8V NFET |
| PMOS | `sky130_fd_pr__pfet_01v8` | Standard 1.8V PFET |
| NMOS (HV) | `sky130_fd_pr__nfet_g5v0d10v5` | 5V/10.5V drain NFET |
| PMOS (HV) | `sky130_fd_pr__pfet_g5v0d10v5` | 5V/10.5V drain PFET |

The `device_classes` field in `pdk.json` maps the basic classes. Extended HV variants
should be added when HV device support is implemented.

## Contact Stack Ordering

Bottom to top with GDS layer numbers:

```
diff     (65/20)  — active silicon
licon1   (66/44)  — local interconnect contact
li1      (67/20)  — local interconnect (first routing)
mcon     (67/44)  — metal contact
met1     (68/20)  — metal 1
via      (68/44)  — via 1
met2     (69/20)  — metal 2
via2     (69/44)  — via 2
met3     (70/20)  — metal 3
via3     (70/44)  — via 3
met4     (71/20)  — metal 4
via4     (71/44)  — via 4
met5     (72/20)  — metal 5 (redistribution)
```

Note: routing layers use datatype 20 (drawing), vias use datatype 44.

## Layer-Specific Gotchas

### licon1 — Exact Size Requirement
- licon1 must be **exactly** 0.170µm × 0.170µm (rule `licon.1`)
- No rectangular licons allowed — this is an `exact_size` rule, not `min_width`
- Fix strategy: if licon is wrong size, replace it (don't resize)
- Arrays of licons use 0.170µm pitch with 0.170µm spacing

### met5 — Redistribution Layer
- met5 is the thick top metal, used primarily for redistribution/power
- Minimum width: 1.600µm (10× larger than met1's 0.140µm)
- Minimum spacing: 1.600µm
- Not suitable for dense signal routing — use met1-met4
- via4 is unusually large: 0.800µm × 0.800µm

### li1 — Unusual Local Interconnect
- li1 is a local interconnect layer below met1, NOT a true metal
- It has resistive properties more like poly than metal
- Minimum width and spacing both 0.170µm (same as licon)
- Minimum area: 0.0561µm² — small shapes get flagged
- Use li1 for short, local connections only; prefer met1 for anything longer

### poly — Gate and Routing
- poly serves dual purpose: transistor gates AND local routing
- poly.7: diff must extend 0.250µm beyond poly (source/drain overhang)
- poly.8: poly must extend 0.130µm beyond diff (endcap)
- Endcap violations are common in auto-placed layouts

## Multi-Finger Transistor Spacing

For multi-finger transistors, inter-finger spacing must account for:
- Source/drain diffusion sharing between adjacent fingers
- Minimum poly-to-poly spacing (0.210µm, rule `poly.2`)
- Source/drain extension beyond poly (0.250µm each side, rule `poly.7`)
- Total finger pitch = poly_width + 2×extension + poly_spacing = 0.150 + 0.500 + 0.210 = 0.860µm minimum
- On grid (0.005µm): round up to 0.860µm (already on grid)

## Grid and Snapping

- Manufacturing grid: 0.005µm (5nm)
- All polygon vertices must land on this grid
- Off-grid violations are common when importing from other tools with different grid settings
- The off-grid check covers ALL layers simultaneously
