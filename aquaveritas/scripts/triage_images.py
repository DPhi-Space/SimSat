"""
Image Triage
------------
Runs before label_data.py. Classifies every observation with an image on disk
into one of three tiers and writes the verdict to Postgres.

  PASS     — image is clean, ready to label
  MARGINAL — degraded (partial cloud, slight tile artefact) but usable; labelled
             with image_quality_limited context in mind
  FAIL     — unusable (black no-data, >70% cloud, broken tile boundary);
             excluded from get_unlabeled() but record + file kept intact

Two scoring modes
-----------------
--heuristic   Fast PIL/numpy checks. No model required. Good for catching
              obvious fails (black tiles, missing files) before a full run.
              Cannot reliably detect cloud cover or partial artefacts, so
              it only emits PASS or FAIL — no MARGINAL.

(default)     Calls LM Studio's OpenAI-compatible API with a vision model.
              Returns structured JSON with per-criterion scores and a verdict.
              Emits all three tiers.

Usage
-----
    # heuristic pre-pass (fast, no GPU needed)
    python scripts/triage_images.py --heuristic

    # LM Studio vision model (default port 1234, model auto-detected)
    python scripts/triage_images.py

    # specify model and batch size
    python scripts/triage_images.py --model llava-1.6-mistral-7b-gguf --batch 100

    # single location
    python scripts/triage_images.py --location lake_chad

    # dry-run: print verdicts without writing to DB
    python scripts/triage_images.py --dry-run

    # export rejection manifest after triage
    python scripts/triage_images.py --export-manifest
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aquaveritas.db import Database

# ── Constants ──────────────────────────────────────────────────────────────────

LMSTUDIO_BASE_URL = "http://localhost:8234/v1"
MANIFEST_DIR      = Path(__file__).parent.parent / "data" / "triage"

HEURISTIC_MODEL_TAG = "heuristic-pil"

# Pixel thresholds for heuristic mode
BLACK_MEAN_THRESHOLD   = 8     # mean pixel value below this → likely no-data
BLACK_PIXEL_RATIO      = 0.65  # fraction of near-black pixels → fail
BLACK_PIXEL_VALUE      = 15    # per-channel max to count as "black"
SMALL_FILE_BYTES       = 4096  # PNG smaller than this → almost certainly blank

# Verdict score thresholds (LM Studio mode)
PASS_MIN_TOTAL     = 12
MARGINAL_MIN_TOTAL = 8
REQUIRED_TILE_MIN  = 3   # TILE_INTEGRITY must be 3 for PASS
REQUIRED_CLOUD_MIN = 2   # CLOUD_COVER must be ≥ 2 for PASS

# ── Evaluation prompt ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a remote sensing analyst evaluating Sentinel-2 L2A satellite imagery "
    "for a freshwater monitoring training dataset. Assess each image against strict "
    "data quality criteria and return a structured JSON report. Be conservative — "
    "flag uncertainty rather than guess. Do not hallucinate features not clearly "
    "visible."
)

USER_PROMPT = """Evaluate this Sentinel-2 satellite image for inclusion in a freshwater change-detection training dataset.

## Context
- Tile: 15 km × 15 km true-colour RGB (B04/B03/B02), ~10 m/pixel, Level-2A
- Layout: 3×3 grid of 5 km sub-tiles

## Scoring (0–3 each)
  0 = absent/fails   1 = marginal   2 = acceptable   3 = clear/excellent

Criteria:
  WATER_BODY      — open water visible
  SHORELINE       — water–land boundary visible (delta edge, riverbank, lake shore)
  AGRICULTURE     — fields, irrigation canals, crop rows, cultivated flood plains
  TILE_INTEGRITY  — no black no-data strips, wedge voids, or tile boundary artefacts
  CLOUD_COVER     — surface visible (3=<10% cloud, 2=<40%, 1=<70%, 0=>70%)
  SPATIAL_CONTEXT — meaningful variation (not 100% open ocean or 100% uniform desert)

## Rules
  PASS     = total ≥ 12 AND TILE_INTEGRITY = 3 AND CLOUD_COVER ≥ 2
  MARGINAL = total 8–11  OR  any single criterion = 0 but total ≥ 8
  FAIL     = total < 8   OR  TILE_INTEGRITY < 2  OR  CLOUD_COVER < 2

## Output
Return ONLY valid JSON. No prose before or after.

