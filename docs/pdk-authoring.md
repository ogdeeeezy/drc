# PDK Authoring Guide

How to add a new PDK to Agentic DRC.

## What You Need

Adding a PDK requires exactly **two files** in `backend/pdk/configs/<pdk_name>/`:

```
backend/pdk/configs/
├── sky130/              ← existing reference
│   ├── pdk.json
│   └── sky130A_mr.drc
└── <your_pdk>/          ← what you'll create
    ├── pdk.json
    └── <your_deck>.drc
```

Everything else (runner, parser, fix engine, API, frontend) works automatically.

## Step 1: Create `pdk.json`

This is the machine-readable PDK config. It has 7 sections:

### Header

```json
{
  "name": "gf180",
  "version": "0.1.0",
  "process_node_nm": 180,
  "grid_um": 0.005,
  "klayout_drc_deck": "gf180_mr.drc"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | PDK identifier (used in API: `?pdk_name=gf180`) |
| `version` | string | Your config version (semver) |
| `process_node_nm` | int | Process node in nanometers |
| `grid_um` | float | Manufacturing grid in microns |
| `klayout_drc_deck` | string | Filename of the `.drc` script (same directory) |

### Layers

Every GDS layer the DRC deck checks or the viewer should render:

```json
"layers": {
  "nwell": {
    "gds_layer": 21,
    "gds_datatype": 0,
    "description": "N-well region",
    "color": "#808000",
    "is_routing": false,
    "is_via": false
  },
  "met1": {
    "gds_layer": 34,
    "gds_datatype": 0,
    "description": "Metal 1",
    "color": "#0000FF",
    "is_routing": true,
    "is_via": false
  },
  "via1": {
    "gds_layer": 35,
    "gds_datatype": 0,
    "description": "Via1 (met1 to met2)",
    "color": "#808080",
    "is_routing": false,
    "is_via": true
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `gds_layer` | int | yes | GDS layer number (from PDK layer map) |
| `gds_datatype` | int | yes | GDS datatype (usually 0 or 20/44 for drawing/via) |
| `description` | string | yes | Human-readable layer purpose |
| `color` | string | yes | Hex color for the viewer (`#RRGGBB`) |
| `is_routing` | bool | no | `true` for routing layers (li, met1-met5) |
| `is_via` | bool | no | `true` for via/contact layers |

**Where to find layer numbers**: The foundry DRM or PDK layer map. For open PDKs:
- SKY130: https://skywater-pdk.readthedocs.io/en/latest/rules/layers.html
- GF180: https://gf180mcu-pdk.readthedocs.io/en/latest/physical_verification/design_manual/drm_10_layers.html

### Rules

Design rules the fix engine uses for severity mapping and fix suggestions:

```json
"rules": [
  {
    "rule_id": "m1.1",
    "rule_type": "min_width",
    "layer": "met1",
    "value_um": 0.23,
    "description": "Min width of met1",
    "severity": 7
  },
  {
    "rule_id": "m1.2",
    "rule_type": "min_spacing",
    "layer": "met1",
    "value_um": 0.23,
    "description": "Min spacing met1-to-met1",
    "severity": 7
  },
  {
    "rule_id": "m1.4",
    "rule_type": "min_enclosure",
    "layer": "met1",
    "related_layer": "via1",
    "value_um": 0.06,
    "description": "Min enclosure of via1 by met1",
    "severity": 7
  }
]
```

**Supported rule types**: `min_width`, `min_spacing`, `min_area`, `min_enclosure`, `min_extension`, `exact_size`, `off_grid`, `min_density`

**Severity scale** (1-10):
- 8-10: Critical (shorts, opens) — fix engine prioritizes these
- 6-7: Standard (width, spacing, enclosure)
- 4-5: Advisory (area, density)
- 1-3: Informational

**`related_layer`**: Required for `min_enclosure` and `min_extension` rules. Specifies the inner layer (e.g., via inside metal).

You don't need to list every rule from the DRM — just the ones you want the fix engine to understand. The `.drc` deck handles the actual checking; rules here provide metadata for triage and fix suggestions.

### Connectivity

Defines the vertical layer stack (which vias connect which metals):

```json
"connectivity": [
  { "via_layer": "contact", "lower_layer": "poly", "upper_layer": "met1" },
  { "via_layer": "via1", "lower_layer": "met1", "upper_layer": "met2" },
  { "via_layer": "via2", "lower_layer": "met2", "upper_layer": "met3" }
]
```

Used by the fix engine to understand layer relationships (e.g., enclosure rules).

### Fix Weights

Controls fix engine behavior per rule type:

```json
"fix_weights": {
  "short": { "enabled": true, "priority": 1, "prefer_move": true, "max_iterations": 3 },
  "off_grid": { "enabled": true, "priority": 2, "prefer_move": false, "max_iterations": 1 },
  "min_width": { "enabled": true, "priority": 3, "prefer_move": false, "max_iterations": 3 },
  "min_spacing": { "enabled": true, "priority": 4, "prefer_move": true, "max_iterations": 3 },
  "min_enclosure": { "enabled": true, "priority": 5, "prefer_move": false, "max_iterations": 3 },
  "min_area": { "enabled": true, "priority": 6, "prefer_move": false, "max_iterations": 3 }
}
```

| Field | Description |
|-------|-------------|
| `priority` | Fix order (1 = first). Shorts before spacing before area. |
| `prefer_move` | `true` = move polygons apart. `false` = grow/shrink in place. |
| `max_iterations` | How many fix-recheck cycles for this rule type. |

These defaults work for most PDKs. Copy from SKY130 and adjust if needed.

## Step 2: Create the DRC Deck (`.drc`)

This is a Ruby script that KLayout executes in batch mode. It defines the actual checks.

### Minimal Template

```ruby
# DRC deck for <YOUR_PDK>
# Source: <link to DRM>

# CLI args from agentic-drc runner
source($input, $top_cell) if $input

if $report
  report("<YOUR_PDK> DRC", $report)
else
  report("<YOUR_PDK> DRC", File.join(File.dirname(RBA::CellView.active.filename), "drc_report.lyrdb"))
end

# Adaptive tiling (set by agentic-drc based on file size)
if defined?($drc_mode) && $drc_mode == "tiled"
  tile_sz = defined?($tile_size) ? $tile_size.to_f : 1000.0
  tiles(tile_sz.um)
  tile_borders(10.um)
else
  deep
end

$thr ? threads($thr) : threads(4)

#-----------------------------------------------
# Layer Definitions
#-----------------------------------------------
nwell    = input(21, 0)
diff     = input(22, 0)
poly     = input(30, 0)
contact  = input(33, 0)
met1     = input(34, 0)
via1     = input(35, 0)
met2     = input(36, 0)
# ... add all layers from your PDK layer map

#-----------------------------------------------
# Design Rules
#-----------------------------------------------

# Width rules
met1.width(0.23, euclidian).output("m1.1", "m1.1 : min. met1 width : 0.23um")
met2.width(0.28, euclidian).output("m2.1", "m2.1 : min. met2 width : 0.28um")

# Spacing rules
met1.space(0.23, euclidian).output("m1.2", "m1.2 : min. met1 spacing : 0.23um")
met2.space(0.28, euclidian).output("m2.2", "m2.2 : min. met2 spacing : 0.28um")

# Enclosure rules
met1.enclosing(contact, 0.06, euclidian).output("m1.4", "m1.4 : min. contact enclosure by met1 : 0.06um")

# Area rules
met1.with_area(nil, 0.083).output("m1.6", "m1.6 : min. met1 area : 0.083um²")
```

### Key Conventions

**Rule ID in `.output()` must match `rule_id` in `pdk.json`** — this is how the violation parser maps DRC results back to your rule metadata.

```ruby
# In .drc deck:
met1.width(0.23, euclidian).output("m1.1", "m1.1 : min. met1 width : 0.23um")
                                    ^^^^^
# In pdk.json:
{ "rule_id": "m1.1", "rule_type": "min_width", "layer": "met1", ... }
               ^^^^^
```

**Required CLI parameters** (passed by the runner automatically):
- `$input` — path to input GDS file
- `$report` — path to output `.lyrdb` report
- `$thr` — thread count
- `$drc_mode` — "deep" or "tiled"
- `$tile_size` — tile size in microns (when tiled)

**Optional flag parameters** (if your deck uses rule groups like SKY130):
- Define flags in the deck with defaults
- Override via `drc_flags` kwarg in `DRCRunner.run()` or add to `DEFAULT_DRC_FLAGS`

### Common KLayout DRC API Calls

```ruby
layer.width(min_um, euclidian)            # min width check
layer.space(min_um, euclidian)            # min spacing (same layer)
layer.separation(other, min_um, euclidian) # min spacing (different layers)
layer.enclosing(inner, min_um, euclidian) # min enclosure
layer.overlap(other, min_um, euclidian)   # min overlap
layer.with_area(nil, min_area)            # min area
layer.not_inside(other)                   # must not be inside
layer.not_outside(other)                  # must not be outside
layer.isolated(min_um, projection)        # isolated spacing (projection mode)
```

Full API reference: https://www.klayout.de/doc-qt5/about/drc_ref.html

## Step 3: Register and Test

### File Placement

```bash
mkdir -p backend/pdk/configs/<your_pdk>
cp your_pdk.json backend/pdk/configs/<your_pdk>/pdk.json
cp your_deck.drc backend/pdk/configs/<your_pdk>/
```

No code changes needed — the loader auto-discovers PDK directories.

### Validate the Config

```bash
# Quick schema validation
python -c "
from backend.pdk.schema import PDKConfig
import json
with open('backend/pdk/configs/<your_pdk>/pdk.json') as f:
    PDKConfig(**json.load(f))
print('Valid!')
"
```

### Test with a GDS File

```bash
# Upload with your PDK
curl -X POST "http://localhost:8000/api/upload?pdk_name=<your_pdk>" \
  -F "file=@test_layout.gds"

# Run DRC
curl -X POST "http://localhost:8000/api/jobs/<job_id>/drc"
```

### Create Test GDS Files

For validation, create small GDS files with intentional violations:

```python
import gdstk

lib = gdstk.Library()
cell = lib.new_cell("TEST_VIOLATIONS")

# Too-narrow metal (violates min width)
cell.add(gdstk.rectangle((0, 0), (0.1, 1.0), layer=34, datatype=0))  # met1 at 0.1um (min is 0.23)

# Too-close metals (violates min spacing)
cell.add(gdstk.rectangle((0, 0), (1, 1), layer=34, datatype=0))
cell.add(gdstk.rectangle((1.1, 0), (2.1, 1), layer=34, datatype=0))  # 0.1um gap (min is 0.23)

lib.write_gds("test_violations.gds")
```

## Checklist

Before shipping a new PDK:

- [ ] `pdk.json` passes schema validation (run the python snippet above)
- [ ] Layer numbers match the foundry layer map
- [ ] Rule IDs in `.drc` deck match `rule_id` values in `pdk.json`
- [ ] DRC deck includes `$input`, `$report`, `$thr`, `$drc_mode` handling
- [ ] DRC deck supports both `deep` and `tiled` modes
- [ ] Test GDS with intentional violations produces expected results
- [ ] Test GDS with clean layout produces zero violations
- [ ] Colors are visually distinct in the viewer
- [ ] Connectivity stack is complete (all via→metal connections)

## Reference: SKY130

The SKY130 config at `backend/pdk/configs/sky130/` is the reference implementation:
- `pdk.json` — 21 layers, 43 rules, 7 connectivity entries, 6 fix weight categories
- `sky130A_mr.drc` — 1,631 lines, ~200 rules across FEOL/BEOL/offgrid groups
- Community-maintained deck (GPLv3), vendored and tracked in this repo
