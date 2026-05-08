"""
Data Labeling
-------------
Reads unlabeled observations from Postgres, calls the Claude oracle
annotator for each, and writes labels back to the database.

Run after collect_data.py. Safe to re-run — skips already-labeled rows.

Usage:
    python scripts/label_data.py
    python scripts/label_data.py --batch 50
    python scripts/label_data.py --location lake_chad
"""

import argparse
import sys
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aquaveritas.annotator import Annotator
from aquaveritas.db import Database
from aquaveritas.locations import LOCATIONS_BY_ID


def label_one(row: dict, annotator: Annotator, db: Database) -> str:
    loc = LOCATIONS_BY_ID.get(row["location_id"])
    if loc is None:
        return "error: unknown location"

    rgb_core_path   = row.get("rgb_core_path")
    swir_core_path  = row.get("swir_core_path")
    rgb_buf_path    = row.get("rgb_buffer_path")
    swir_buf_path   = row.get("swir_buffer_path")

    core_output   = None
    buffer_output = None

    # ── Core zone ─────────────────────────────────────────────────────────────
    if rgb_core_path and swir_core_path:
        try:
            rgb_bytes  = Path(rgb_core_path).read_bytes()
            swir_bytes = Path(swir_core_path).read_bytes()
            core_output = annotator.annotate_core(rgb_bytes, swir_bytes, loc)
        except FileNotFoundError as exc:
            return f"error: {exc}"
    else:
        # Images not available — set quality flag but no labels
        db.apply_labels(row["id"], None, None)
        return "skipped (no core images)"

    # ── Buffer zone ───────────────────────────────────────────────────────────
    if rgb_buf_path and swir_buf_path:
        try:
            rgb_bytes  = Path(rgb_buf_path).read_bytes()
            swir_bytes = Path(swir_buf_path).read_bytes()
            buffer_output = annotator.annotate_buffer(rgb_bytes, swir_bytes, loc)
        except FileNotFoundError:
            pass  # buffer images missing — still save core labels

    if core_output is None:
        return "error: annotator returned None"

    db.apply_labels(row["id"], core_output, buffer_output)
    return "ok"


def main():
    parser = argparse.ArgumentParser(description="Label AquaVeritas observations with Claude oracle")
    parser.add_argument("--batch",    type=int, default=200,
                        help="Max observations to label per run (default: 200)")
    parser.add_argument("--location", default=None,
                        help="Restrict to one location ID")
    args = parser.parse_args()

    db        = Database()
    annotator = Annotator()

    rows = db.get_unlabeled(limit=args.batch)

    if args.location:
        rows = [r for r in rows if r["location_id"] == args.location]

    if not rows:
        print("No unlabeled observations found.")
        return

    print(f"Labeling {len(rows)} observations…")
    counters = {"ok": 0, "skipped": 0, "error": 0}

    for row in tqdm(rows, unit="obs"):
        result = label_one(row, annotator, db)
        if result == "ok":
            counters["ok"] += 1
        elif result.startswith("skipped"):
            counters["skipped"] += 1
        else:
            counters["error"] += 1
            tqdm.write(f"  [{row['location_id']} {row['observed_at']}] {result}")

    print("\nLabeling complete:", counters)


if __name__ == "__main__":
    main()