{
  "location_hint": "<dominant features, colours, patterns>",
  "scores": {
    "WATER_BODY": <0-3>,
    "SHORELINE": <0-3>,
    "AGRICULTURE": <0-3>,
    "TILE_INTEGRITY": <0-3>,
    "CLOUD_COVER": <0-3>,
    "SPATIAL_CONTEXT": <0-3>
  },
  "total": <sum 0-18>,
  "verdict": "<PASS|MARGINAL|FAIL>",
  "verdict_reason": "<one sentence>",
  "flags": ["<zero or more of: tile_boundary_artefact, black_no_data, high_cloud, no_water_visible, wrong_feature, open_water_only, inland_only>"],
  "recommended_action": "<keep|re-coordinate|resample_date|remove>"
}"""


# ── Heuristic scorer ───────────────────────────────────────────────────────────

def heuristic_score(rgb_path: Path) -> dict:
    """PIL/numpy quality check. Returns triage dict (PASS or FAIL only)."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        raise SystemExit(
            "Heuristic mode requires Pillow and numpy.\n"
            "  pip install Pillow numpy"
        )

    if not rgb_path.exists():
        return _fail_result(
            flags=["black_no_data"],
            reason="Image file not found on disk.",
            scores={k: 0 for k in _score_keys()},
            model=HEURISTIC_MODEL_TAG,
        )

    if rgb_path.stat().st_size < SMALL_FILE_BYTES:
        return _fail_result(
            flags=["black_no_data"],
            reason=f"File is only {rgb_path.stat().st_size} bytes — likely a blank/empty tile.",
            scores={k: 0 for k in _score_keys()},
            model=HEURISTIC_MODEL_TAG,
        )

    try:
        img = Image.open(rgb_path).convert("RGB")
    except Exception as exc:
        return _fail_result(
            flags=["black_no_data"],
            reason=f"Could not open image: {exc}",
            scores={k: 0 for k in _score_keys()},
            model=HEURISTIC_MODEL_TAG,
        )

    arr = np.array(img, dtype=np.float32)

    mean_val      = float(arr.mean())
    black_mask    = (arr < BLACK_PIXEL_VALUE).all(axis=2)
    black_ratio   = float(black_mask.mean())

    if mean_val < BLACK_MEAN_THRESHOLD or black_ratio > BLACK_PIXEL_RATIO:
        pct = int(black_ratio * 100)
        return _fail_result(
            flags=["black_no_data", "tile_boundary_artefact"],
            reason=(
                f"{pct}% of pixels are near-black (mean={mean_val:.1f}) — "
                "no-data tile or MGRS boundary artefact."
            ),
            scores={"WATER_BODY": 0, "SHORELINE": 0, "AGRICULTURE": 0,
                    "TILE_INTEGRITY": 0, "CLOUD_COVER": 0, "SPATIAL_CONTEXT": 0},
            model=HEURISTIC_MODEL_TAG,
        )

    # Heuristic cannot assess cloud or features reliably — emit PASS
    # and let the LM Studio pass do the fine-grained scoring.
    scores = {
        "WATER_BODY": 2, "SHORELINE": 2, "AGRICULTURE": 2,
        "TILE_INTEGRITY": 3, "CLOUD_COVER": 2, "SPATIAL_CONTEXT": 2,
    }
    return {
        "verdict":     "pass",
        "verdict_reason": "No obvious no-data artefacts detected by heuristic check.",
        "flags":       [],
        "scores":      scores,
        "total":       sum(scores.values()),
        "model":       HEURISTIC_MODEL_TAG,
    }


def _score_keys():
    return ["WATER_BODY", "SHORELINE", "AGRICULTURE",
            "TILE_INTEGRITY", "CLOUD_COVER", "SPATIAL_CONTEXT"]


def _fail_result(flags, reason, scores, model):
    return {
        "verdict":      "fail",
        "verdict_reason": reason,
        "flags":        flags,
        "scores":       scores,
        "total":        sum(scores.values()),
        "model":        model,
    }


# ── LM Studio scorer ───────────────────────────────────────────────────────────

def lmstudio_score(rgb_path: Path, model: str, base_url: str) -> dict:
    """Send image to LM Studio vision model, parse JSON response."""
    try:
        from openai import OpenAI
    except ImportError:
        raise SystemExit(
            "LM Studio mode requires the openai package.\n"
            "  pip install openai"
        )

    if not rgb_path.exists():
        return _fail_result(
            flags=["black_no_data"],
            reason="Image file not found on disk.",
            scores={k: 0 for k in _score_keys()},
            model=model,
        )

    img_b64 = base64.b64encode(rgb_path.read_bytes()).decode()

    client = OpenAI(base_url=base_url, api_key="lm-studio")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type":      "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                        },
                        {"type": "text", "text": USER_PROMPT},
                    ],
                },
            ],
            temperature=0.0,
            max_tokens=512,
        )
    except Exception as exc:
        return _fail_result(
            flags=[],
            reason=f"LM Studio API error: {exc}",
            scores={k: 0 for k in _score_keys()},
            model=model,
        )

    raw = response.choices[0].message.content.strip()

    # Strip markdown fences if the model wraps JSON in ```json ... ```
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(
            l for l in lines if not l.startswith("```")
        ).strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return _fail_result(
            flags=[],
            reason=f"Model returned non-JSON response: {raw[:120]}",
            scores={k: 0 for k in _score_keys()},
            model=model,
        )

    return _normalise_lmstudio_result(parsed, model)


