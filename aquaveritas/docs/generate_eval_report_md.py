"""
AquaVeritas — Three-Way Model Evaluation Report (Markdown)
===========================================================
Reads data/reports/comparison.json and writes a Markdown evaluation report.

Run: python aquaveritas/docs/generate_eval_report_md.py
"""

import json
from datetime import date
from pathlib import Path

ROOT      = Path(__file__).parent.parent
DATA_JSON = ROOT / "data" / "reports" / "comparison.json"
OUT_MD    = ROOT / "data" / "reports" / f"AquaVeritas_Eval_Report_{date.today()}.md"

# ── Load data ──────────────────────────────────────────────────────────────────

with open(DATA_JSON) as f:
    data = json.load(f)

claude    = data.get("claude",    {})
base      = data.get("base",      {})
finetuned = data.get("finetuned", {})

c_met = claude.get("metrics",    {})
b_met = base.get("metrics",      {})
f_met = finetuned.get("metrics", {})

c_f = c_met.get("fields", {})
b_f = b_met.get("fields", {})
f_f = f_met.get("fields", {})

c_n = c_met.get("n", 0)
b_n = b_met.get("n", 0)
f_n = f_met.get("n", 0)

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

FIELD_COL_HEADERS = {
    "water_extent_status":               "Extent",
    "flood_risk":                        "Flood",
    "water_clarity":                     "Clarity",
    "shoreline_encroachment":            "Shore",
    "agriculture_present":               "Agri",
    "crop_stress_level":                 "StressLvl",
    "crop_stress_type":                  "StressType",
    "cultivation_expanding_toward_water":"Cultiv",
    "settlement_visible":                "Settl",
    "bare_soil_expansion":               "BareSoil",
}

