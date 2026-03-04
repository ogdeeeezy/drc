"""Poly resistor parameterized cell generator for SKY130."""

from __future__ import annotations

from dataclasses import dataclass

import gdstk

from backend.pcell.base import PCellGenerator, PCellResult


# ---------------------------------------------------------------------------
# SKY130 design rules relevant to poly resistor layout
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _SKY130ResRules:
    """SKY130 design rules for poly resistor construction.

    Values in microns sourced from the SKY130 DRM.
    """

    grid: float = 0.005

    # Poly (66/20)
    poly_min_width: float = 0.150  # poly.1a

    # RPM (86/20) — resistor poly marker
    rpm_min_width: float = 1.270  # rpm.1a
    rpm_min_spacing: float = 0.840  # rpm.2
    rpm_enc_poly: float = 0.200  # RPM enclosure of poly body (conservative)

    # poly_rs (66/13) — poly resistor ID, same extent as RPM over poly
    # The poly_rs layer marks the resistive region on poly.

    # Contact spacing from resistor body
    # licon must not be placed on the resistor body (inside RPM).
    # The contact-to-RPM spacing is implicit: contacts are placed
    # outside the RPM region at the head/tail.
    contact_to_rpm: float = 0.200  # conservative spacing

    # Licon (66/44)
    licon_size: float = 0.170  # licon.1
    licon_spacing: float = 0.170  # licon.2
    licon_enc_by_poly: float = 0.050  # licon.8

    # Li1 (67/20)
    li1_min_width: float = 0.170  # li.1
    li1_enc_licon: float = 0.080  # li.5

    # Mcon (67/44)
    mcon_size: float = 0.170  # ct.1
    mcon_spacing: float = 0.190  # ct.2

    # Met1 (68/20)
    met1_min_width: float = 0.140  # m1.1
    met1_enc_mcon: float = 0.030  # m1.4
    met1_enc_mcon_adj: float = 0.060  # m1.5

    # PSDM (94/20) enclosure
    psdm_enc_poly: float = 0.125  # approximate

    # NPC (95/20) — nitride poly cut, must cover poly-to-licon transition
    npc_enc_poly: float = 0.100  # npc enclosure of poly


SKY130_RES = _SKY130ResRules()

# ---------------------------------------------------------------------------
# GDS layer numbers (layer, datatype)
# ---------------------------------------------------------------------------
LYR_POLY = (66, 20)
LYR_POLY_RS = (66, 13)  # poly resistor ID
LYR_RPM = (86, 20)  # resistor poly marker (p+)
LYR_PSDM = (94, 20)
LYR_NPC = (95, 20)
LYR_LICON = (66, 44)
LYR_LI1 = (67, 20)
LYR_MCON = (67, 44)
LYR_MET1 = (68, 20)
LYR_MET1_PIN = (68, 16)
LYR_MET1_LBL = (68, 5)


