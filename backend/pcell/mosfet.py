"""MOSFET parameterized cell generator for SKY130."""

from __future__ import annotations

from dataclasses import dataclass

import gdstk

from backend.pcell.base import PCellGenerator, PCellResult


# ---------------------------------------------------------------------------
# SKY130 design rules relevant to MOSFET layout
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _SKY130Rules:
    """SKY130 design rules for MOSFET construction.

    Values in microns sourced from the SKY130 DRM and pdk.json.
    """

    grid: float = 0.005

    # Diffusion (65/20)
    diff_min_width: float = 0.150  # difftap.1
    diff_ext_poly: float = 0.250  # poly.7 — S/D extension beyond gate

    # Poly (66/20)
    poly_min_width: float = 0.150  # poly.1a
    poly_min_spacing: float = 0.210  # poly.2
    poly_ext_diff: float = 0.130  # poly.8 — endcap extension (no contact)

    # Nwell (64/20)
    nwell_enc_diff: float = 0.180  # difftap.8
    nwell_min_width: float = 0.840  # nwell.1

    # Licon (66/44) — local interconnect contact
    licon_size: float = 0.170  # licon.1 (square)
    licon_spacing: float = 0.170  # licon.2
    licon_enc_by_diff: float = 0.040  # licon.5a
    licon_enc_by_poly: float = 0.050  # licon.8
    licon_to_poly_on_diff: float = 0.055  # licon.11 (poly edge to diff-licon)

    # Li1 (67/20) — local interconnect routing
    li1_min_width: float = 0.170  # li.1
    li1_enc_licon: float = 0.080  # li.5 (one pair of adj sides)

    # Mcon (67/44) — li1 to met1 contact
    mcon_size: float = 0.170  # ct.1 (square)
    mcon_spacing: float = 0.190  # ct.2

    # Met1 (68/20)
    met1_min_width: float = 0.140  # m1.1
    met1_min_spacing: float = 0.140  # m1.2
    met1_enc_mcon: float = 0.030  # m1.4
    met1_enc_mcon_adj: float = 0.060  # m1.5 (one pair of adj sides)

    # Implant enclosure of diff (approximate, conservative)
    implant_enc_diff: float = 0.125


# Singleton
SKY130 = _SKY130Rules()

# ---------------------------------------------------------------------------
# GDS layer numbers (layer, datatype)
# ---------------------------------------------------------------------------
LYR_NWELL = (64, 20)
LYR_DIFF = (65, 20)
LYR_POLY = (66, 20)
LYR_NSDM = (93, 44)
LYR_PSDM = (94, 20)
LYR_NPC = (95, 20)
LYR_LICON = (66, 44)
LYR_LI1 = (67, 20)
LYR_MCON = (67, 44)
LYR_MET1 = (68, 20)
LYR_MET1_PIN = (68, 16)  # met1 pin purpose
LYR_MET1_LBL = (68, 5)  # met1 label purpose


