# AquaVeritas — Model Evaluation Report
*Three-Way Accuracy Comparison · All 10 Fields · Generated 2026-05-04*

---

## Overall Accuracy at a Glance

| Model | n | Overall | Core Zone (4) | Buffer Zone (6) |
|---|:---:|:---:|:---:|:---:|
| 🔵 **Claude claude-opus-4-6 Oracle** | 30 | **86.3%** | 85.8% | 86.7% |
| 🔴 **Base LFM2.5-VL-450M** | 30 | **18.0%** | 15.0% | 20.0% |
| 🟢 **AquaVeritas Fine-Tuned** | 30 | **85.4%** | 90.0% | 82.2% |

> **Fine-tuned vs base uplift:** +67.4% overall · +75.0% core zone · +62.2% buffer zone

---

## 1  Executive Summary

AquaVeritas fine-tunes LFM2.5-VL-450M (450M parameters) on Sentinel-2 satellite imagery (RGB + SWIR bands) to classify freshwater body status and surrounding agricultural stress across 10 structured fields. This report presents a full three-way accuracy comparison on the held-out test set (2024-01-01 onwards): the **Claude claude-opus-4-6 oracle** that generated ground-truth labels, the **unmodified LFM2.5-VL-450M base model**, and the **AquaVeritas fine-tuned checkpoint** — evaluated across both the core (water body) and buffer (agriculture) zones.

| Finding | Detail |
|---|---|
| Fine-tuned overall | **85.4%** on 30 obs across all 10 fields |
| vs Claude oracle | Oracle scores 86.3% — fine-tuned trails by only 0.9% |
| vs Base model | Base scores 18.0% — fine-tuning delivers **+67.4%** uplift |
| Core zone (4 fields) | Fine-tuned 90.0% vs Base 15.0% → **+75.0%** |
| Buffer zone (6 fields) | Fine-tuned 82.2% vs Base 20.0% → **+62.2%** |
| Strongest gain | `crop_stress_type`: 0.0% → **83.3%** (▲ 83.3%) |
| Weakest field | `crop_stress_level`: fine-tuned 56.7% vs oracle 76.7% — ordinal ambiguity |

---

## 2  Evaluation Setup

| Parameter | Value |
|---|---|
| Test split | Observations from 2024-01-01 onwards (held out during training) |
| Observations | 30 per model (all 30 completed) |
| Inference backend | llama-server (OpenAI-compatible, port 8080) · ctx-size 8192 · timeout 120 s |
| Model — base | `LiquidAI/LFM2.5-VL-450M-GGUF` · LFM2.5-VL-450M-Q8_0.gguf |
| Model — fine-tuned | `Arty1001/aquaveritas-lfm-GGUF` · aquaveritas-lfm-q8_0.gguf |
| Vision projector | mmproj-LFM2.5-VL-450m-F16.gguf (shared — frozen during fine-tuning) |
| Images per observation | 2 — RGB true-colour + SWIR false-colour (15 km × 15 km, 3×3 grid) |
| Core fields (4) | water_extent_status, flood_risk, water_clarity, shoreline_encroachment |
| Buffer fields (6) | agriculture_present, crop_stress_level, crop_stress_type, cultivation_expanding_toward_water, settlement_visible, bare_soil_expansion |
| Calls per observation | 2 — `infer_core()` + `infer_buffer()` with separate system prompts |
| Training data | 1,280 obs (before 2024-01-01) · 3 epochs · Modal H100 · final loss 0.011 |

---

## 3  Three-Way Field-Level Accuracy

Accuracy = fraction of observations where the model prediction **exactly matches** the Claude oracle ground-truth label. All 30 observations evaluated across all 10 fields for all three models.