class PolyResistorGenerator(PCellGenerator):
    """Generate a SKY130 p+ poly resistor layout.

    The resistor body is a strip of poly marked with RPM and poly_rs layers.
    Head and tail contacts connect the resistor to metal1 via the standard
    poly → licon → li1 → mcon → met1 stack.

    Multi-segment resistors use a serpentine/meander pattern where segments
    are connected by U-turn poly bends.

    Coordinate system:
        - Origin at bottom-left corner of the first segment poly
        - X axis: resistor width direction
        - Y axis: resistor length direction (segments run vertically)
    """

    def param_schema(self) -> dict:
        return {
            "w_um": {
                "type": "float",
                "description": "Resistor width in microns",
                "min": SKY130_RES.poly_min_width,
            },
            "l_um": {
                "type": "float",
                "description": "Resistor length per segment in microns",
                "min": SKY130_RES.poly_min_width,
            },
            "segments": {
                "type": "int",
                "description": "Number of resistor segments",
                "default": 1,
                "min": 1,
            },
            "head_contact": {
                "type": "bool",
                "description": "Include contact at head (PLUS) terminal",
                "default": True,
            },
            "tail_contact": {
                "type": "bool",
                "description": "Include contact at tail (MINUS) terminal",
                "default": True,
            },
        }

    def validate_params(self, params: dict) -> None:
        w_um = params.get("w_um")
        if w_um is None or w_um < SKY130_RES.poly_min_width:
            raise ValueError(
                f"w_um must be >= {SKY130_RES.poly_min_width} um "
                f"(SKY130 min poly width), got {w_um}"
            )

        l_um = params.get("l_um")
        if l_um is None or l_um < SKY130_RES.poly_min_width:
            raise ValueError(
                f"l_um must be >= {SKY130_RES.poly_min_width} um "
                f"(SKY130 min length), got {l_um}"
            )

        segments = params.get("segments", 1)
        if not isinstance(segments, int) or segments < 1:
            raise ValueError(f"segments must be an integer >= 1, got {segments}")

    def generate(self, params: dict) -> PCellResult:
        self.validate_params(params)

        w_um: float = params["w_um"]
        l_um: float = params["l_um"]
        segments: int = params.get("segments", 1)
        head_contact: bool = params.get("head_contact", True)
        tail_contact: bool = params.get("tail_contact", True)

        snap = self.snap_to_grid
        r = SKY130_RES

        w = snap(w_um)
        seg_len = snap(l_um)

        # Contact region length (poly extension for contacts)
        # Must account for RPM enclosure of poly body — the RPM extends
        # rpm_enc_poly beyond the body edge, so licons must be placed
        # outside that RPM region to avoid being clipped by licon.1 DRC rule
        # (licon.not(prec_resistor) clips licons overlapping RPM).
        contact_len = snap(
            r.rpm_enc_poly + r.contact_to_rpm + r.licon_size + r.licon_enc_by_poly
        )

        # U-turn width (poly connecting two adjacent segments)
        uturn_ext = snap(r.poly_min_width)  # minimum poly width for U-turn

        # Segment X pitch (center-to-center of adjacent segments)
        seg_pitch = snap(w + r.rpm_min_spacing)

        # Create cell
        cell_name = self.cell_name_format(
            "sky130", "polyres", W=w, L=seg_len, S=segments
        )
        cell = gdstk.Cell(cell_name)

        # Track segment endpoints for connecting
        # Each segment: (x0, y_bot, y_top, segment_index)
        seg_info: list[dict] = []

        for seg_idx in range(segments):
            seg_x0 = snap(seg_idx * seg_pitch)
            seg_x1 = snap(seg_x0 + w)

            # Odd segments are flipped (serpentine pattern)
            is_flipped = seg_idx % 2 == 1

            # Y coordinates for resistor body
            body_y0 = 0.0
            body_y1 = snap(seg_len)

            # Compute actual poly extent for this segment
            py0 = body_y0
            py1 = body_y1

            # Head extension (first segment)
            if seg_idx == 0 and head_contact:
                if not is_flipped:
                    py0 = snap(-contact_len)
                else:
                    py1 = snap(body_y1 + contact_len)

            # Tail extension (last segment)
            if seg_idx == segments - 1 and tail_contact:
                if not is_flipped:
                    py1 = snap(body_y1 + contact_len)
                else:
                    py0 = snap(-contact_len)

            # U-turn connections: extend poly to connect to next segment
            if seg_idx < segments - 1:
                # Current segment connects to next at top or bottom
                if not is_flipped:
                    # Even segment: connect at top
                    py1 = snap(body_y1 + uturn_ext)
                else:
                    # Odd segment: connect at bottom
                    py0 = snap(-uturn_ext)

            # Previous U-turn: extend to match
            if seg_idx > 0:
                prev_flipped = (seg_idx - 1) % 2 == 1
                if not prev_flipped:
                    # Previous connected at top, so this one extends to top too
                    py1 = max(py1, snap(body_y1 + uturn_ext))
                else:
                    # Previous connected at bottom
                    py0 = min(py0, snap(-uturn_ext))

            # Draw poly body
            cell.add(gdstk.rectangle(
                (seg_x0, py0), (seg_x1, py1),
                layer=LYR_POLY[0], datatype=LYR_POLY[1],
            ))

            seg_info.append({
                "x0": seg_x0, "x1": seg_x1,
                "body_y0": body_y0, "body_y1": body_y1,
                "poly_y0": py0, "poly_y1": py1,
                "flipped": is_flipped,
            })

        # U-turn poly bridges between segments
        for seg_idx in range(segments - 1):
            s_cur = seg_info[seg_idx]
            s_nxt = seg_info[seg_idx + 1]

            if not s_cur["flipped"]:
                # Even→odd: connect at top
                bridge_y0 = snap(seg_len)
                bridge_y1 = snap(seg_len + uturn_ext)
            else:
                # Odd→even: connect at bottom
                bridge_y0 = snap(-uturn_ext)
                bridge_y1 = 0.0

            cell.add(gdstk.rectangle(
                (s_cur["x0"], bridge_y0),
                (s_nxt["x1"], bridge_y1),
                layer=LYR_POLY[0], datatype=LYR_POLY[1],
            ))

        # RPM layer — covers the resistor body of each segment
        for seg_idx in range(segments):
            si = seg_info[seg_idx]
            rpm_x0 = snap(si["x0"] - r.rpm_enc_poly)
            rpm_x1 = snap(si["x1"] + r.rpm_enc_poly)
            rpm_y0 = snap(si["body_y0"] - r.rpm_enc_poly)
            rpm_y1 = snap(si["body_y1"] + r.rpm_enc_poly)

            # Enforce RPM minimum width
            rpm_w = rpm_x1 - rpm_x0
            if rpm_w < r.rpm_min_width:
                extra = snap((r.rpm_min_width - rpm_w) / 2)
                rpm_x0 = snap(rpm_x0 - extra)
                rpm_x1 = snap(rpm_x1 + extra)

            rpm_h = rpm_y1 - rpm_y0
            if rpm_h < r.rpm_min_width:
                extra = snap((r.rpm_min_width - rpm_h) / 2)
                rpm_y0 = snap(rpm_y0 - extra)
                rpm_y1 = snap(rpm_y1 + extra)

            cell.add(gdstk.rectangle(
                (rpm_x0, rpm_y0), (rpm_x1, rpm_y1),
                layer=LYR_RPM[0], datatype=LYR_RPM[1],
            ))

        # poly_rs layer — same as RPM extent over each segment body
        for seg_idx in range(segments):
            si = seg_info[seg_idx]
            cell.add(gdstk.rectangle(
                (si["x0"], si["body_y0"]),
                (si["x1"], si["body_y1"]),
                layer=LYR_POLY_RS[0], datatype=LYR_POLY_RS[1],
            ))

        # PSDM layer — covers resistor area (p+ implant)
        psdm_x0 = snap(seg_info[0]["x0"] - r.psdm_enc_poly)
        psdm_x1 = snap(seg_info[-1]["x1"] + r.psdm_enc_poly)
        psdm_y0 = snap(min(si["poly_y0"] for si in seg_info) - r.psdm_enc_poly)
        psdm_y1 = snap(max(si["poly_y1"] for si in seg_info) + r.psdm_enc_poly)
        cell.add(gdstk.rectangle(
            (psdm_x0, psdm_y0), (psdm_x1, psdm_y1),
            layer=LYR_PSDM[0], datatype=LYR_PSDM[1],
        ))

        # Licon center offset from body edge — positioned outside RPM region
        # RPM extends rpm_enc_poly beyond body, then contact_to_rpm gap,
        # then licon starts. Center is at rpm_enc_poly + contact_to_rpm + licon_size/2.
        licon_offset = snap(
            r.rpm_enc_poly + r.contact_to_rpm + r.licon_size / 2
        )

        # Head contact (PLUS terminal) — on first segment
        head_info = seg_info[0]
        if head_contact:
            if not head_info["flipped"]:
                # Contact at bottom of first segment
                contact_cy = snap(-licon_offset)
            else:
                contact_cy = snap(seg_len + licon_offset)
            self._place_terminal_contacts(
                cell, head_info["x0"], head_info["x1"],
                contact_cy, w, "PLUS", r,
            )

        # Tail contact (MINUS terminal) — on last segment
        tail_info = seg_info[-1]
        if tail_contact:
            if not tail_info["flipped"]:
                # Contact at top of last segment
                contact_cy = snap(seg_len + licon_offset)
            else:
                contact_cy = snap(-licon_offset)
            self._place_terminal_contacts(
                cell, tail_info["x0"], tail_info["x1"],
                contact_cy, w, "MINUS", r,
            )

        # NPC layer — covers poly-to-contact transitions at terminals
        npc_enc = r.npc_enc_poly
        for si in seg_info:
            cell.add(gdstk.rectangle(
                (snap(si["x0"] - npc_enc), snap(si["poly_y0"] - npc_enc)),
                (snap(si["x1"] + npc_enc), snap(si["poly_y1"] + npc_enc)),
                layer=LYR_NPC[0], datatype=LYR_NPC[1],
            ))

        # Total resistance length
        total_res_length = snap(seg_len * segments)

        return PCellResult(
            cell=cell,
            cell_name=cell_name,
            params={
                "w_um": w,
                "l_um": seg_len,
                "segments": segments,
                "head_contact": head_contact,
                "tail_contact": tail_contact,
            },
            metadata={
                "total_resistance_length_um": total_res_length,
                "segments": segments,
                "segment_length_um": seg_len,
            },
        )

    # ---- helpers ---------------------------------------------------------------

    def _place_terminal_contacts(
        self,
        cell: gdstk.Cell,
        poly_x0: float,
        poly_x1: float,
        center_y: float,
        poly_width: float,
        label: str,
        rules: _SKY130ResRules,
    ) -> None:
        """Place a contact array (licon → li1 → mcon → met1) at a terminal."""
        snap = self.snap_to_grid
        poly_cx = snap((poly_x0 + poly_x1) / 2)

        # Contact array in X direction
        contact_pitch = snap(
            rules.licon_size + max(rules.licon_spacing, rules.mcon_spacing)
        )
        available = poly_width - 2 * rules.licon_enc_by_poly
        n_contacts = max(1, 1 + int((available - rules.licon_size) / contact_pitch))
        total_span = (n_contacts - 1) * contact_pitch
        x_start = snap(poly_cx - total_span / 2)

        contact_positions = [snap(x_start + i * contact_pitch) for i in range(n_contacts)]

        # Licon contacts
        for cx in contact_positions:
            self._add_contact_square(cell, cx, center_y, rules.licon_size, LYR_LICON)

        # Li1 pad
        li1_half_x = snap(
            max(rules.li1_min_width, total_span + rules.licon_size + 2 * rules.li1_enc_licon) / 2
        )
        li1_half_y = snap(
            max(rules.li1_min_width, rules.licon_size + 2 * rules.li1_enc_licon) / 2
        )
        cell.add(gdstk.rectangle(
            (snap(poly_cx - li1_half_x), snap(center_y - li1_half_y)),
            (snap(poly_cx + li1_half_x), snap(center_y + li1_half_y)),
            layer=LYR_LI1[0], datatype=LYR_LI1[1],
        ))

        # Mcon contacts
        for cx in contact_positions:
            self._add_contact_square(cell, cx, center_y, rules.mcon_size, LYR_MCON)

        # Met1 pad
        met1_enc = rules.met1_enc_mcon_adj
        met1_half_x = snap(
            max(rules.met1_min_width, total_span + rules.mcon_size + 2 * met1_enc) / 2
        )
        met1_half_y = snap(
            max(rules.met1_min_width, rules.mcon_size + 2 * met1_enc) / 2
        )
        cell.add(gdstk.rectangle(
            (snap(poly_cx - met1_half_x), snap(center_y - met1_half_y)),
            (snap(poly_cx + met1_half_x), snap(center_y + met1_half_y)),
            layer=LYR_MET1[0], datatype=LYR_MET1[1],
        ))

        # Pin label
        cell.add(gdstk.Label(
            label, (poly_cx, center_y),
            layer=LYR_MET1_LBL[0], texttype=LYR_MET1_LBL[1],
        ))

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