class MOSFETGenerator(PCellGenerator):
    """Generate a SKY130 MOSFET layout with multi-finger support.

    The layout uses the following connection stack:
        diff → licon → li1 → mcon → met1 (pins)

    Coordinate system:
        - Origin at bottom-left corner of diffusion
        - X axis: gate pitch direction (left → right)
        - Y axis: gate width direction (bottom → top)
    """

    def param_schema(self) -> dict:
        return {
            "device_type": {
                "type": "str",
                "description": "MOSFET type",
                "choices": ["nmos", "pmos"],
            },
            "w_um": {
                "type": "float",
                "description": "Gate width in microns",
                "min": SKY130.diff_min_width,
            },
            "l_um": {
                "type": "float",
                "description": "Gate length in microns",
                "min": SKY130.poly_min_width,
            },
            "fingers": {
                "type": "int",
                "description": "Number of gate fingers",
                "default": 1,
                "min": 1,
            },
            "gate_contact": {
                "type": "str",
                "description": "Gate contact placement",
                "choices": ["top", "bottom", "both"],
                "default": "both",
            },
        }

    def validate_params(self, params: dict) -> None:
        device_type = params.get("device_type")
        if device_type not in ("nmos", "pmos"):
            raise ValueError(
                f"device_type must be 'nmos' or 'pmos', got '{device_type}'"
            )

        w_um = params.get("w_um")
        if w_um is None or w_um < SKY130.diff_min_width:
            raise ValueError(
                f"w_um must be >= {SKY130.diff_min_width} um (SKY130 min diff width), "
                f"got {w_um}"
            )

        l_um = params.get("l_um")
        if l_um is None or l_um < SKY130.poly_min_width:
            raise ValueError(
                f"l_um must be >= {SKY130.poly_min_width} um (SKY130 min poly width), "
                f"got {l_um}"
            )

        fingers = params.get("fingers", 1)
        if not isinstance(fingers, int) or fingers < 1:
            raise ValueError(f"fingers must be an integer >= 1, got {fingers}")

        gate_contact = params.get("gate_contact", "both")
        if gate_contact not in ("top", "bottom", "both"):
            raise ValueError(
                f"gate_contact must be 'top', 'bottom', or 'both', "
                f"got '{gate_contact}'"
            )

    def generate(self, params: dict) -> PCellResult:
        self.validate_params(params)

        device_type: str = params["device_type"]
        w_um: float = params["w_um"]
        l_um: float = params["l_um"]
        fingers: int = params.get("fingers", 1)
        gate_contact: str = params.get("gate_contact", "both")

        # Snap dimensions to grid
        snap = self.snap_to_grid
        w = snap(w_um)
        gl = snap(l_um)  # gate length

        # Derived dimensions --------------------------------------------------
        r = SKY130  # shorthand

        # Width of poly endcap for gate contact (must fit licon + enclosure)
        gc_licon_width = r.licon_size + 2 * r.licon_enc_by_poly  # 0.270
        nc_ext = snap(r.poly_ext_diff)  # 0.130 (no-contact endcap)

        # Edge source/drain width (diff edge to first/last poly edge)
        edge_sd = snap(
            max(r.diff_ext_poly, r.licon_to_poly_on_diff + r.licon_size + r.licon_enc_by_diff)
        )  # max(0.250, 0.265) = 0.265

        # Internal S/D width (between two adjacent poly edges)
        # Must accommodate both licon contacts AND met1 pads with m1.2 spacing
        licon_sd = snap(
            r.licon_to_poly_on_diff + r.licon_size + r.licon_to_poly_on_diff
        )  # 0.280
        met1_pad_w = snap(r.mcon_size + 2 * r.met1_enc_mcon)
        met1_sd = snap(met1_pad_w + r.met1_min_spacing)  # 0.370
        internal_sd = snap(max(licon_sd, met1_sd))

        # Unified contact pitch (satisfies both licon and mcon spacing)
        contact_pitch = snap(r.licon_size + max(r.licon_spacing, r.mcon_spacing))
        # = 0.170 + 0.190 = 0.360

        # Diffusion dimensions
        diff_w = snap(2 * edge_sd + fingers * gl + (fingers - 1) * internal_sd)
        diff_h = w  # gate width

        # Pre-compute vertical contact array (needed for dynamic gate contact Y)
        n_contacts_y, contact_y_positions = self._contact_array_y(w, contact_pitch, r)

        # --- Dynamic gate contact Y positioning (m1.2 clearance) ---------------
        # S/D met1 dimensions
        met1_sd_half_x = snap(
            max(r.met1_min_width, r.mcon_size + 2 * r.met1_enc_mcon) / 2
        )
        met1_sd_enc_y = r.met1_enc_mcon_adj  # 0.060 — m1.5 adj pair

        sd_met1_bot = snap(contact_y_positions[0] - r.mcon_size / 2 - met1_sd_enc_y)
        sd_met1_top = snap(contact_y_positions[-1] + r.mcon_size / 2 + met1_sd_enc_y)

        # Enforce m1.6 (min area 0.083µm²) on S/D met1 pads
        sd_met1_w = snap(2 * met1_sd_half_x)
        sd_met1_h = snap(sd_met1_top - sd_met1_bot)
        min_area = 0.083
        if sd_met1_w * sd_met1_h < min_area:
            min_h = snap(min_area / sd_met1_w + r.grid)
            extend = snap((min_h - sd_met1_h) / 2)
            sd_met1_bot = snap(sd_met1_bot - extend)
            sd_met1_top = snap(sd_met1_top + extend)

        # Gate met1 pad dimensions
        met1_gc_half = snap(
            max(r.met1_min_width, r.mcon_size + 2 * r.met1_enc_mcon_adj) / 2
        )
        met1_gc_enc = r.met1_enc_mcon_adj
        gc_m1_half_y = snap(
            max(r.met1_min_width, r.mcon_size + 2 * met1_gc_enc) / 2
        )
        gc_m1_w = snap(2 * met1_gc_half)
        gc_m1_h = snap(2 * gc_m1_half_y)
        if gc_m1_w * gc_m1_h < min_area:
            gc_m1_half_y = snap(min_area / gc_m1_w / 2 + r.grid)

        # Push gate contacts far enough for m1.2 clearance to S/D met1
        gc_cy_top_natural = snap(diff_h + r.licon_enc_by_poly + r.licon_size / 2)
        min_gc_cy_top = snap(sd_met1_top + r.met1_min_spacing + gc_m1_half_y)
        gc_cy_top = snap(max(gc_cy_top_natural, min_gc_cy_top))

        gc_cy_bot_natural = snap(-(r.licon_enc_by_poly + r.licon_size / 2))
        max_gc_cy_bot = snap(sd_met1_bot - r.met1_min_spacing - gc_m1_half_y)
        gc_cy_bot = snap(min(gc_cy_bot_natural, max_gc_cy_bot))

        # Poly extension for gate contacts (dynamic, based on actual gc positions)
        gc_ext_top = snap(gc_cy_top + r.licon_size / 2 + r.licon_enc_by_poly - diff_h)
        gc_ext_bot = snap(abs(gc_cy_bot) + r.licon_size / 2 + r.licon_enc_by_poly)

        # Create cell -----------------------------------------------------------
        cell_name = self.cell_name_format(
            "sky130", device_type, W=w, L=gl, F=fingers
        )
        cell = gdstk.Cell(cell_name)

        # 1. Diffusion ----------------------------------------------------------
        cell.add(gdstk.rectangle((0, 0), (diff_w, diff_h), layer=LYR_DIFF[0], datatype=LYR_DIFF[1]))

        # 2. Poly gates ---------------------------------------------------------
        gate_positions: list[float] = []  # left X of each gate
        for i in range(fingers):
            gx0 = snap(edge_sd + i * (gl + internal_sd))
            gx1 = snap(gx0 + gl)
            gate_positions.append(gx0)

            # Poly Y extents
            py_bot = -gc_ext_bot if gate_contact in ("bottom", "both") else -nc_ext
            py_top = diff_h + gc_ext_top if gate_contact in ("top", "both") else diff_h + nc_ext

            # Main gate body
            cell.add(gdstk.rectangle(
                (gx0, py_bot), (gx1, py_top),
                layer=LYR_POLY[0], datatype=LYR_POLY[1],
            ))

            # T-gate widening for gate contact if L < gc_licon_width
            if gl < gc_licon_width:
                poly_cx = snap(gx0 + gl / 2)
                pad_half = snap(gc_licon_width / 2)
                pad_x0 = snap(poly_cx - pad_half)
                pad_x1 = snap(poly_cx + pad_half)

                if gate_contact in ("top", "both"):
                    cell.add(gdstk.rectangle(
                        (pad_x0, diff_h), (pad_x1, diff_h + gc_ext_top),
                        layer=LYR_POLY[0], datatype=LYR_POLY[1],
                    ))
                if gate_contact in ("bottom", "both"):
                    cell.add(gdstk.rectangle(
                        (pad_x0, -gc_ext_bot), (pad_x1, 0),
                        layer=LYR_POLY[0], datatype=LYR_POLY[1],
                    ))

        # 3. Source/drain contacts (licon on diff) --------------------------------
        sd_regions: list[tuple[float, bool]] = []  # (center_x, is_source)
        for i in range(fingers + 1):
            is_source = (i % 2 == 0)

            if i == 0:
                # Left edge: licon centered in [0, edge_sd]
                cx = snap(edge_sd / 2)
            elif i == fingers:
                # Right edge: licon centered in [last_gate_x1, diff_w]
                last_gx1 = snap(edge_sd + (fingers - 1) * (gl + internal_sd) + gl)
                cx = snap((last_gx1 + diff_w) / 2)
            else:
                # Internal: licon centered between two gates
                left_gx1 = snap(edge_sd + (i - 1) * (gl + internal_sd) + gl)
                right_gx0 = snap(edge_sd + i * (gl + internal_sd))
                cx = snap((left_gx1 + right_gx0) / 2)

            sd_regions.append((cx, is_source))

        # Place licon contacts for each S/D region (contact_y_positions pre-computed above)
        for cx, _is_source in sd_regions:
            for cy in contact_y_positions:
                self._add_contact_square(cell, cx, cy, r.licon_size, LYR_LICON)

        # 4. Gate contacts (licon on poly endcap) ---------------------------------
        gate_contact_x_positions: list[float] = []
        for gx0 in gate_positions:
            poly_cx = snap(gx0 + gl / 2)
            gate_contact_x_positions.append(poly_cx)

            if gate_contact in ("top", "both"):
                self._add_contact_square(cell, poly_cx, gc_cy_top, r.licon_size, LYR_LICON)
            if gate_contact in ("bottom", "both"):
                self._add_contact_square(cell, poly_cx, gc_cy_bot, r.licon_size, LYR_LICON)

        # 5. Li1 routing ----------------------------------------------------------
        # Li1 strips over S/D contacts
        li1_half_w = snap(r.li1_min_width / 2)  # 0.085
        li1_y_bot = snap(contact_y_positions[0] - r.licon_size / 2 - r.li1_enc_licon)
        li1_y_top = snap(contact_y_positions[-1] + r.licon_size / 2 + r.li1_enc_licon)

        for cx, _is_source in sd_regions:
            cell.add(gdstk.rectangle(
                (snap(cx - li1_half_w), li1_y_bot),
                (snap(cx + li1_half_w), li1_y_top),
                layer=LYR_LI1[0], datatype=LYR_LI1[1],
            ))

        # Li1 pads over gate contacts
        li1_gc_margin = r.licon_size / 2 + r.li1_enc_licon
        for poly_cx in gate_contact_x_positions:
            gc_li1_half = snap(
                max(r.li1_min_width, r.licon_size + 2 * r.li1_enc_licon) / 2
            )
            if gate_contact in ("top", "both"):
                cell.add(gdstk.rectangle(
                    (snap(poly_cx - gc_li1_half),
                     snap(gc_cy_top - li1_gc_margin)),
                    (snap(poly_cx + gc_li1_half),
                     snap(gc_cy_top + li1_gc_margin)),
                    layer=LYR_LI1[0], datatype=LYR_LI1[1],
                ))
            if gate_contact in ("bottom", "both"):
                cell.add(gdstk.rectangle(
                    (snap(poly_cx - gc_li1_half),
                     snap(gc_cy_bot - li1_gc_margin)),
                    (snap(poly_cx + gc_li1_half),
                     snap(gc_cy_bot + li1_gc_margin)),
                    layer=LYR_LI1[0], datatype=LYR_LI1[1],
                ))

        # 6. Mcon contacts (on li1) -----------------------------------------------
        for cx, _is_source in sd_regions:
            for cy in contact_y_positions:
                self._add_contact_square(cell, cx, cy, r.mcon_size, LYR_MCON)

        for poly_cx in gate_contact_x_positions:
            if gate_contact in ("top", "both"):
                self._add_contact_square(cell, poly_cx, gc_cy_top, r.mcon_size, LYR_MCON)
            if gate_contact in ("bottom", "both"):
                self._add_contact_square(cell, poly_cx, gc_cy_bot, r.mcon_size, LYR_MCON)

        # 7. Met1 pins ------------------------------------------------------------
        # S/D met1 uses pre-computed bounds (includes m1.6 min area enforcement)
        for cx, is_source in sd_regions:
            cell.add(gdstk.rectangle(
                (snap(cx - met1_sd_half_x), sd_met1_bot),
                (snap(cx + met1_sd_half_x), sd_met1_top),
                layer=LYR_MET1[0], datatype=LYR_MET1[1],
            ))
            label_text = "S" if is_source else "D"
            label_y = snap((sd_met1_bot + sd_met1_top) / 2)
            cell.add(gdstk.Label(
                label_text, (cx, label_y),
                layer=LYR_MET1_LBL[0], texttype=LYR_MET1_LBL[1],
            ))

        # Gate met1 pads (dimensions and m1.6 pre-computed above)
        for poly_cx in gate_contact_x_positions:
            if gate_contact in ("top", "both"):
                cell.add(gdstk.rectangle(
                    (snap(poly_cx - met1_gc_half), snap(gc_cy_top - gc_m1_half_y)),
                    (snap(poly_cx + met1_gc_half), snap(gc_cy_top + gc_m1_half_y)),
                    layer=LYR_MET1[0], datatype=LYR_MET1[1],
                ))
                cell.add(gdstk.Label(
                    "G", (poly_cx, gc_cy_top),
                    layer=LYR_MET1_LBL[0], texttype=LYR_MET1_LBL[1],
                ))
            if gate_contact in ("bottom", "both"):
                cell.add(gdstk.rectangle(
                    (snap(poly_cx - met1_gc_half), snap(gc_cy_bot - gc_m1_half_y)),
                    (snap(poly_cx + met1_gc_half), snap(gc_cy_bot + gc_m1_half_y)),
                    layer=LYR_MET1[0], datatype=LYR_MET1[1],
                ))
                cell.add(gdstk.Label(
                    "G", (poly_cx, gc_cy_bot),
                    layer=LYR_MET1_LBL[0], texttype=LYR_MET1_LBL[1],
                ))

        # Body label at substrate (bottom-left of diff)
        cell.add(gdstk.Label(
            "B", (0, 0),
            layer=LYR_MET1_LBL[0], texttype=LYR_MET1_LBL[1],
        ))

        # 8. Implant layers -------------------------------------------------------
        imp_enc = snap(r.implant_enc_diff)
        imp_x0 = snap(-imp_enc)
        imp_x1 = snap(diff_w + imp_enc)
        imp_y0 = snap(-imp_enc)
        imp_y1 = snap(diff_h + imp_enc)

        if device_type == "nmos":
            cell.add(gdstk.rectangle(
                (imp_x0, imp_y0), (imp_x1, imp_y1),
                layer=LYR_NSDM[0], datatype=LYR_NSDM[1],
            ))
        else:  # pmos
            cell.add(gdstk.rectangle(
                (imp_x0, imp_y0), (imp_x1, imp_y1),
                layer=LYR_PSDM[0], datatype=LYR_PSDM[1],
            ))

        # 9. Nwell (PMOS only) ----------------------------------------------------
        if device_type == "pmos":
            nw_enc = snap(r.nwell_enc_diff)
            nw_x0 = snap(-nw_enc)
            nw_x1 = snap(diff_w + nw_enc)
            nw_y0 = snap(-nw_enc)
            nw_y1 = snap(diff_h + nw_enc)
            # Enforce nwell min width
            if (nw_x1 - nw_x0) < r.nwell_min_width:
                extra = snap((r.nwell_min_width - (nw_x1 - nw_x0)) / 2)
                nw_x0 -= extra
                nw_x1 += extra
            if (nw_y1 - nw_y0) < r.nwell_min_width:
                extra = snap((r.nwell_min_width - (nw_y1 - nw_y0)) / 2)
                nw_y0 -= extra
                nw_y1 += extra
            cell.add(gdstk.rectangle(
                (nw_x0, nw_y0), (nw_x1, nw_y1),
                layer=LYR_NWELL[0], datatype=LYR_NWELL[1],
            ))

        # Build result -----------------------------------------------------------
        return PCellResult(
            cell=cell,
            cell_name=cell_name,
            params={
                "device_type": device_type,
                "w_um": w,
                "l_um": gl,
                "fingers": fingers,
                "gate_contact": gate_contact,
            },
            metadata={
                "diff_width_um": diff_w,
                "diff_height_um": diff_h,
                "n_sd_contacts_y": n_contacts_y,
                "n_sd_regions": fingers + 1,
            },
        )

    # ---- helpers ---------------------------------------------------------------

    @staticmethod
    def _contact_array_y(
        width: float, pitch: float, rules: _SKY130Rules
    ) -> tuple[int, list[float]]:
        """Compute Y positions for a vertical contact array within gate width.

        Returns (count, [center_y_positions]).
        """
        snap = PCellGenerator.snap_to_grid
        available = width - 2 * rules.licon_enc_by_diff  # diff enclosure on each side
        if available < rules.licon_size:
            raise ValueError(
                f"Gate width {width} um too small for even one contact "
                f"(need >= {rules.licon_size + 2 * rules.licon_enc_by_diff} um)"
            )

        n = 1 + int((available - rules.licon_size) / pitch)
        total_span = (n - 1) * pitch + rules.licon_size
        y_start = snap((width - total_span) / 2 + rules.licon_size / 2)

        positions = [snap(y_start + i * pitch) for i in range(n)]
        return n, positions

    @staticmethod
    def _add_contact_square(
        cell: gdstk.Cell,
        cx: float,
        cy: float,
        size: float,
        layer_dt: tuple[int, int],
    ) -> None:
        """Add a square contact centered at (cx, cy)."""
        snap = PCellGenerator.snap_to_grid
        half = snap(size / 2)
        cell.add(gdstk.rectangle(
            (snap(cx - half), snap(cy - half)),
            (snap(cx + half), snap(cy + half)),
            layer=layer_dt[0],
            datatype=layer_dt[1],
        ))