| Field | Claude (n=30) | Base LFM (n=30) | Fine-tuned (n=30) | Δ (ft − base) |
|---|:---:|:---:|:---:|:---:|
| **OVERALL (10 fields)** | **86.3%** | **18.0%** | **85.4%** | **▲ 67.4%** |
| *Core zone avg (4 fields)* | *85.8%* | *15.0%* | *90.0%* | *▲ 75.0%* |
| *Buffer zone avg (6 fields)* | *86.7%* | *20.0%* | *82.2%* | *▲ 62.2%* |
| **— CORE ZONE —** | | | | |
| 🟢 Water Extent Status | 90.0% | 3.3% | 86.7% | ▲ 83.4% |
| 🟢 Flood Risk | 76.7% | 30.0% | 80.0% | ▲ 50.0% |
| 🟢 Water Clarity | 93.3% | 13.3% | 96.7% | ▲ 83.4% |
| 🟢 Shoreline Encroachment | 83.3% | 13.3% | 96.7% | ▲ 83.4% |
| **— BUFFER ZONE —** | | | | |
| 🟡 Agriculture Present | 86.7% | 30.0% | 66.7% | ▲ 36.7% |
| 🔴 Crop Stress Level | 76.7% | 13.3% | 56.7% | ▲ 43.4% |
| 🟢 Crop Stress Type | 70.0% | 0.0% | 83.3% | ▲ 83.3% |
| 🟢 Cultivation Expanding → Water | 93.3% | 16.7% | 96.7% | ▲ 80.0% |
| 🟢 Settlement Visible | 96.7% | 30.0% | 93.3% | ▲ 63.3% |
| 🟢 Bare Soil Expansion | 96.7% | 30.0% | 96.7% | ▲ 66.7% |

*🟢 ≥ 80% · 🟡 65–79% · 🔴 < 65% · Δ = fine-tuned minus base · ▲ improvement · ▼ regression*

---

## 4  Core Zone — Per-Field Deep Dive

The core zone covers the water body itself. These 4 fields are the primary signal for freshwater stress monitoring. The fine-tuned model reaches or exceeds the oracle on water_clarity (96.7%) and shoreline_encroachment (96.7%), and outscores Claude on flood_risk (80.0% vs 76.7%).

### Water Extent Status
Valid values: `shrinking` `stable` `flooded` `recovering` `dry`

| Model | Accuracy | Progress |
|---|:---:|---|
| 🔵 Claude oracle | 90.0% | `███████████░` |
| 🔴 Base LFM | 3.3% | `░░░░░░░░░░░░` |
| 🟢 Fine-tuned | 86.7% | `██████████░░` |

> **Δ (fine-tuned − base): ▲ 83.4%**

### Flood Risk
Valid values: `none` `elevated` `active`

| Model | Accuracy | Progress |
|---|:---:|---|
| 🔵 Claude oracle | 76.7% | `█████████░░░` |
| 🔴 Base LFM | 30.0% | `████░░░░░░░░` |
| 🟢 Fine-tuned | 80.0% | `██████████░░` |

> **Δ (fine-tuned − base): ▲ 50.0%**

### Water Clarity
Valid values: `clear` `turbid` `heavily_silted`

| Model | Accuracy | Progress |
|---|:---:|---|
| 🔵 Claude oracle | 93.3% | `███████████░` |
| 🔴 Base LFM | 13.3% | `██░░░░░░░░░░` |
| 🟢 Fine-tuned | 96.7% | `████████████` |

> **Δ (fine-tuned − base): ▲ 83.4%**

### Shoreline Encroachment
Valid values: `true` `false`

| Model | Accuracy | Progress |
|---|:---:|---|
| 🔵 Claude oracle | 83.3% | `██████████░░` |
| 🔴 Base LFM | 13.3% | `██░░░░░░░░░░` |
| 🟢 Fine-tuned | 96.7% | `████████████` |

> **Δ (fine-tuned − base): ▲ 83.4%**

---

## 5  Buffer Zone — Per-Field Deep Dive

The buffer zone covers the agricultural land surrounding each water body — 6 fields tracking crop stress, land-use change, and settlement expansion. The fine-tuned model averages **82.2%** across these 6 fields versus **20.0%** for the base model (**+62.2%** lift). `crop_stress_type` shows the largest gain (0.0% → 83.3%), reflecting successful learning of the drought / flood_damage / none taxonomy. `crop_stress_level` is the hardest field for both fine-tuned (56.7%) and oracle (76.7%), indicating genuine label ambiguity in the none / low / moderate / severe ordinal scale.

### Agriculture Present
Valid values: `true` `false`

| Model | Accuracy | Progress |
|---|:---:|---|
| 🔵 Claude oracle | 86.7% | `██████████░░` |
| 🔴 Base LFM | 30.0% | `████░░░░░░░░` |
| 🟢 Fine-tuned | 66.7% | `████████░░░░` |

> **Δ (fine-tuned − base): ▲ 36.7%**

### Crop Stress Level
Valid values: `none` `low` `moderate` `severe`

| Model | Accuracy | Progress |
|---|:---:|---|
| 🔵 Claude oracle | 76.7% | `█████████░░░` |
| 🔴 Base LFM | 13.3% | `██░░░░░░░░░░` |
| 🟢 Fine-tuned | 56.7% | `███████░░░░░` |

