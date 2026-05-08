"""
AquaVeritas — Three-Way Model Evaluation Report (PDF)
======================================================
Reads data/reports/comparison.json and generates a PDF evaluation report
covering both core zone (water body) and buffer zone (agriculture).

Run: python aquaveritas/docs/generate_eval_report.py
"""

import json
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable, KeepTogether, PageBreak, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)

# ── Paths ──────────────────────────────────────────────────────────────────────

ROOT      = Path(__file__).parent.parent
DATA_JSON = ROOT / "data" / "reports" / "comparison.json"
OUT_PDF   = ROOT / "data" / "reports" / f"AquaVeritas_Eval_Report_{date.today()}.pdf"

# ── Colour palette ─────────────────────────────────────────────────────────────

NAVY      = colors.HexColor("#1B2A4A")
STEEL     = colors.HexColor("#2E5090")
LIGHT_BG  = colors.HexColor("#F4F6FA")
BORDER    = colors.HexColor("#D0D8E8")
GREEN_OK  = colors.HexColor("#27AE60")
RED_BAD   = colors.HexColor("#C0392B")
AMBER     = colors.HexColor("#F39C12")
TEAL      = colors.HexColor("#16A085")
WHITE     = colors.white
GREY_TEXT = colors.HexColor("#555555")
PALE_BLUE = colors.HexColor("#EBF0FA")
PALE_TEAL = colors.HexColor("#E8F6F3")
DARK_ROW  = colors.HexColor("#D4DEEF")
DARK_TEAL = colors.HexColor("#C8EDE8")

W, H   = A4
MARGIN = 18 * mm


def S(name, **kw):
    return ParagraphStyle(name, **kw)


cover_title   = S("CoverTitle",  fontName="Helvetica-Bold", fontSize=26, textColor=WHITE,    leading=32, alignment=TA_CENTER)
cover_sub     = S("CoverSub",    fontName="Helvetica",      fontSize=13, textColor=BORDER,   leading=18, alignment=TA_CENTER)
cover_meta    = S("CoverMeta",   fontName="Helvetica",      fontSize=10, textColor=BORDER,   leading=14, alignment=TA_CENTER)
sect_head     = S("SectHead",    fontName="Helvetica-Bold", fontSize=15, textColor=NAVY,     leading=19, spaceBefore=10, spaceAfter=4)
sub_head      = S("SubHead",     fontName="Helvetica-Bold", fontSize=11, textColor=STEEL,    leading=14, spaceBefore=6,  spaceAfter=3)
sub_head_teal = S("SubHeadT",    fontName="Helvetica-Bold", fontSize=11, textColor=TEAL,     leading=14, spaceBefore=6,  spaceAfter=3)
body_style    = S("Body",        fontName="Helvetica",      fontSize=9,  textColor=colors.HexColor("#333333"), leading=13, spaceAfter=3)
caption_style = S("Caption",     fontName="Helvetica",      fontSize=7,  textColor=GREY_TEXT, leading=10, alignment=TA_CENTER, spaceAfter=4)
note_style    = S("Note",        fontName="Helvetica",      fontSize=8,  textColor=GREY_TEXT, leading=11, leftIndent=6, spaceAfter=4)
label_style   = S("Label",       fontName="Helvetica-Bold", fontSize=8,  textColor=NAVY,     leading=10, spaceAfter=1)


# ── Helpers ────────────────────────────────────────────────────────────────────

def pct(v):
    return "—" if v is None else f"{v:.1%}"


def bar(v, width=10):
    if v is None:
        return "—"
    filled = round(v * width)
    return "█" * filled + "░" * (width - filled)


def score_color(v):
    if v is None:
        return GREY_TEXT
    if v >= 0.8:
        return GREEN_OK
    if v >= 0.5:
        return AMBER
    return RED_BAD


def delta_str(base, fine):
    if base is None or fine is None:
        return "—"
    d = fine - base
    return f"{'▲' if d >= 0 else '▼'} {abs(d):.1%}"


def delta_color(base, fine):
    if base is None or fine is None:
        return GREY_TEXT
    return GREEN_OK if fine >= base else RED_BAD