def _normalise_lmstudio_result(parsed: dict, model: str) -> dict:
    """Normalise model output to internal triage dict."""
    scores  = parsed.get("scores", {})
    total   = parsed.get("total", sum(scores.values()))
    verdict = parsed.get("verdict", "").lower()

    # Re-apply rules in case model got them wrong
    tile_ok  = scores.get("TILE_INTEGRITY", 0) >= REQUIRED_TILE_MIN
    cloud_ok = scores.get("CLOUD_COVER",    0) >= REQUIRED_CLOUD_MIN

    if total >= PASS_MIN_TOTAL and tile_ok and cloud_ok:
        verdict = "pass"
    elif total >= MARGINAL_MIN_TOTAL:
        verdict = "marginal"
    else:
        verdict = "fail"

    return {
        "verdict":        verdict,
        "verdict_reason": parsed.get("verdict_reason", ""),
        "flags":          parsed.get("flags", []),
        "scores":         scores,
        "total":          total,
        "model":          model,
    }


# ── Model auto-detection ───────────────────────────────────────────────────────

def detect_loaded_model(base_url: str) -> str:
    """Ask LM Studio which model is currently loaded."""
    try:
        from openai import OpenAI
        client = OpenAI(base_url=base_url, api_key="lm-studio")
        models = client.models.list()
        ids = [m.id for m in models.data]
        if not ids:
            raise SystemExit(
                "No model loaded in LM Studio. Load a vision model and retry."
            )
        if len(ids) > 1:
            print(f"  Multiple models detected: {ids}")
            print(f"  Using: {ids[0]}  (pass --model to override)")
        return ids[0]
    except Exception as exc:
        raise SystemExit(
            f"Cannot reach LM Studio at {base_url}.\n"
            f"  Error: {exc}\n"
            f"  Start LM Studio, load a vision model, and enable the local server."
        )


# ── Rejection manifest export ──────────────────────────────────────────────────

def export_rejection_manifest(db: Database, out_dir: Path) -> None:
    """Write JSON + CSV rejection manifests for all FAIL observations."""
    rows = db.get_failed_observations()
    if not rows:
        print("No FAIL observations in database — manifest is empty.")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    ts    = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # JSON
    json_path = out_dir / f"rejection_manifest_{ts}.json"
    serialisable = []
    for r in rows:
        row = dict(r)
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()
        serialisable.append(row)
    json_path.write_text(json.dumps(serialisable, indent=2))

    # CSV (flat — flags/scores as JSON strings)
    csv_path = out_dir / f"rejection_manifest_{ts}.csv"
    fieldnames = [
        "id", "location_id", "location_name", "observed_at",
        "triage_verdict", "triage_reason", "triage_flags",
        "triage_scores", "triage_model", "triaged_at", "rgb_core_path",
    ]
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in serialisable:
            row["triage_flags"]  = json.dumps(row.get("triage_flags", []))
            row["triage_scores"] = json.dumps(row.get("triage_scores", {}))
            writer.writerow(row)

    print(f"\nRejection manifest written:")
    print(f"  JSON → {json_path}")
    print(f"  CSV  → {csv_path}")
    print(f"  {len(rows)} FAIL observations recorded")


# ── Main triage loop ───────────────────────────────────────────────────────────