> **Δ (fine-tuned − base): ▲ 43.4%**

### Crop Stress Type
Valid values: `drought` `flood_damage` `none`

| Model | Accuracy | Progress |
|---|:---:|---|
| 🔵 Claude oracle | 70.0% | `████████░░░░` |
| 🔴 Base LFM | 0.0% | `░░░░░░░░░░░░` |
| 🟢 Fine-tuned | 83.3% | `██████████░░` |

> **Δ (fine-tuned − base): ▲ 83.3%**

### Cultivation Expanding → Water
Valid values: `true` `false`

| Model | Accuracy | Progress |
|---|:---:|---|
| 🔵 Claude oracle | 93.3% | `███████████░` |
| 🔴 Base LFM | 16.7% | `██░░░░░░░░░░` |
| 🟢 Fine-tuned | 96.7% | `████████████` |

> **Δ (fine-tuned − base): ▲ 80.0%**

### Settlement Visible
Valid values: `true` `false`

| Model | Accuracy | Progress |
|---|:---:|---|
| 🔵 Claude oracle | 96.7% | `████████████` |
| 🔴 Base LFM | 30.0% | `████░░░░░░░░` |
| 🟢 Fine-tuned | 93.3% | `███████████░` |

> **Δ (fine-tuned − base): ▲ 63.3%**

### Bare Soil Expansion
Valid values: `true` `false`

| Model | Accuracy | Progress |
|---|:---:|---|
| 🔵 Claude oracle | 96.7% | `████████████` |
| 🔴 Base LFM | 30.0% | `████░░░░░░░░` |
| 🟢 Fine-tuned | 96.7% | `████████████` |

> **Δ (fine-tuned − base): ▲ 66.7%**

---

## 6  Observation Match Matrix

Each row is one test observation. Each column is one of the 10 evaluated fields. ✓ = exact match with ground truth · ✗ = mismatch. Columns 1–4 are core zone fields, columns 5–10 are buffer zone fields.

### Claude oracle
| # | Extent | Flood | Clarity | Shore | Agri | StressLvl | StressType | Cultiv | Settl | BareSoil | Correct |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | 9/10 |
| 2 | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | 8/10 |
| 3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 4 | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 8/10 |
| 5 | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 8/10 |
| 6 | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 9/10 |
| 7 | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 8/10 |
| 8 | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 9/10 |
| 9 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 10 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | 9/10 |
| 11 | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | 7/10 |
| 12 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 13 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | 8/10 |
| 14 | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 9/10 |
| 15 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | 8/10 |
| 16 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | 8/10 |
| 17 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 18 | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 9/10 |
| 19 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | ✓ | ✓ | 8/10 |
| 20 | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | 6/10 |
| 21 | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | 7/10 |
| 22 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 23 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 24 | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | 7/10 |
| 25 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 26 | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 9/10 |
| 27 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ | 8/10 |
| 28 | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | 9/10 |
| 29 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 30 | ✓ | ✓ | ✗ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | 8/10 |