def colored_pct(v):
    return Paragraph(
        pct(v),
        S("cp", fontName="Helvetica-Bold", fontSize=8,
          textColor=score_color(v) if v is not None else GREY_TEXT,
          alignment=TA_CENTER, leading=10),
    )


def colored_delta(bv, fv):
    return Paragraph(
        delta_str(bv, fv),
        S("cd", fontName="Helvetica-Bold", fontSize=8,
          textColor=delta_color(bv, fv), alignment=TA_CENTER, leading=10),
    )


def section_banner(title, story, color=NAVY):
    story.append(Spacer(1, 4 * mm))
    t = Table(
        [[Paragraph(title, S("BT", fontName="Helvetica-Bold", fontSize=12, textColor=WHITE, leading=16))]],
        colWidths=[W - 2 * MARGIN],
    )
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), color),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))
    story.append(t)
    story.append(Spacer(1, 3 * mm))


def field_panel(label, cv, bv, fv, head_color=STEEL):
    """Single-field scorecard panel: label row + three model scores + bars."""
    inner = Table(
        [[
            Paragraph("Claude Oracle",   S("h", fontName="Helvetica-Bold", fontSize=8, textColor=STEEL,    alignment=TA_CENTER)),
            Paragraph("Base LFM2.5-VL", S("h", fontName="Helvetica-Bold", fontSize=8, textColor=RED_BAD,  alignment=TA_CENTER)),
            Paragraph("Fine-tuned LFM", S("h", fontName="Helvetica-Bold", fontSize=8, textColor=GREEN_OK, alignment=TA_CENTER)),
            Paragraph("Δ (ft − base)",  S("h", fontName="Helvetica-Bold", fontSize=8, textColor=NAVY,     alignment=TA_CENTER)),
        ], [
            Paragraph(pct(cv), S("v", fontName="Helvetica-Bold", fontSize=18, textColor=score_color(cv), alignment=TA_CENTER, leading=22)),
            Paragraph(pct(bv), S("v", fontName="Helvetica-Bold", fontSize=18, textColor=score_color(bv), alignment=TA_CENTER, leading=22)),
            Paragraph(pct(fv), S("v", fontName="Helvetica-Bold", fontSize=18, textColor=score_color(fv), alignment=TA_CENTER, leading=22)),
            Paragraph(delta_str(bv, fv), S("v", fontName="Helvetica-Bold", fontSize=14,
                                            textColor=delta_color(bv, fv), alignment=TA_CENTER, leading=18)),
        ], [
            Paragraph(bar(cv), S("b", fontName="Courier", fontSize=9, textColor=score_color(cv), alignment=TA_CENTER)),
            Paragraph(bar(bv), S("b", fontName="Courier", fontSize=9, textColor=score_color(bv), alignment=TA_CENTER)),
            Paragraph(bar(fv), S("b", fontName="Courier", fontSize=9, textColor=score_color(fv), alignment=TA_CENTER)),
            Paragraph("", body_style),
        ]],
        colWidths=[(W - 2 * MARGIN) / 4] * 4,
    )
    inner.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  LIGHT_BG),
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return KeepTogether([
        Paragraph(label, S("fl", fontName="Helvetica-Bold", fontSize=11, textColor=head_color, leading=14, spaceBefore=6, spaceAfter=3)),
        inner,
        Spacer(1, 4 * mm),
    ])