def run_triage(
    db:          Database,
    rows:        list[dict],
    mode:        str,           # 'heuristic' | 'lmstudio'
    model:       str,
    base_url:    str,
    dry_run:     bool,
) -> dict:
    counters = {"pass": 0, "marginal": 0, "fail": 0, "error": 0}

    for row in tqdm(rows, unit="img"):
        rgb_path = Path(row["rgb_core_path"]) if row.get("rgb_core_path") else None

        if rgb_path is None:
            result = _fail_result(
                flags=["black_no_data"],
                reason="No rgb_core_path recorded for this observation.",
                scores={k: 0 for k in _score_keys()},
                model=model,
            )
        elif mode == "heuristic":
            result = heuristic_score(rgb_path)
        else:
            result = lmstudio_score(rgb_path, model, base_url)

        verdict = result["verdict"]

        if not dry_run:
            try:
                db.apply_triage(
                    observation_id = row["id"],
                    verdict        = verdict,
                    reason         = result["verdict_reason"],
                    flags          = result["flags"],
                    scores         = result["scores"],
                    model          = result["model"],
                )
                counters[verdict] = counters.get(verdict, 0) + 1
            except Exception as exc:
                tqdm.write(
                    f"  DB error [{row['location_id']} "
                    f"{row['observed_at']}]: {exc}"
                )
                counters["error"] += 1
        else:
            tqdm.write(
                f"  [DRY-RUN] {row['location_id']:25s} "
                f"{str(row['observed_at'])[:10]}  →  {verdict.upper():8s}  "
                f"{result['verdict_reason'][:60]}"
            )
            counters[verdict] = counters.get(verdict, 0) + 1

    return counters


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Triage collected images into PASS / MARGINAL / FAIL before labelling."
    )
    parser.add_argument(
        "--heuristic", action="store_true",
        help="Fast PIL-based check (no LM Studio needed). Detects blank/no-data tiles only.",
    )
    parser.add_argument(
        "--model", default=None,
        help="LM Studio model name. Auto-detected from /v1/models if omitted.",
    )
    parser.add_argument(
        "--lmstudio-url", default=LMSTUDIO_BASE_URL,
        help=f"LM Studio base URL (default: {LMSTUDIO_BASE_URL})",
    )
    parser.add_argument(
        "--location", default=None,
        help="Restrict to one location ID.",
    )
    parser.add_argument(
        "--batch", type=int, default=2000,
        help="Max observations to triage per run (default: 2000).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print verdicts without writing to the database.",
    )
    parser.add_argument(
        "--export-manifest", action="store_true",
        help="After triage, export JSON + CSV rejection manifest for FAIL observations.",
    )
    parser.add_argument(
        "--export-only", action="store_true",
        help="Skip triage, just export the rejection manifest from existing DB records.",
    )
    parser.add_argument(
        "--retriage-heuristic", action="store_true",
        help=(
            "Re-evaluate observations that were marked PASS by the heuristic pass. "
            "Use this for the LM Studio vision pass after running --heuristic first."
        ),
    )
    args = parser.parse_args()

    db = Database()

    # ── Schema migration (idempotent) ──────────────────────────────────────────
    if not args.dry_run:
        try:
            db.run_triage_migration()
        except psycopg2.Error as exc:
            raise SystemExit(f"Migration failed: {exc}")

    # ── Export-only mode ───────────────────────────────────────────────────────
    if args.export_only:
        export_rejection_manifest(db, MANIFEST_DIR)
        return

    # ── Resolve model ──────────────────────────────────────────────────────────
    if args.heuristic:
        mode  = "heuristic"
        model = HEURISTIC_MODEL_TAG
    else:
        mode  = "lmstudio"
        model = args.model or detect_loaded_model(args.lmstudio_url)
        print(f"Model: {model}")

    # ── Fetch rows ─────────────────────────────────────────────────────────────
    if args.retriage_heuristic:
        if args.heuristic:
            raise SystemExit("--retriage-heuristic cannot be combined with --heuristic.")
        rows = db.get_heuristic_passed(location_id=args.location, limit=args.batch)
        fetch_label = "heuristic-PASS observations for vision re-evaluation"
    else:
        rows = db.get_untriaged(location_id=args.location, limit=args.batch)
        fetch_label = "untriaged observations"

    if not rows:
        print(f"No {fetch_label} found.")
        if args.export_manifest:
            export_rejection_manifest(db, MANIFEST_DIR)
        return

    print(
        f"Triaging {len(rows)} {fetch_label} "
        f"[mode={mode}]"
        + (f" [location={args.location}]" if args.location else "")
        + (" [--retriage-heuristic]" if args.retriage_heuristic else "")
        + (" [DRY-RUN]" if args.dry_run else "")
    )

    # ── Triage ─────────────────────────────────────────────────────────────────
    counters = run_triage(
        db       = db,
        rows     = rows,
        mode     = mode,
        model    = model,
        base_url = args.lmstudio_url,
        dry_run  = args.dry_run,
    )

    # ── Summary ────────────────────────────────────────────────────────────────
    total   = sum(counters.values())
    pass_n  = counters.get("pass",    0)
    marg_n  = counters.get("marginal",0)
    fail_n  = counters.get("fail",    0)
    err_n   = counters.get("error",   0)

    print(f"\nTriage complete  ({total} processed)")
    print(f"  PASS     {pass_n:>5}  ({pass_n/total*100:.1f}%)")
    print(f"  MARGINAL {marg_n:>5}  ({marg_n/total*100:.1f}%)")
    print(f"  FAIL     {fail_n:>5}  ({fail_n/total*100:.1f}%)  ← excluded from labelling")
    if err_n:
        print(f"  ERRORS   {err_n:>5}")

    if not args.dry_run:
        db_summary = db.get_triage_summary()
        print(f"\nDatabase totals: {db_summary}")

    if args.export_manifest and not args.dry_run:
        export_rejection_manifest(db, MANIFEST_DIR)


if __name__ == "__main__":
    main()