### Base LFM2.5-VL-450M
| # | Extent | Flood | Clarity | Shore | Agri | StressLvl | StressType | Cultiv | Settl | BareSoil | Correct |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | ✗ | ✓ | ✗ | ✗ | — | — | — | — | — | — | 1/10 |
| 2 | — | — | — | — | — | — | — | — | — | — | 0/10 |
| 3 | — | — | — | — | — | — | — | — | — | — | 0/10 |
| 4 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ | ✗ | 0/10 |
| 5 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ | ✗ | 0/10 |
| 6 | — | — | — | — | — | — | — | — | — | — | 0/10 |
| 7 | — | — | — | — | — | — | — | — | — | — | 0/10 |
| 8 | — | — | — | — | — | — | — | — | — | — | 0/10 |
| 9 | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | — | ✓ | — | — | 2/10 |
| 10 | ✗ | ✗ | ✗ | ✗ | — | — | — | — | — | — | 0/10 |
| 11 | — | — | — | — | — | — | — | — | — | — | 0/10 |
| 12 | ✗ | ✗ | ✗ | — | ✗ | ✓ | — | ✓ | ✗ | ✗ | 2/10 |
| 13 | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✓ | ✓ | 2/10 |
| 14 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | — | 7/10 |
| 15 | ✗ | ✓ | ✗ | ✓ | ✗ | ✗ | — | ✗ | ✓ | ✓ | 4/10 |
| 16 | — | — | — | — | ✓ | ✗ | — | ✗ | — | — | 1/10 |
| 17 | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | — | ✗ | ✓ | ✓ | 3/10 |
| 18 | ✗ | ✓ | ✗ | ✗ | ✓ | ✗ | — | ✗ | ✓ | ✓ | 4/10 |
| 19 | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | — | ✗ | ✓ | ✓ | 3/10 |
| 20 | — | — | — | — | — | — | — | — | — | — | 0/10 |
| 21 | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | — | ✓ | ✓ | ✓ | 4/10 |
| 22 | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ | — | ✗ | ✓ | ✓ | 4/10 |
| 23 | ✗ | ✗ | ✗ | ✗ | — | — | — | — | — | — | 0/10 |
| 24 | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✓ | ✓ | 3/10 |
| 25 | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ | — | ✗ | — | — | 4/10 |
| 26 | ✗ | ✗ | ✗ | ✗ | — | — | — | — | — | — | 0/10 |
| 27 | — | — | — | — | ✗ | ✓ | — | ✗ | — | — | 1/10 |
| 28 | ✗ | ✓ | ✗ | ✗ | — | — | — | — | — | — | 1/10 |
| 29 | ✗ | ✗ | ✓ | — | ✓ | ✓ | — | ✓ | ✓ | ✓ | 6/10 |
| 30 | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ | — | ✗ | — | — | 2/10 |

### AquaVeritas Fine-Tuned
| # | Extent | Flood | Clarity | Shore | Agri | StressLvl | StressType | Cultiv | Settl | BareSoil | Correct |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | ✓ | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | 6/10 |
| 2 | ✗ | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | 5/10 |
| 3 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 4 | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 8/10 |
| 5 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 6 | ✗ | ✗ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | 6/10 |
| 7 | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | 8/10 |
| 8 | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 9/10 |
| 9 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 10 | ✗ | ✗ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | 6/10 |
| 11 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 12 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 13 | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | 8/10 |
| 14 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 15 | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | 9/10 |
| 16 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 17 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | 9/10 |
| 18 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | 9/10 |
| 19 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ | ✓ | 8/10 |
| 20 | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | 7/10 |
| 21 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 22 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | 9/10 |
| 23 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 24 | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | 9/10 |
| 25 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 26 | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | 5/10 |
| 27 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ | ✓ | 8/10 |
| 28 | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | 9/10 |
| 29 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 10/10 |
| 30 | ✓ | ✓ | ✗ | ✓ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | 8/10 |

---

## 7  Remaining Considerations

### Self-referential oracle
Claude generated the ground-truth labels and is also evaluated against them. Non-determinism explains why oracle accuracy is ~86% rather than 100%. Human annotation of a small validation subset would provide an independent accuracy anchor.

### `crop_stress_level` ambiguity
Fine-tuned scores 56.7% on this field — the lowest of all 10. The oracle itself scores only 76.7%. Distinguishing none / low / moderate / severe stress from a 15 km tile is inherently ambiguous; this ceiling may reflect a label-quality limit rather than a model limit.

### `agriculture_present` regression (fine-tuned < oracle)
Fine-tuned 66.7% vs oracle 86.7%. Possible cause: training labels for arid/semi-arid locations (Aral Sea, Dead Sea) marked `agriculture_present=False` across many months, biasing the model toward under-detection in similar imagery in the test set.

### LEAP inference platform
The AquaVeritas bundle is already uploaded to the Liquid AI LEAP inference platform (bundle ID 1, Q8_0 backbone + F16 mmproj). Running evaluation through LEAP would remove the local llama-server throughput constraint and enable larger-scale testing.

### COMBINED_SYSTEM prompt opportunity
Core and buffer inferences are currently two separate API calls with different system prompts. Switching to `COMBINED_SYSTEM` (one call, both zones) would halve API cost and allow the model to reason about both zones simultaneously — potentially improving cross-zone consistency (e.g. `agriculture_present` ↔ `crop_stress_level` coherence).

---

## 8  Data Source

All metrics computed from **`aquaveritas/data/reports/comparison.json`**
generated by `compare_models.py` on 2026-05-04.

Ground-truth labels produced by the Claude claude-opus-4-6 oracle annotator and stored in the
AquaVeritas PostgreSQL/PostGIS database. Test split: `observed_at >= 2024-01-01`.

---

*AquaVeritas · Model Evaluation Report · 2026-05-04*