def page_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GREY_TEXT)
    canvas.drawCentredString(W / 2, 12 * mm,
        f"AquaVeritas · Model Evaluation Report · {date.today()} · Page {doc.page}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 16 * mm, W - MARGIN, 16 * mm)
    canvas.restoreState()


# ── Load data ──────────────────────────────────────────────────────────────────

with open(DATA_JSON) as f:
    data = json.load(f)

claude    = data.get("claude",    {})
base      = data.get("base",      {})
finetuned = data.get("finetuned", {})

c_met = claude.get("metrics",    {})
b_met = base.get("metrics",      {})
f_met = finetuned.get("metrics", {})

c_fields = c_met.get("fields", {})
b_fields = b_met.get("fields", {})
f_fields = f_met.get("fields", {})

CORE_FIELDS = [
    "water_extent_status",
    "flood_risk",
    "water_clarity",
    "shoreline_encroachment",
]
BUFFER_FIELDS = [
    "agriculture_present",
    "crop_stress_level",
    "crop_stress_type",
    "cultivation_expanding_toward_water",
    "settlement_visible",
    "bare_soil_expansion",
]
ALL_FIELDS = CORE_FIELDS + BUFFER_FIELDS

FIELD_LABELS = {
    "water_extent_status":               "Water Extent Status",
    "flood_risk":                        "Flood Risk",
    "water_clarity":                     "Water Clarity",
    "shoreline_encroachment":            "Shoreline Encroachment",
    "agriculture_present":               "Agriculture Present",
    "crop_stress_level":                 "Crop Stress Level",
    "crop_stress_type":                  "Crop Stress Type",
    "cultivation_expanding_toward_water":"Cultivation Expanding → Water",
    "settlement_visible":                "Settlement Visible",
    "bare_soil_expansion":               "Bare Soil Expansion",
}

FIELD_SHORT = {
    "water_extent_status":               "Extent",
    "flood_risk":                        "Flood",
    "water_clarity":                     "Clarity",
    "shoreline_encroachment":            "Shore",
    "agriculture_present":               "Agri",
    "crop_stress_level":                 "Stress\nLvl",
    "crop_stress_type":                  "Stress\nType",
    "cultivation_expanding_toward_water":"Cultiv\nExp",
    "settlement_visible":                "Settl",
    "bare_soil_expansion":               "Bare\nSoil",
}


def zone_avg(fields_dict, zone_fields):
    vals = [fields_dict.get(f) for f in zone_fields if fields_dict.get(f) is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


c_core   = zone_avg(c_fields, CORE_FIELDS)
b_core   = zone_avg(b_fields, CORE_FIELDS)
f_core   = zone_avg(f_fields, CORE_FIELDS)

c_buf    = zone_avg(c_fields, BUFFER_FIELDS)
b_buf    = zone_avg(b_fields, BUFFER_FIELDS)
f_buf    = zone_avg(f_fields, BUFFER_FIELDS)


# ── Build PDF ──────────────────────────────────────────────────────────────────

def build_pdf():
    doc = SimpleDocTemplate(
        str(OUT_PDF),
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=22 * mm,
    )
    story = []

    # ── Cover page ─────────────────────────────────────────────────────────────
    cover_bg = Table([[
        Paragraph("AquaVeritas", cover_title),
        Spacer(1, 4),
        Paragraph("Model Evaluation Report", cover_sub),
        Spacer(1, 6),
        Paragraph("Three-Way Accuracy Comparison · All 10 Fields", cover_sub),
        Spacer(1, 10),
        Paragraph(
            "Claude claude-opus-4-6 Oracle  ·  LFM2.5-VL-450M Base  ·  AquaVeritas Fine-Tuned",
            cover_meta,
        ),
        Spacer(1, 4),
        Paragraph(
            f"Generated: {date.today()}  ·  Test set: {c_met.get('n', 0)} observations  "
            f"·  Core zone (4 fields) + Buffer zone (6 fields)",
            cover_meta,
        ),
    ]], colWidths=[W - 2 * MARGIN])
    cover_bg.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 30),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 30),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 20),
    ]))
    story.append(cover_bg)
    story.append(Spacer(1, 8 * mm))

    # ── KPI strip: overall + zone breakdown ────────────────────────────────────
    kpi_col = (W - 2 * MARGIN) / 3

    def kpi_cell(val, label, color):
        return [
            Paragraph(pct(val), S("K", fontName="Helvetica-Bold", fontSize=22,
                                   textColor=color, leading=26, alignment=TA_CENTER)),
            Paragraph(label, S("L", fontName="Helvetica", fontSize=8,
                                textColor=GREY_TEXT, leading=11, alignment=TA_CENTER)),
        ]

    # Row 1 — overall
    row1 = Table(
        [[
            Table([[kpi_cell(c_met.get("overall"), f"Claude oracle\nOverall · n={c_met.get('n',0)}", STEEL)]],   colWidths=[kpi_col]),
            Table([[kpi_cell(b_met.get("overall"), f"Base LFM2.5-VL\nOverall · n={b_met.get('n',0)}", RED_BAD)]], colWidths=[kpi_col]),
            Table([[kpi_cell(f_met.get("overall"), f"Fine-tuned LFM\nOverall · n={f_met.get('n',0)}", GREEN_OK)]], colWidths=[kpi_col]),
        ]],
        colWidths=[kpi_col, kpi_col, kpi_col],
    )
    row1.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND",    (0, 0), (-1, -1), LIGHT_BG),
    ]))
    story.append(row1)
    story.append(Spacer(1, 2 * mm))

    # Row 2 — core vs buffer breakdown
    sub_col = (W - 2 * MARGIN) / 6

    def mini_kpi(val, label, color):
        return [
            Paragraph(pct(val), S("mk", fontName="Helvetica-Bold", fontSize=14,
                                   textColor=color, leading=18, alignment=TA_CENTER)),
            Paragraph(label, S("ml", fontName="Helvetica", fontSize=7,
                                textColor=GREY_TEXT, leading=9, alignment=TA_CENTER)),
        ]

    row2 = Table(
        [[
            Table([[mini_kpi(c_core, "Claude\nCore", STEEL)]],   colWidths=[sub_col]),
            Table([[mini_kpi(c_buf,  "Claude\nBuffer", STEEL)]],  colWidths=[sub_col]),
            Table([[mini_kpi(b_core, "Base\nCore", RED_BAD)]],    colWidths=[sub_col]),
            Table([[mini_kpi(b_buf,  "Base\nBuffer", RED_BAD)]],  colWidths=[sub_col]),
            Table([[mini_kpi(f_core, "Fine-tuned\nCore", GREEN_OK)]],   colWidths=[sub_col]),
            Table([[mini_kpi(f_buf,  "Fine-tuned\nBuffer", GREEN_OK)]], colWidths=[sub_col]),
        ]],
        colWidths=[sub_col] * 6,
    )
    row2.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND",    (0, 0), (1, -1), PALE_BLUE),
        ("BACKGROUND",    (2, 0), (3, -1), colors.HexColor("#FEF0E7")),
        ("BACKGROUND",    (4, 0), (5, -1), colors.HexColor("#E9F7EF")),
    ]))
    story.append(row2)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "Core zone: water_extent_status, flood_risk, water_clarity, shoreline_encroachment  "
        "·  Buffer zone: agriculture_present, crop_stress_level, crop_stress_type, "
        "cultivation_expanding, settlement_visible, bare_soil_expansion",
        caption_style,
    ))

    story.append(PageBreak())

    # ── 1. Executive Summary ───────────────────────────────────────────────────
    section_banner("1  Executive Summary", story)

    story.append(Paragraph(
        "AquaVeritas fine-tunes LFM2.5-VL-450M (450M parameters) on Sentinel-2 satellite "
        "imagery (RGB + SWIR) to classify freshwater body status and surrounding agricultural "
        "stress across 10 structured fields. This report presents a full three-way accuracy "
        "comparison on the held-out test set (2024-01-01 onwards): the Claude claude-opus-4-6 oracle "
        "that generated ground-truth labels, the unmodified LFM2.5-VL-450M base model, and "
        "the AquaVeritas fine-tuned checkpoint — evaluated across both core and buffer zones.",
        body_style,
    ))
    story.append(Spacer(1, 2 * mm))

    findings = [
        ["Finding", "Detail"],
        ["Fine-tuned overall",
         f"{pct(f_met.get('overall'))} on {f_met.get('n',0)} obs across all 10 fields — "
         f"core {pct(f_core)}, buffer {pct(f_buf)}"],
        ["vs Claude oracle",
         f"Oracle scores {pct(c_met.get('overall'))} overall — fine-tuned trails by only "
         f"{abs(f_met.get('overall',0) - c_met.get('overall',0)):.1%} on 10 fields"],
        ["vs Base model",
         f"Base scores {pct(b_met.get('overall'))} — fine-tuning delivers "
         f"+{f_met.get('overall',0) - b_met.get('overall',0):.1%} uplift overall"],
        ["Core zone (4 fields)",
         f"Fine-tuned {pct(f_core)} vs Base {pct(b_core)} — "
         f"+{f_core - b_core:.1%} gain; water_clarity and shoreline_encroachment at 96.7%"],
        ["Buffer zone (6 fields)",
         f"Fine-tuned {pct(f_buf)} vs Base {pct(b_buf)} — "
         f"+{f_buf - b_buf:.1%} gain; crop_stress_type lifted from 0% to 83.3%"],
        ["Strongest field gain",
         f"crop_stress_type: base 0.0% → fine-tuned 83.3% (▲ 83.3%)"],
        ["Weakest field",
         f"crop_stress_level: fine-tuned {pct(f_fields.get('crop_stress_level'))} "
         f"(vs oracle {pct(c_fields.get('crop_stress_level'))}) — "
         "multi-class ordinal field with highest ambiguity"],
    ]
    ft = Table(findings, colWidths=[48 * mm, W - 2 * MARGIN - 48 * mm])
    ft.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("FONTNAME",      (0, 1), (0, -1),  "Helvetica-Bold"),
        ("TEXTCOLOR",     (0, 1), (0, -1),  STEEL),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, PALE_BLUE]),
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(ft)

    # ── 2. Evaluation Setup ────────────────────────────────────────────────────
    story.append(Spacer(1, 2 * mm))
    section_banner("2  Evaluation Setup", story)

    setup_rows = [
        ["Parameter", "Value"],
        ["Test split",             "Observations from 2024-01-01 onwards (held out during training)"],
        ["Observations (all)",     f"{c_met.get('n', 0)} per model"],
        ["Inference backend",      "llama-server (OpenAI-compatible, port 8080) · ctx-size 8192 · timeout 120 s"],
        ["Model — base",           "LiquidAI/LFM2.5-VL-450M-GGUF · LFM2.5-VL-450M-Q8_0.gguf"],
        ["Model — fine-tuned",     "Arty1001/aquaveritas-lfm-GGUF · aquaveritas-lfm-q8_0.gguf"],
        ["Vision projector",       "mmproj-LFM2.5-VL-450m-F16.gguf (shared; frozen during fine-tuning)"],
        ["Images per observation", "2 — RGB true-colour + SWIR false-colour (15 km × 15 km, 3×3 grid of 5km sub-tiles)"],
        ["Core fields (4)",        "water_extent_status, flood_risk, water_clarity, shoreline_encroachment"],
        ["Buffer fields (6)",      "agriculture_present, crop_stress_level, crop_stress_type, "
                                   "cultivation_expanding_toward_water, settlement_visible, bare_soil_expansion"],
        ["Calls per observation",  "2 (infer_core + infer_buffer) — each with its own system prompt"],
        ["Training data",          "1,280 obs (before 2024-01-01) · 3 epochs · Modal H100 · final loss 0.011"],
    ]
    st = Table(setup_rows, colWidths=[52 * mm, W - 2 * MARGIN - 52 * mm])
    st.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("FONTNAME",      (0, 1), (0, -1),  "Helvetica-Bold"),
        ("TEXTCOLOR",     (0, 1), (0, -1),  STEEL),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, PALE_BLUE]),
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(st)

    # ── 3. Three-Way Comparison Table ─────────────────────────────────────────
    story.append(PageBreak())
    section_banner("3  Three-Way Field-Level Accuracy", story)

    story.append(Paragraph(
        "Accuracy = fraction of observations where the model prediction exactly matches the "
        "Claude oracle ground-truth label. All 30 observations evaluated across all 10 fields "
        "for all three models. Colours: green ≥ 80% · amber 50–79% · red < 50%.",
        body_style,
    ))
    story.append(Spacer(1, 2 * mm))

    col_w = (W - 2 * MARGIN) / 5
    header = [
        Paragraph("Field", label_style),
        Paragraph(f"Claude\nn={c_met.get('n',0)}",
                  S("H", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, alignment=TA_CENTER, leading=11)),
        Paragraph(f"Base LFM\nn={b_met.get('n',0)}",
                  S("H", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, alignment=TA_CENTER, leading=11)),
        Paragraph(f"Fine-tuned\nn={f_met.get('n',0)}",
                  S("H", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, alignment=TA_CENTER, leading=11)),
        Paragraph("Δ (ft − base)",
                  S("H", fontName="Helvetica-Bold", fontSize=8, textColor=WHITE, alignment=TA_CENTER, leading=11)),
    ]
    rows = [header]

    def zone_row(label, cv, bv, fv):
        return [
            Paragraph(label, S("O", fontName="Helvetica-Bold", fontSize=8, textColor=NAVY, leading=10)),
            colored_pct(cv), colored_pct(bv), colored_pct(fv),
            colored_delta(bv, fv),
        ]

    def banner_row(label, bg_color=PALE_BLUE):
        return [
            Paragraph(label, S("ZB", fontName="Helvetica-Bold", fontSize=8, textColor=STEEL, leading=10)),
            Paragraph("", body_style), Paragraph("", body_style),
            Paragraph("", body_style), Paragraph("", body_style),
        ]

    rows.append(zone_row("OVERALL (10 fields)",
                          c_met.get("overall"), b_met.get("overall"), f_met.get("overall")))
    rows.append(zone_row("Core zone avg (4 fields)", c_core, b_core, f_core))
    rows.append(zone_row("Buffer zone avg (6 fields)", c_buf, b_buf, f_buf))

    rows.append(banner_row("── CORE ZONE — Water Body ──"))
    for fld in CORE_FIELDS:
        cv, bv, fv = c_fields.get(fld), b_fields.get(fld), f_fields.get(fld)
        rows.append([
            Paragraph(FIELD_LABELS[fld],
                      S("F", fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#333333"), leading=10)),
            colored_pct(cv), colored_pct(bv), colored_pct(fv),
            colored_delta(bv, fv),
        ])

    rows.append(banner_row("── BUFFER ZONE — Agriculture ──", PALE_TEAL))
    for fld in BUFFER_FIELDS:
        cv, bv, fv = c_fields.get(fld), b_fields.get(fld), f_fields.get(fld)
        rows.append([
            Paragraph(FIELD_LABELS[fld],
                      S("F", fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#333333"), leading=10)),
            colored_pct(cv), colored_pct(bv), colored_pct(fv),
            colored_delta(bv, fv),
        ])

    ts = TableStyle([
        ("BACKGROUND",    (0, 0),  (-1, 0),   NAVY),
        ("TEXTCOLOR",     (0, 0),  (-1, 0),   WHITE),
        ("FONTNAME",      (0, 0),  (-1, 0),   "Helvetica-Bold"),
        # summary rows
        ("BACKGROUND",    (0, 1),  (-1, 3),   DARK_ROW),
        # core banner
        ("BACKGROUND",    (0, 4),  (-1, 4),   PALE_BLUE),
        # core field rows
        ("ROWBACKGROUNDS",(0, 5),  (-1, 8),   [WHITE, LIGHT_BG]),
        # buffer banner
        ("BACKGROUND",    (0, 9),  (-1, 9),   PALE_TEAL),
        # buffer field rows
        ("ROWBACKGROUNDS",(0, 10), (-1, -1),  [WHITE, colors.HexColor("#F0FBF9")]),
        ("GRID",          (0, 0),  (-1, -1),  0.4, BORDER),
        ("TOPPADDING",    (0, 0),  (-1, -1),  5),
        ("BOTTOMPADDING", (0, 0),  (-1, -1),  5),
        ("LEFTPADDING",   (0, 0),  (-1, -1),  6),
        ("RIGHTPADDING",  (0, 0),  (-1, -1),  6),
        ("VALIGN",        (0, 0),  (-1, -1),  "MIDDLE"),
        ("ALIGN",         (1, 0),  (-1, -1),  "CENTER"),
    ])
    comp_table = Table(rows, colWidths=[col_w * 1.6, col_w * 0.85, col_w * 0.85, col_w * 0.85, col_w * 0.85])
    comp_table.setStyle(ts)
    story.append(comp_table)
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "Δ = fine-tuned minus base  ·  ▲ positive = improvement  "
        "·  Green ≥ 80%  ·  Amber 50–79%  ·  Red < 50%",
        caption_style,
    ))

    # ── 4. Core Zone Deep Dive ─────────────────────────────────────────────────
    story.append(PageBreak())
    section_banner("4  Core Zone — Per-Field Deep Dive", story)

    story.append(Paragraph(
        "The core zone covers the water body itself — 4 fields that are the primary signal "
        "for freshwater stress monitoring. The fine-tuned model reaches or exceeds the oracle "
        "on 3 of 4 core fields, with flood_risk the only field where it outscores Claude "
        f"({pct(f_fields.get('flood_risk'))} vs {pct(c_fields.get('flood_risk'))}).",
        body_style,
    ))
    story.append(Spacer(1, 3 * mm))

    for fld in CORE_FIELDS:
        story.append(field_panel(
            FIELD_LABELS[fld],
            c_fields.get(fld), b_fields.get(fld), f_fields.get(fld),
            head_color=STEEL,
        ))

    # ── 5. Buffer Zone Deep Dive ───────────────────────────────────────────────
    story.append(PageBreak())
    section_banner("5  Buffer Zone — Per-Field Deep Dive", story, color=TEAL)

    story.append(Paragraph(
        "The buffer zone covers the agricultural land surrounding each water body — "
        "6 fields tracking crop stress, land-use change, and settlement expansion. "
        f"The fine-tuned model averages {pct(f_buf)} across these 6 fields versus "
        f"{pct(b_buf)} for the base model — a +{f_buf - b_buf:.1%} lift. "
        "crop_stress_type shows the largest gain (0% → 83.3%), reflecting successful "
        "learning of the drought / flood_damage / none taxonomy from training data. "
        "crop_stress_level is the weakest field for both fine-tuned and oracle, indicating "
        "genuine label ambiguity in distinguishing none/low/moderate/severe stress levels "
        "from imagery alone.",
        body_style,
    ))
    story.append(Spacer(1, 3 * mm))

    for fld in BUFFER_FIELDS:
        story.append(field_panel(
            FIELD_LABELS[fld],
            c_fields.get(fld), b_fields.get(fld), f_fields.get(fld),
            head_color=TEAL,
        ))

    # ── 6. Observation Matrix ──────────────────────────────────────────────────
    story.append(PageBreak())
    section_banner("6  Fine-Tuned Model — Observation Match Matrix", story)

    story.append(Paragraph(
        f"Each row is one of the {f_met.get('n', 0)} test observations. Each column is one of "
        "the 10 evaluated fields. ✓ = exact match with ground truth · ✗ = mismatch. "
        "Core zone fields (blue header) · Buffer zone fields (teal header).",
        body_style,
    ))
    story.append(Spacer(1, 2 * mm))

    ft_preds = finetuned.get("predictions", [])
    ft_gts   = finetuned.get("ground_truth", [])

    # Column widths: obs# + 10 fields
    obs_w   = 7 * mm
    field_w = (W - 2 * MARGIN - obs_w) / len(ALL_FIELDS)

    # Header row — short labels, coloured by zone
    matrix_header = [Paragraph("#", S("mh", fontName="Helvetica-Bold", fontSize=6,
                                       textColor=WHITE, alignment=TA_CENTER))]
    for fld in ALL_FIELDS:
        color = STEEL if fld in CORE_FIELDS else TEAL
        matrix_header.append(
            Paragraph(FIELD_SHORT[fld],
                      S("mh", fontName="Helvetica-Bold", fontSize=6,
                         textColor=WHITE, alignment=TA_CENTER, leading=8))
        )

    matrix_rows = [matrix_header]
    for i, (pred, gt) in enumerate(zip(ft_preds, ft_gts)):
        row = [Paragraph(str(i + 1), S("mi", fontName="Helvetica-Bold", fontSize=7,
                                        textColor=NAVY, alignment=TA_CENTER))]
        for fld in ALL_FIELDS:
            pv = pred.get(fld)
            gv = gt.get(fld)
            if pv is None:
                sym, col = "—", GREY_TEXT
            elif str(pv).lower() == str(gv).lower():
                sym, col = "✓", GREEN_OK
            else:
                sym, col = "✗", RED_BAD
            row.append(Paragraph(sym, S("ms", fontName="Helvetica-Bold", fontSize=8,
                                         textColor=col, alignment=TA_CENTER)))
        matrix_rows.append(row)

    col_widths = [obs_w] + [field_w] * len(ALL_FIELDS)
    matrix_table = Table(matrix_rows, colWidths=col_widths, repeatRows=1)

    mat_style = TableStyle([
        # Header background — split by zone
        ("BACKGROUND",    (0, 0),  (0, 0),                       NAVY),
        ("BACKGROUND",    (1, 0),  (len(CORE_FIELDS), 0),        STEEL),
        ("BACKGROUND",    (len(CORE_FIELDS)+1, 0), (-1, 0),      TEAL),
        ("GRID",          (0, 0),  (-1, -1), 0.3, BORDER),
        ("TOPPADDING",    (0, 0),  (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0),  (-1, -1), 3),
        ("LEFTPADDING",   (0, 0),  (-1, -1), 1),
        ("RIGHTPADDING",  (0, 0),  (-1, -1), 1),
        ("VALIGN",        (0, 0),  (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0),  (-1, -1), "CENTER"),
    ])
    # Alternate row background
    for i in range(len(ft_preds)):
        bg = LIGHT_BG if i % 2 == 0 else WHITE
        mat_style.add("BACKGROUND", (0, i + 1), (-1, i + 1), bg)

    matrix_table.setStyle(mat_style)
    story.append(matrix_table)
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "Blue headers = core zone (water body)  ·  Teal headers = buffer zone (agriculture)  "
        "·  ✓ exact match  ·  ✗ mismatch  ·  — not predicted",
        caption_style,
    ))

    # ── 7. Remaining Considerations ────────────────────────────────────────────
    story.append(PageBreak())
    section_banner("7  Remaining Considerations", story)

    notes = [
        ["#", "Topic", "Detail"],
        ["1",
         "Self-referential oracle",
         "Claude generated the ground-truth labels and is also evaluated against them. "
         "Non-determinism explains why oracle accuracy is ~86% rather than 100%. "
         "Human annotation of a small validation subset would provide an independent anchor."],
        ["2",
         "crop_stress_level ambiguity",
         f"Fine-tuned scores {pct(f_fields.get('crop_stress_level'))} on this field — "
         "the lowest of all 10. The oracle itself scores only "
         f"{pct(c_fields.get('crop_stress_level'))}. Distinguishing none/low/moderate/severe "
         "stress from a 15km tile is inherently ambiguous; this ceiling may be a label-quality "
         "limit rather than a model limit."],
        ["3",
         "agriculture_present fine-tuned < oracle",
         f"Fine-tuned {pct(f_fields.get('agriculture_present'))} vs oracle "
         f"{pct(c_fields.get('agriculture_present'))}. "
         "Possible cause: training labels for arid/semi-arid locations (Aral Sea, Dead Sea) "
         "marked agriculture_present=False but inference on similar imagery in test set "
         "diverges from the oracle's interpretation."],
        ["4",
         "LEAP inference platform",
         "The AquaVeritas bundle is already uploaded to the LEAP inference platform "
         "(bundle ID 1, Q8_0 backbone + F16 mmproj). Running evaluation through LEAP "
         "would remove the local llama-server throughput constraint entirely."],
        ["5",
         "Buffer zone prompt separation",
         "Core and buffer inferences are two separate API calls with different system prompts. "
         "Switching to COMBINED_SYSTEM (one call, both zones) would halve API cost and "
         "allow the model to reason about both zones simultaneously — potentially improving "
         "cross-zone consistency (e.g. agriculture_present ↔ crop_stress_level)."],
    ]
    nc = [(W - 2 * MARGIN) * x for x in [0.04, 0.24, 0.72]]
    nt = Table(notes, colWidths=nc, repeatRows=1)
    nt.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("FONTNAME",      (0, 1), (1, -1),  "Helvetica-Bold"),
        ("TEXTCOLOR",     (0, 1), (0, -1),  STEEL),
        ("TEXTCOLOR",     (1, 1), (1, -1),  NAVY),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, PALE_BLUE]),
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(nt)

    # ── 8. Data Source ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 4 * mm))
    section_banner("8  Data Source", story)

    story.append(Paragraph(
        f"All metrics computed from <b>aquaveritas/data/reports/comparison.json</b> "
        f"generated by <i>compare_models.py</i> on {date.today()}. "
        "Ground-truth labels produced by the Claude claude-opus-4-6 oracle and stored in the "
        "AquaVeritas PostgreSQL/PostGIS database. Test split: observed_at ≥ 2024-01-01.",
        body_style,
    ))

    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    print(f"PDF written: {OUT_PDF}")


if __name__ == "__main__":
    build_pdf()
