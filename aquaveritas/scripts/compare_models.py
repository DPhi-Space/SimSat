"""
AquaVeritas — Three-Way Model Comparison
==========================================
Downloads GGUFs, runs inference on N test observations for three models,
then prints a side-by-side accuracy table:

    Claude oracle  |  LFM2.5-VL-450M base  |  AquaVeritas fine-tuned

Usage:
    python scripts/compare_models.py --limit 30
    python scripts/compare_models.py --limit 30 --skip-claude
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aquaveritas.evaluator import (
    AnthropicBackend, LlamaBackend,
    ALL_FIELDS, CORE_FIELDS, BUFFER_FIELDS,
    compute_accuracy,
)
from aquaveritas.db import Database
from aquaveritas.locations import LOCATIONS_BY_ID

# ── Paths ─────────────────────────────────────────────────────────────────────

MODELS_DIR   = Path(__file__).parent.parent / "data" / "models"
REPORTS_DIR  = Path(__file__).parent.parent / "data" / "reports"

BASE_GGUF     = MODELS_DIR / "LFM2.5-VL-450M-Q8_0.gguf"
BASE_MMPROJ   = MODELS_DIR / "mmproj-LFM2.5-VL-450m-F16.gguf"
FINETUNED_GGUF = MODELS_DIR / "aquaveritas-lfm-q8_0.gguf"

LLAMA_SERVER  = "/opt/homebrew/bin/llama-server"
LLAMA_PORT    = 8080

# ── Download helpers ───────────────────────────────────────────────────────────

def download_gguf(repo: str, filename: str, dest: Path):
    if dest.exists():
        print(f"  ✓ {dest.name} already present ({dest.stat().st_size/1024**2:.0f} MB)")
        return
    print(f"  Downloading {filename} from {repo}…")
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(repo_id=repo, filename=filename, local_dir=str(MODELS_DIR))
    Path(path).rename(dest) if Path(path) != dest else None
    print(f"  ✓ {dest.name} ({dest.stat().st_size/1024**2:.0f} MB)")


def ensure_models():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print("Checking model files…")
    download_gguf("LiquidAI/LFM2.5-VL-450M-GGUF", "LFM2.5-VL-450M-Q8_0.gguf",       BASE_GGUF)
    download_gguf("LiquidAI/LFM2.5-VL-450M-GGUF", "mmproj-LFM2.5-VL-450m-F16.gguf",  BASE_MMPROJ)
    download_gguf("Arty1001/aquaveritas-lfm-GGUF",  "aquaveritas-lfm-q8_0.gguf",       FINETUNED_GGUF)


# ── llama-server lifecycle ─────────────────────────────────────────────────────

def start_llama_server(model_path: Path, mmproj_path: Path = None, port: int = LLAMA_PORT):
    cmd = [
        LLAMA_SERVER,
        "-m",    str(model_path),
        "--port", str(port),
        "--ctx-size", "8192",
        "-ngl",  "99",          # offload all layers to GPU/Metal
        "--host", "127.0.0.1",
        "-np",   "1",
        "--log-disable",
    ]
    if mmproj_path and mmproj_path.exists():
        cmd += ["--mmproj", str(mmproj_path)]

    print(f"  Starting llama-server on port {port}: {model_path.name}")
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,
    )
    # Wait for server to be ready
    import urllib.request, urllib.error
    for _ in range(60):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
            print(f"  ✓ llama-server ready (pid {proc.pid})")
            return proc
        except Exception:
            pass
    raise RuntimeError("llama-server failed to start in 60s")


def stop_llama_server(proc):
    if proc and proc.poll() is None:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=10)
        print("  ✓ llama-server stopped")


# ── Inference ─────────────────────────────────────────────────────────────────

def run_eval(backend, rows: list[dict]) -> tuple[list, list, list]:
    """Returns (predictions, ground_truth, row_meta)."""
    predictions, ground_truth, meta = [], [], []

    for row in tqdm(rows, desc=f"  {backend.name}", unit="obs"):
        loc = LOCATIONS_BY_ID.get(row["location_id"])
        if loc is None:
            continue

        pred = {}

        rgb_path  = row.get("rgb_core_path")
        swir_path = row.get("swir_core_path")
        if rgb_path and swir_path:
            try:
                rgb  = Path(rgb_path).read_bytes()
                swir = Path(swir_path).read_bytes()
                core   = backend.infer_core(rgb, swir, loc)   or {}
                buffer = backend.infer_buffer(rgb, swir, loc) or {}
                pred.update(core)
                pred.update(buffer)
            except FileNotFoundError:
                pass

        if not pred:
            continue

        gt = {
            "water_extent_status":               row.get("water_extent_status"),
            "flood_risk":                        row.get("flood_risk"),
            "water_clarity":                     row.get("water_clarity"),
            "shoreline_encroachment":            row.get("shoreline_encroachment"),
            "agriculture_present":               row.get("agriculture_present"),
            "crop_stress_level":                 row.get("crop_stress_level"),
            "crop_stress_type":                  row.get("crop_stress_type"),
            "cultivation_expanding_toward_water": row.get("cultivation_expanding"),
            "settlement_visible":                row.get("settlement_visible"),
            "bare_soil_expansion":               row.get("bare_soil_expansion"),
        }
        predictions.append(pred)
        ground_truth.append(gt)
        meta.append({"location_id": row["location_id"], "observed_at": str(row["observed_at"])})

    return predictions, ground_truth, meta


# ── Table rendering ────────────────────────────────────────────────────────────

FIELD_LABELS = {
    "water_extent_status":               "Water Extent Status",
    "flood_risk":                        "Flood Risk",
    "water_clarity":                     "Water Clarity",
    "shoreline_encroachment":            "Shoreline Encroachment",
    "agriculture_present":               "Agriculture Present",
    "crop_stress_level":                 "Crop Stress Level",
    "crop_stress_type":                  "Crop Stress Type",
    "cultivation_expanding_toward_water":"Cultivation Expanding",
    "settlement_visible":                "Settlement Visible",
    "bare_soil_expansion":               "Bare Soil Expansion",
}

def fmt(v):
    if v is None:
        return "  —  "
    return f"{v:.1%}"

def delta(base, finetuned):
    if base is None or finetuned is None:
        return ""
    d = finetuned - base
    return f"{'▲' if d >= 0 else '▼'} {abs(d):.1%}"

def print_table(results: dict):
    claude    = results.get("claude", {})
    base      = results.get("base", {})
    finetuned = results.get("finetuned", {})

    c_m = claude.get("metrics", {})
    b_m = base.get("metrics", {})
    f_m = finetuned.get("metrics", {})

    c_f = c_m.get("fields", {})
    b_f = b_m.get("fields", {})
    f_f = f_m.get("fields", {})

    W = 26  # field name column width
    C = 10  # model column width

    sep  = f"+{'-'*(W+2)}+{'-'*(C+2)}+{'-'*(C+2)}+{'-'*(C+2)}+{'-'*10}+"
    head = (f"| {'Field':<{W}} | {'Claude':^{C}} | {'Base LFM':^{C}} | "
            f"{'Fine-tuned':^{C}} | {'Δ (ft-base)':^8} |")

    print()
    print("=" * len(sep))
    print("  AquaVeritas — Model Comparison (field-level accuracy on test set)")
    print("=" * len(sep))
    print(f"  Claude oracle : {c_m.get('n', 0)} observations")
    print(f"  Base model    : {b_m.get('n', 0)} observations  (LFM2.5-VL-450M Q8_0 — no fine-tuning)")
    print(f"  Fine-tuned    : {f_m.get('n', 0)} observations  (AquaVeritas-LFM Q8_0)")
    print()
    print(sep)
    print(head)
    print(sep)

    # Overall row
    print(
        f"| {'OVERALL ACCURACY':<{W}} | {fmt(c_m.get('overall')):^{C}} | "
        f"{fmt(b_m.get('overall')):^{C}} | {fmt(f_m.get('overall')):^{C}} | "
        f"{delta(b_m.get('overall'), f_m.get('overall')):^10} |"
    )
    print(sep)

    # Core zone
    print(f"| {'── CORE ZONE ──':<{W}} | {'':^{C}} | {'':^{C}} | {'':^{C}} | {'':^10} |")
    for field in CORE_FIELDS:
        label = FIELD_LABELS.get(field, field)
        cv = c_f.get(field)
        bv = b_f.get(field)
        fv = f_f.get(field)
        print(
            f"| {label:<{W}} | {fmt(cv):^{C}} | {fmt(bv):^{C}} | {fmt(fv):^{C}} | {delta(bv, fv):^10} |"
        )

    print(sep)

    # Buffer zone
    print(f"| {'── BUFFER ZONE ──':<{W}} | {'':^{C}} | {'':^{C}} | {'':^{C}} | {'':^10} |")
    for field in BUFFER_FIELDS:
        label = FIELD_LABELS.get(field, field)
        cv = c_f.get(field)
        bv = b_f.get(field)
        fv = f_f.get(field)
        print(
            f"| {label:<{W}} | {fmt(cv):^{C}} | {fmt(bv):^{C}} | {fmt(fv):^{C}} | {delta(bv, fv):^10} |"
        )

    print(sep)
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30,
                        help="Number of test observations to evaluate (default: 30)")
    parser.add_argument("--skip-claude", action="store_true",
                        help="Skip Claude oracle (saves API cost)")
    parser.add_argument("--skip-base", action="store_true",
                        help="Skip base model eval")
    parser.add_argument("--skip-finetuned", action="store_true",
                        help="Skip fine-tuned model eval")
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    ensure_models()

    db   = Database()
    rows = db.get_labeled(split="test")
    rows = rows[:args.limit]
    print(f"\nEvaluating on {len(rows)} test observations\n")

    results = {}

    # ── 1. Claude oracle ──────────────────────────────────────────────────────
    if not args.skip_claude:
        print("── Claude oracle (claude-opus-4-6) ──")
        backend = AnthropicBackend()
        preds, gts, meta = run_eval(backend, rows)
        metrics = compute_accuracy(preds, gts)
        results["claude"] = {"metrics": metrics, "predictions": preds, "ground_truth": gts}
        print(f"  Overall accuracy: {metrics['overall']:.1%}  (n={metrics['n']})\n")

    # ── 2. Base model ─────────────────────────────────────────────────────────
    if not args.skip_base:
        print("── Base model (LFM2.5-VL-450M Q8_0, no fine-tuning) ──")
        proc = start_llama_server(BASE_GGUF, BASE_MMPROJ)
        try:
            backend = LlamaBackend(base_url=f"http://127.0.0.1:{LLAMA_PORT}", timeout=120.0)
            backend.name = "lfm-base"
            preds, gts, meta = run_eval(backend, rows)
            metrics = compute_accuracy(preds, gts)
            results["base"] = {"metrics": metrics, "predictions": preds, "ground_truth": gts}
            print(f"  Overall accuracy: {metrics['overall']:.1%}  (n={metrics['n']})\n")
        finally:
            stop_llama_server(proc)

    # ── 3. Fine-tuned model ───────────────────────────────────────────────────
    if not args.skip_finetuned:
        print("── Fine-tuned model (AquaVeritas-LFM Q8_0) ──")
        # Vision encoder unchanged — reuse base mmproj
        proc = start_llama_server(FINETUNED_GGUF, BASE_MMPROJ)
        try:
            backend = LlamaBackend(base_url=f"http://127.0.0.1:{LLAMA_PORT}", timeout=120.0)
            backend.name = "lfm-finetuned"
            preds, gts, meta = run_eval(backend, rows)
            metrics = compute_accuracy(preds, gts)
            results["finetuned"] = {"metrics": metrics, "predictions": preds, "ground_truth": gts}
            print(f"  Overall accuracy: {metrics['overall']:.1%}  (n={metrics['n']})\n")
        finally:
            stop_llama_server(proc)

    # ── Comparison table ──────────────────────────────────────────────────────
    print_table(results)

    # Save results
    out = REPORTS_DIR / "comparison.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"Results saved: {out}")


if __name__ == "__main__":
    main()
