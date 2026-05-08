"""
Model Evaluation
-----------------
Runs inference on the test split and computes per-field accuracy.
Supports two backends: Claude oracle (baseline) and local llama-server (fine-tuned).

Usage:
    # Evaluate fine-tuned model (llama-server must be running)
    python scripts/evaluate.py --backend llama

    # Evaluate Claude oracle baseline
    python scripts/evaluate.py --backend claude

    # Save results JSON
    python scripts/evaluate.py --backend llama --output data/reports/eval_llama.json
"""

import argparse
import json
import sys
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aquaveritas.db import Database
from aquaveritas.evaluator import (
    AnthropicBackend, LlamaBackend,
    ALL_FIELDS, CORE_FIELDS, BUFFER_FIELDS,
    compute_accuracy, generate_report,
)
from aquaveritas.locations import LOCATIONS_BY_ID

REPORTS_DIR = Path(__file__).parent.parent / "data" / "reports"


def evaluate(backend, rows: list[dict]) -> tuple[list, list]:
    predictions, ground_truth = [], []

    for row in tqdm(rows, unit="obs"):
        loc = LOCATIONS_BY_ID.get(row["location_id"])
        if loc is None:
            continue

        pred = {}

        # Core zone
        if row.get("rgb_core_path") and row.get("swir_core_path"):
            try:
                rgb  = Path(row["rgb_core_path"]).read_bytes()
                swir = Path(row["swir_core_path"]).read_bytes()
                core_pred = backend.infer_core(rgb, swir, loc) or {}
                pred.update(core_pred)
            except FileNotFoundError:
                pass

        # Buffer zone
        if row.get("rgb_buffer_path") and row.get("swir_buffer_path"):
            try:
                rgb  = Path(row["rgb_buffer_path"]).read_bytes()
                swir = Path(row["swir_buffer_path"]).read_bytes()
                buf_pred = backend.infer_buffer(rgb, swir, loc) or {}
                # cultivation_expanding_toward_water from DB is stored as cultivation_expanding
                if "cultivation_expanding_toward_water" in buf_pred:
                    buf_pred["cultivation_expanding"] = buf_pred["cultivation_expanding_toward_water"]
                pred.update(buf_pred)
            except FileNotFoundError:
                pass

        if not pred:
            continue

        gt = {
            "water_extent_status":              row.get("water_extent_status"),
            "flood_risk":                       row.get("flood_risk"),
            "water_clarity":                    row.get("water_clarity"),
            "shoreline_encroachment":           row.get("shoreline_encroachment"),
            "agriculture_present":              row.get("agriculture_present"),
            "crop_stress_level":                row.get("crop_stress_level"),
            "crop_stress_type":                 row.get("crop_stress_type"),
            "cultivation_expanding_toward_water": row.get("cultivation_expanding"),
            "settlement_visible":               row.get("settlement_visible"),
            "bare_soil_expansion":              row.get("bare_soil_expansion"),
        }
        predictions.append(pred)
        ground_truth.append(gt)

    return predictions, ground_truth


def per_location_accuracy(predictions, ground_truth, rows) -> dict:
    loc_preds = {}
    loc_gts   = {}
    for pred, gt, row in zip(predictions, ground_truth, rows):
        lid = row["location_id"]
        loc_preds.setdefault(lid, []).append(pred)
        loc_gts.setdefault(lid, []).append(gt)

    result = {}
    for lid in loc_preds:
        m = compute_accuracy(loc_preds[lid], loc_gts[lid])
        result[lid] = m["overall"]
    return result


def main():
    parser = argparse.ArgumentParser(description="Evaluate AquaVeritas model")
    parser.add_argument("--backend", choices=["claude", "llama"], default="llama",
                        help="Inference backend (default: llama)")
    parser.add_argument("--output", default=None,
                        help="Path to save results JSON")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max test observations to evaluate")
    args = parser.parse_args()

    db   = Database()
    rows = db.get_labeled(split="test")
    if args.limit:
        rows = rows[:args.limit]

    print(f"Test observations: {len(rows)}")
    if not rows:
        print("No labeled test observations found. Run collect_data.py and label_data.py first.")
        sys.exit(1)

    if args.backend == "claude":
        backend = AnthropicBackend()
        print("Backend: Claude oracle (claude-opus-4-6)")
    else:
        backend = LlamaBackend()
        print(f"Backend: llama-server at {backend.client.base_url}")

    print(f"Evaluating {len(rows)} observations…")
    predictions, ground_truth = evaluate(backend, rows)

    if not predictions:
        print("No valid predictions produced — check image paths and backend connectivity.")
        sys.exit(1)

    metrics      = compute_accuracy(predictions, ground_truth)
    per_loc      = per_location_accuracy(predictions, ground_truth, rows)
    report_text  = generate_report(metrics, backend.name, per_loc)

    print("\n" + report_text)

    # Save outputs
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"report_{args.backend}.md"
    report_path.write_text(report_text)
    print(f"\nReport saved: {report_path}")

    results = {
        "backend":    args.backend,
        "metrics":    metrics,
        "per_location": per_loc,
        "predictions": predictions,
        "ground_truth": ground_truth,
    }
    results_path = args.output or str(REPORTS_DIR / f"results_{args.backend}.json")
    Path(results_path).write_text(json.dumps(results, indent=2, default=str))
    print(f"Results saved: {results_path}")


if __name__ == "__main__":
    main()
