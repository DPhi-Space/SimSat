"""Model evaluation — backends, accuracy metrics, report generation."""

import base64
import json
import os
import time
from typing import Optional

import anthropic
from openai import OpenAI

from .annotator import CORE_SYSTEM, BUFFER_SYSTEM, _image_block, _parse_json
from .locations import LOCATIONS_BY_ID

LLAMA_URL   = os.environ.get("LLAMA_SERVER_URL", "http://localhost:8080")
ORACLE_MODEL = "claude-opus-4-6"

CORE_FIELDS   = ["water_extent_status", "flood_risk", "water_clarity", "shoreline_encroachment"]
BUFFER_FIELDS = ["agriculture_present", "crop_stress_level", "crop_stress_type",
                 "cultivation_expanding_toward_water", "settlement_visible", "bare_soil_expansion"]
ALL_FIELDS    = CORE_FIELDS + BUFFER_FIELDS


# ── Backends ───────────────────────────────────────────────────────────────────

class AnthropicBackend:
    """Uses Claude claude-opus-4-6 — the oracle baseline."""
    name = "claude-oracle"

    def __init__(self):
        self.client = anthropic.Anthropic()

    def infer_core(self, rgb_bytes, swir_bytes, location) -> Optional[dict]:
        system = CORE_SYSTEM.format(
            name=location.name, lat=location.lat, lon=location.lon,
            description=location.description,
            expected_water_status=location.expected_water_status,
        )
        return _anthropic_call(self.client, system, rgb_bytes, swir_bytes)

    def infer_buffer(self, rgb_bytes, swir_bytes, location) -> Optional[dict]:
        system = BUFFER_SYSTEM.format(
            name=location.name, lat=location.lat, lon=location.lon,
            description=location.description,
        )
        return _anthropic_call(self.client, system, rgb_bytes, swir_bytes)


class LlamaBackend:
    """Uses local llama-server (OpenAI-compatible) — fine-tuned LFM2.5-VL."""
    name = "lfm-finetuned"

    def __init__(self, base_url: str = LLAMA_URL):
        self.client = OpenAI(base_url=f"{base_url}/v1", api_key="none")

    def infer_core(self, rgb_bytes, swir_bytes, location) -> Optional[dict]:
        system = CORE_SYSTEM.format(
            name=location.name, lat=location.lat, lon=location.lon,
            description=location.description,
            expected_water_status=location.expected_water_status,
        )
        return _llama_call(self.client, system, rgb_bytes, swir_bytes)

    def infer_buffer(self, rgb_bytes, swir_bytes, location) -> Optional[dict]:
        system = BUFFER_SYSTEM.format(
            name=location.name, lat=location.lat, lon=location.lon,
            description=location.description,
        )
        return _llama_call(self.client, system, rgb_bytes, swir_bytes)


# ── Metrics ────────────────────────────────────────────────────────────────────

def compute_accuracy(predictions: list[dict], ground_truth: list[dict]) -> dict:
    """
    Compute per-field and overall accuracy.
    Returns {field: accuracy, "overall": mean_accuracy, "n": count}.
    """
    counts = {f: {"correct": 0, "total": 0} for f in ALL_FIELDS}

    for pred, gt in zip(predictions, ground_truth):
        for field in ALL_FIELDS:
            gt_val   = gt.get(field)
            pred_val = pred.get(field)
            if gt_val is None:
                continue
            counts[field]["total"] += 1
            if str(pred_val).lower() == str(gt_val).lower():
                counts[field]["correct"] += 1

    per_field = {}
    for f, c in counts.items():
        per_field[f] = round(c["correct"] / c["total"], 3) if c["total"] > 0 else None

    valid_scores = [v for v in per_field.values() if v is not None]
    overall      = round(sum(valid_scores) / len(valid_scores), 3) if valid_scores else 0.0

    return {"fields": per_field, "overall": overall, "n": len(predictions)}


def generate_report(metrics: dict, backend_name: str, per_location: dict) -> str:
    lines = [
        f"# AquaVeritas Evaluation Report",
        f"Backend: {backend_name}",
        f"Samples: {metrics['n']}",
        f"",
        f"## Overall Accuracy: {metrics['overall']:.3f}",
        f"",
        f"## Per-Field Accuracy",
        f"",
        f"### Water Body (Core Zone)",
    ]
    for f in CORE_FIELDS:
        v = metrics["fields"].get(f)
        lines.append(f"- {f}: {v:.3f}" if v is not None else f"- {f}: N/A")

    lines += ["", "### Agricultural Buffer Zone"]
    for f in BUFFER_FIELDS:
        v = metrics["fields"].get(f)
        lines.append(f"- {f}: {v:.3f}" if v is not None else f"- {f}: N/A")

    lines += ["", "## Per-Location Accuracy"]
    for loc_id, score in sorted(per_location.items(), key=lambda x: -x[1]):
        lines.append(f"- {loc_id}: {score:.3f}")

    return "\n".join(lines)


# ── Internal call helpers ──────────────────────────────────────────────────────

def _anthropic_call(client, system, rgb_bytes, swir_bytes):
    try:
        msg = client.messages.create(
            model=ORACLE_MODEL, max_tokens=512, system=system,
            messages=[{"role": "user", "content": [
                _image_block(rgb_bytes),
                _image_block(swir_bytes),
                {"type": "text", "text": "Analyse these satellite images and return the JSON assessment."},
            ]}],
        )
        return _parse_json(msg.content[0].text)
    except Exception:
        return None


def _llama_call(client, system, rgb_bytes, swir_bytes):
    rgb_b64  = base64.standard_b64encode(rgb_bytes).decode()
    swir_b64 = base64.standard_b64encode(swir_bytes).decode()
    try:
        resp = client.chat.completions.create(
            model="aquaveritas",
            max_tokens=512,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{rgb_b64}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{swir_b64}"}},
                    {"type": "text",      "text": "Analyse these satellite images and return the JSON assessment."},
                ]},
            ],
        )
        return _parse_json(resp.choices[0].message.content)
    except Exception:
        return None