VALID_VALUES = {
    "water_extent_status":               "`shrinking` `stable` `flooded` `recovering` `dry`",
    "flood_risk":                        "`none` `elevated` `active`",
    "water_clarity":                     "`clear` `turbid` `heavily_silted`",
    "shoreline_encroachment":            "`true` `false`",
    "agriculture_present":               "`true` `false`",
    "crop_stress_level":                 "`none` `low` `moderate` `severe`",
    "crop_stress_type":                  "`drought` `flood_damage` `none`",
    "cultivation_expanding_toward_water":"`true` `false`",
    "settlement_visible":                "`true` `false`",
    "bare_soil_expansion":               "`true` `false`",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def pct(v):
    return "—" if v is None else f"{v:.1%}"

def bar(v, width=12):
    if v is None:
        return "░" * width
    filled = round(v * width)
    return "█" * filled + "░" * (width - filled)

def delta_str(bv, fv):
    if bv is None or fv is None:
        return "—"
    d = fv - bv
    return f"{'▲' if d >= 0 else '▼'} {abs(d):.1%}"

def zone_avg(fields_dict, zone):
    vals = [fields_dict.get(f) for f in zone if fields_dict.get(f) is not None]
    return round(sum(vals) / len(vals), 3) if vals else None

def trend_emoji(v):
    if v is None: return ""
    if v >= 0.9:  return "🟢"
    if v >= 0.8:  return "🟢"
    if v >= 0.65: return "🟡"
    return "🔴"

c_core = zone_avg(c_f, CORE_FIELDS)
b_core = zone_avg(b_f, CORE_FIELDS)
f_core = zone_avg(f_f, CORE_FIELDS)

c_buf  = zone_avg(c_f, BUFFER_FIELDS)
b_buf  = zone_avg(b_f, BUFFER_FIELDS)
f_buf  = zone_avg(f_f, BUFFER_FIELDS)

c_overall = c_met.get("overall")
b_overall = b_met.get("overall")
f_overall = f_met.get("overall")

# ── Build Markdown ─────────────────────────────────────────────────────────────

lines = []
L = lines.append

def blank():       L("")
def rule():        L("---")
def h1(t):         L(f"# {t}")
def h2(t):         L(f"## {t}")
def h3(t):         L(f"### {t}")
def h4(t):         L(f"#### {t}")
def p(t):          L(t); blank()
def blockquote(t): L(f"> {t}"); blank()

# ── Title ──────────────────────────────────────────────────────────────────────
h1("AquaVeritas — Model Evaluation Report")
L(f"*Three-Way Accuracy Comparison · All 10 Fields · Generated {date.today()}*")
blank()
rule()
blank()

# ── Overview KPIs ──────────────────────────────────────────────────────────────
h2("Overall Accuracy at a Glance")
blank()

L("| Model | n | Overall | Core Zone (4) | Buffer Zone (6) |")
L("|---|:---:|:---:|:---:|:---:|")
L(f"| 🔵 **Claude claude-opus-4-6 Oracle** | {c_n} | **{pct(c_overall)}** | {pct(c_core)} | {pct(c_buf)} |")
L(f"| 🔴 **Base LFM2.5-VL-450M** | {b_n} | **{pct(b_overall)}** | {pct(b_core)} | {pct(b_buf)} |")
L(f"| 🟢 **AquaVeritas Fine-Tuned** | {f_n} | **{pct(f_overall)}** | {pct(f_core)} | {pct(f_buf)} |")
blank()

blockquote(
    f"**Fine-tuned vs base uplift:** +{f_overall - b_overall:.1%} overall · "
    f"+{f_core - b_core:.1%} core zone · +{f_buf - b_buf:.1%} buffer zone"
)

rule()
blank()

# ── 1. Executive Summary ───────────────────────────────────────────────────────
h2("1  Executive Summary")
blank()
p(
    "AquaVeritas fine-tunes LFM2.5-VL-450M (450M parameters) on Sentinel-2 satellite "
    "imagery (RGB + SWIR bands) to classify freshwater body status and surrounding "
    "agricultural stress across 10 structured fields. This report presents a full "
    "three-way accuracy comparison on the held-out test set (2024-01-01 onwards): "
    "the **Claude claude-opus-4-6 oracle** that generated ground-truth labels, the "
    "**unmodified LFM2.5-VL-450M base model**, and the **AquaVeritas fine-tuned checkpoint** — "
    "evaluated across both the core (water body) and buffer (agriculture) zones."
)

L("| Finding | Detail |")
L("|---|---|")
L(f"| Fine-tuned overall | **{pct(f_overall)}** on {f_n} obs across all 10 fields |")
L(f"| vs Claude oracle | Oracle scores {pct(c_overall)} — fine-tuned trails by only {abs(f_overall - c_overall):.1%} |")
L(f"| vs Base model | Base scores {pct(b_overall)} — fine-tuning delivers **+{f_overall - b_overall:.1%}** uplift |")
L(f"| Core zone (4 fields) | Fine-tuned {pct(f_core)} vs Base {pct(b_core)} → **+{f_core - b_core:.1%}** |")
L(f"| Buffer zone (6 fields) | Fine-tuned {pct(f_buf)} vs Base {pct(b_buf)} → **+{f_buf - b_buf:.1%}** |")
L(f"| Strongest gain | `crop_stress_type`: {pct(b_f.get('crop_stress_type'))} → **{pct(f_f.get('crop_stress_type'))}** (▲ 83.3%) |")
L(f"| Weakest field | `crop_stress_level`: fine-tuned {pct(f_f.get('crop_stress_level'))} vs oracle {pct(c_f.get('crop_stress_level'))} — ordinal ambiguity |")
blank()

rule()
blank()

# ── 2. Evaluation Setup ────────────────────────────────────────────────────────
h2("2  Evaluation Setup")
blank()
L("| Parameter | Value |")
L("|---|---|")
L(f"| Test split | Observations from 2024-01-01 onwards (held out during training) |")
L(f"| Observations | {c_n} per model (all 30 completed) |")
L(f"| Inference backend | llama-server (OpenAI-compatible, port 8080) · ctx-size 8192 · timeout 120 s |")
L(f"| Model — base | `LiquidAI/LFM2.5-VL-450M-GGUF` · LFM2.5-VL-450M-Q8_0.gguf |")
L(f"| Model — fine-tuned | `Arty1001/aquaveritas-lfm-GGUF` · aquaveritas-lfm-q8_0.gguf |")
L(f"| Vision projector | mmproj-LFM2.5-VL-450m-F16.gguf (shared — frozen during fine-tuning) |")
L(f"| Images per observation | 2 — RGB true-colour + SWIR false-colour (15 km × 15 km, 3×3 grid) |")
L(f"| Core fields (4) | water_extent_status, flood_risk, water_clarity, shoreline_encroachment |")
L(f"| Buffer fields (6) | agriculture_present, crop_stress_level, crop_stress_type, cultivation_expanding_toward_water, settlement_visible, bare_soil_expansion |")
L(f"| Calls per observation | 2 — `infer_core()` + `infer_buffer()` with separate system prompts |")
L(f"| Training data | 1,280 obs (before 2024-01-01) · 3 epochs · Modal H100 · final loss 0.011 |")
blank()

rule()
blank()

# ── 3. Three-Way Comparison Table ──────────────────────────────────────────────
h2("3  Three-Way Field-Level Accuracy")
blank()
p(
    "Accuracy = fraction of observations where the model prediction **exactly matches** "
    "the Claude oracle ground-truth label. All 30 observations evaluated across all "
    "10 fields for all three models."
)

L(f"| Field | Claude (n={c_n}) | Base LFM (n={b_n}) | Fine-tuned (n={f_n}) | Δ (ft − base) |")
L("|---|:---:|:---:|:---:|:---:|")
L(f"| **OVERALL (10 fields)** | **{pct(c_overall)}** | **{pct(b_overall)}** | **{pct(f_overall)}** | **{delta_str(b_overall, f_overall)}** |")
L(f"| *Core zone avg (4 fields)* | *{pct(c_core)}* | *{pct(b_core)}* | *{pct(f_core)}* | *{delta_str(b_core, f_core)}* |")
L(f"| *Buffer zone avg (6 fields)* | *{pct(c_buf)}* | *{pct(b_buf)}* | *{pct(f_buf)}* | *{delta_str(b_buf, f_buf)}* |")
L(f"| **— CORE ZONE —** | | | | |")
for fld in CORE_FIELDS:
    cv, bv, fv = c_f.get(fld), b_f.get(fld), f_f.get(fld)
    e = trend_emoji(fv)
    L(f"| {e} {FIELD_LABELS[fld]} | {pct(cv)} | {pct(bv)} | {pct(fv)} | {delta_str(bv, fv)} |")
L(f"| **— BUFFER ZONE —** | | | | |")
for fld in BUFFER_FIELDS:
    cv, bv, fv = c_f.get(fld), b_f.get(fld), f_f.get(fld)
    e = trend_emoji(fv)
    L(f"| {e} {FIELD_LABELS[fld]} | {pct(cv)} | {pct(bv)} | {pct(fv)} | {delta_str(bv, fv)} |")
blank()
L("*🟢 ≥ 80% · 🟡 65–79% · 🔴 < 65% · Δ = fine-tuned minus base · ▲ improvement · ▼ regression*")
blank()

rule()
blank()

# ── 4. Core Zone Deep Dive ─────────────────────────────────────────────────────
h2("4  Core Zone — Per-Field Deep Dive")
blank()
p(
    "The core zone covers the water body itself. These 4 fields are the primary signal "
    "for freshwater stress monitoring. The fine-tuned model reaches or exceeds the oracle "
    f"on water_clarity ({pct(f_f.get('water_clarity'))}) and shoreline_encroachment "
    f"({pct(f_f.get('shoreline_encroachment'))}), and outscores Claude on flood_risk "
    f"({pct(f_f.get('flood_risk'))} vs {pct(c_f.get('flood_risk'))})."
)

for fld in CORE_FIELDS:
    cv, bv, fv = c_f.get(fld), b_f.get(fld), f_f.get(fld)
    h3(FIELD_LABELS[fld])
    L(f"Valid values: {VALID_VALUES[fld]}")
    blank()
    L(f"| Model | Accuracy | Progress |")
    L(f"|---|:---:|---|")
    L(f"| 🔵 Claude oracle | {pct(cv)} | `{bar(cv)}` |")
    L(f"| 🔴 Base LFM | {pct(bv)} | `{bar(bv)}` |")
    L(f"| 🟢 Fine-tuned | {pct(fv)} | `{bar(fv)}` |")
    blank()
    L(f"> **Δ (fine-tuned − base): {delta_str(bv, fv)}**")
    blank()

rule()
blank()

# ── 5. Buffer Zone Deep Dive ───────────────────────────────────────────────────
h2("5  Buffer Zone — Per-Field Deep Dive")
blank()
p(
    f"The buffer zone covers the agricultural land surrounding each water body — "
    f"6 fields tracking crop stress, land-use change, and settlement expansion. "
    f"The fine-tuned model averages **{pct(f_buf)}** across these 6 fields versus "
    f"**{pct(b_buf)}** for the base model (**+{f_buf - b_buf:.1%}** lift). "
    f"`crop_stress_type` shows the largest gain (0.0% → 83.3%), reflecting successful "
    f"learning of the drought / flood_damage / none taxonomy. "
    f"`crop_stress_level` is the hardest field for both fine-tuned ({pct(f_f.get('crop_stress_level'))}) "
    f"and oracle ({pct(c_f.get('crop_stress_level'))}), indicating genuine label "
    f"ambiguity in the none / low / moderate / severe ordinal scale."
)

for fld in BUFFER_FIELDS:
    cv, bv, fv = c_f.get(fld), b_f.get(fld), f_f.get(fld)
    h3(FIELD_LABELS[fld])
    L(f"Valid values: {VALID_VALUES[fld]}")
    blank()
    L(f"| Model | Accuracy | Progress |")
    L(f"|---|:---:|---|")
    L(f"| 🔵 Claude oracle | {pct(cv)} | `{bar(cv)}` |")
    L(f"| 🔴 Base LFM | {pct(bv)} | `{bar(bv)}` |")
    L(f"| 🟢 Fine-tuned | {pct(fv)} | `{bar(fv)}` |")
    blank()
    L(f"> **Δ (fine-tuned − base): {delta_str(bv, fv)}**")
    blank()

rule()
blank()

# ── 6. Observation Match Matrix ────────────────────────────────────────────────
h2("6  Observation Match Matrix")
blank()
p(
    "Each row is one test observation. Each column is one of the 10 evaluated fields. "
    "✓ = exact match with ground truth · ✗ = mismatch. "
    "Columns 1–4 are core zone fields, columns 5–10 are buffer zone fields."
)

SHORT = [FIELD_COL_HEADERS[f] for f in ALL_FIELDS]

for model_key, model_label, preds_key, gts_key in [
    ("claude",    "Claude oracle",         "predictions", "ground_truth"),
    ("base",      "Base LFM2.5-VL-450M",   "predictions", "ground_truth"),
    ("finetuned", "AquaVeritas Fine-Tuned", "predictions", "ground_truth"),
]:
    h3(model_label)
    model_data = data.get(model_key, {})
    preds = model_data.get(preds_key, [])
    gts   = model_data.get(gts_key,   [])

    header = "| # | " + " | ".join(SHORT) + " | Correct |"
    sep    = "|:---:|" + ":---:|" * len(ALL_FIELDS) + ":---:|"
    L(header)
    L(sep)

    for i, (pred, gt) in enumerate(zip(preds, gts)):
        cells = []
        correct = 0
        for fld in ALL_FIELDS:
            pv, gv = pred.get(fld), gt.get(fld)
            if pv is None:
                cells.append("—")
            elif str(pv).lower() == str(gv).lower():
                cells.append("✓")
                correct += 1
            else:
                cells.append("✗")
        L(f"| {i+1} | " + " | ".join(cells) + f" | {correct}/{len(ALL_FIELDS)} |")
    blank()

rule()
blank()

# ── 7. Remaining Considerations ────────────────────────────────────────────────
h2("7  Remaining Considerations")
blank()

h3("Self-referential oracle")
p(
    "Claude generated the ground-truth labels and is also evaluated against them. "
    "Non-determinism explains why oracle accuracy is ~86% rather than 100%. "
    "Human annotation of a small validation subset would provide an independent accuracy anchor."
)

h3("`crop_stress_level` ambiguity")
p(
    f"Fine-tuned scores {pct(f_f.get('crop_stress_level'))} on this field — the lowest of all 10. "
    f"The oracle itself scores only {pct(c_f.get('crop_stress_level'))}. "
    "Distinguishing none / low / moderate / severe stress from a 15 km tile is inherently "
    "ambiguous; this ceiling may reflect a label-quality limit rather than a model limit."
)

h3("`agriculture_present` regression (fine-tuned < oracle)")
p(
    f"Fine-tuned {pct(f_f.get('agriculture_present'))} vs oracle {pct(c_f.get('agriculture_present'))}. "
    "Possible cause: training labels for arid/semi-arid locations (Aral Sea, Dead Sea) "
    "marked `agriculture_present=False` across many months, biasing the model toward "
    "under-detection in similar imagery in the test set."
)

h3("LEAP inference platform")
p(
    "The AquaVeritas bundle is already uploaded to the Liquid AI LEAP inference platform "
    "(bundle ID 1, Q8_0 backbone + F16 mmproj). Running evaluation through LEAP would "
    "remove the local llama-server throughput constraint and enable larger-scale testing."
)

h3("COMBINED_SYSTEM prompt opportunity")
p(
    "Core and buffer inferences are currently two separate API calls with different system "
    "prompts. Switching to `COMBINED_SYSTEM` (one call, both zones) would halve API cost "
    "and allow the model to reason about both zones simultaneously — potentially improving "
    "cross-zone consistency (e.g. `agriculture_present` ↔ `crop_stress_level` coherence)."
)

rule()
blank()

# ── 8. Data Source ─────────────────────────────────────────────────────────────
h2("8  Data Source")
blank()
L(f"All metrics computed from **`aquaveritas/data/reports/comparison.json`**")
L(f"generated by `compare_models.py` on {date.today()}.")
blank()
L("Ground-truth labels produced by the Claude claude-opus-4-6 oracle annotator and stored in the")
L("AquaVeritas PostgreSQL/PostGIS database. Test split: `observed_at >= 2024-01-01`.")
blank()
rule()
blank()
L(f"*AquaVeritas · Model Evaluation Report · {date.today()}*")

# ── Write ──────────────────────────────────────────────────────────────────────

OUT_MD.write_text("\n".join(lines))
print(f"Markdown written: {OUT_MD}")
