"""
Training Dataset Preparation
-----------------------------
Reads all labeled observations from Postgres, formats them into a HuggingFace
dataset in the conversational JSONL format expected by leap-finetune, and
pushes to HuggingFace Hub.

Creates two splits: train (before 2024-01-01) and test (2024-01-01 onwards).
Each example contains: system prompt, two images (RGB + SWIR), assistant JSON.

Usage:
    python scripts/train.py --hf-repo YOUR_HF_USERNAME/aquaveritas-water-stress
    python scripts/train.py --hf-repo ... --dry-run
"""

import argparse
import base64
import json
import sys
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aquaveritas.annotator import CORE_SYSTEM, BUFFER_SYSTEM
from aquaveritas.db import Database
from aquaveritas.locations import LOCATIONS_BY_ID


CORE_FIELDS   = ["water_extent_status", "flood_risk", "water_clarity",
                 "shoreline_encroachment", "image_quality_limited"]
BUFFER_FIELDS = ["agriculture_present", "crop_stress_level", "crop_stress_type",
                 "cultivation_expanding_toward_water", "settlement_visible",
                 "bare_soil_expansion", "image_quality_limited"]


def row_to_examples(row: dict) -> list[dict]:
    """
    Convert one DB observation to 0, 1, or 2 JSONL training examples
    (one for core zone, one for buffer zone — only if both images present).
    """
    loc = LOCATIONS_BY_ID.get(row["location_id"])
    if loc is None:
        return []

    examples = []

    # ── Core zone example ─────────────────────────────────────────────────────
    if (row.get("rgb_core_path") and row.get("swir_core_path")
            and row.get("water_extent_status")):
        try:
            rgb_b64  = _encode(Path(row["rgb_core_path"]).read_bytes())
            swir_b64 = _encode(Path(row["swir_core_path"]).read_bytes())
        except FileNotFoundError:
            rgb_b64 = swir_b64 = None

        if rgb_b64:
            label = {f: row.get(f) for f in CORE_FIELDS}
            system = CORE_SYSTEM.format(
                name=loc.name, lat=loc.lat, lon=loc.lon,
                description=loc.description,
                expected_water_status=loc.expected_water_status,
            )
            examples.append(_make_example(system, rgb_b64, swir_b64,
                                          label, "core", row))

    # ── Buffer zone example ───────────────────────────────────────────────────
    if (row.get("rgb_buffer_path") and row.get("swir_buffer_path")
            and row.get("crop_stress_level")):
        try:
            rgb_b64  = _encode(Path(row["rgb_buffer_path"]).read_bytes())
            swir_b64 = _encode(Path(row["swir_buffer_path"]).read_bytes())
        except FileNotFoundError:
            rgb_b64 = swir_b64 = None

        if rgb_b64:
            label = {
                "agriculture_present":              row.get("agriculture_present"),
                "crop_stress_level":                row.get("crop_stress_level"),
                "crop_stress_type":                 row.get("crop_stress_type"),
                "cultivation_expanding_toward_water": row.get("cultivation_expanding"),
                "settlement_visible":               row.get("settlement_visible"),
                "bare_soil_expansion":              row.get("bare_soil_expansion"),
                "image_quality_limited":            row.get("image_quality_limited"),
            }
            system = BUFFER_SYSTEM.format(
                name=loc.name, lat=loc.lat, lon=loc.lon,
                description=loc.description,
            )
            examples.append(_make_example(system, rgb_b64, swir_b64,
                                          label, "buffer", row))
    return examples


def _make_example(system, rgb_b64, swir_b64, label, zone, row) -> dict:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{rgb_b64}"}},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{swir_b64}"}},
                {"type": "text",
                 "text": "Analyse these satellite images and return the JSON assessment."},
            ]},
            {"role": "assistant", "content": json.dumps(label)},
        ],
        "metadata": {
            "location_id": row["location_id"],
            "observed_at": str(row["observed_at"]),
            "zone":        zone,
        },
    }


def _encode(b: bytes) -> str:
    return base64.standard_b64encode(b).decode()


def build_split(rows: list[dict], split_name: str) -> list[dict]:
    examples = []
    for row in tqdm(rows, desc=f"Building {split_name}", unit="obs"):
        examples.extend(row_to_examples(row))
    return examples


def push_to_hf(train_examples, test_examples, repo_id: str):
    from datasets import Dataset, DatasetDict

    def to_hf(examples):
        return Dataset.from_list([
            {
                "messages":    json.dumps(e["messages"]),
                "location_id": e["metadata"]["location_id"],
                "observed_at": e["metadata"]["observed_at"],
                "zone":        e["metadata"]["zone"],
            }
            for e in examples
        ])

    ds = DatasetDict({"train": to_hf(train_examples), "test": to_hf(test_examples)})
    ds.push_to_hub(repo_id)
    print(f"Pushed to https://huggingface.co/datasets/{repo_id}")


def main():
    parser = argparse.ArgumentParser(description="Prepare AquaVeritas training dataset")
    parser.add_argument("--hf-repo", required=True,
                        help="HuggingFace dataset repo, e.g. user/aquaveritas-water-stress")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print stats without pushing to HuggingFace")
    args = parser.parse_args()

    db = Database()
    print("Loading labeled observations…")
    train_rows = db.get_labeled(split="train")
    test_rows  = db.get_labeled(split="test")

    print(f"Train rows: {len(train_rows)} | Test rows: {len(test_rows)}")

    train_examples = build_split(train_rows, "train")
    test_examples  = build_split(test_rows,  "test")

    print(f"\nTrain examples: {len(train_examples)}")
    print(f"Test  examples: {len(test_examples)}")

    # Write local JSONL copies
    out_dir = Path(__file__).parent.parent / "data"
    out_dir.mkdir(exist_ok=True)
    for name, examples in [("train", train_examples), ("test", test_examples)]:
        path = out_dir / f"{name}.jsonl"
        with path.open("w") as f:
            for ex in examples:
                f.write(json.dumps(ex) + "\n")
        print(f"Saved {path}")

    if args.dry_run:
        print("Dry run — not pushing to HuggingFace.")
        return

    push_to_hf(train_examples, test_examples, args.hf_repo)


if __name__ == "__main__":
    main()
