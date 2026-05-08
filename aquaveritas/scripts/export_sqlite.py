"""
Export AquaVeritas PostgreSQL observations to a bundled SQLite file.

This creates data/observations.db (relative to the hf_space/ directory)
for use by the HuggingFace Space, which cannot connect to a live PostgreSQL.

Usage:
    python scripts/export_sqlite.py
    python scripts/export_sqlite.py --db-path /custom/path/observations.db
    python scripts/export_sqlite.py --dry-run    # print counts, don't write
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

# Allow importing the project db layer
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from aquaveritas.db import Database
from aquaveritas.locations import LOCATIONS

DEFAULT_OUTPUT = REPO_ROOT / "hf_space" / "data" / "observations.db"


# ── Schema ────────────────────────────────────────────────────────────────────

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS locations (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    lon                   REAL NOT NULL,
    lat                   REAL NOT NULL,
    description           TEXT,
    expected_water_status TEXT,
    category              TEXT,
    baseline_date         TEXT
);

CREATE TABLE IF NOT EXISTS observations (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id            TEXT NOT NULL REFERENCES locations(id),
    observed_at            TEXT NOT NULL,
    water_extent_status    TEXT,
    flood_risk             TEXT,
    water_clarity          TEXT,
    shoreline_encroachment INTEGER,    -- 0/1 for boolean
    agriculture_present    INTEGER,
    crop_stress_level      TEXT,
    crop_stress_type       TEXT,
    cultivation_expanding  INTEGER,
    settlement_visible     INTEGER,
    bare_soil_expansion    INTEGER,
    image_quality_limited  INTEGER,
    prose_brief            TEXT,       -- Claude Haiku output if available
    UNIQUE (location_id, observed_at)
);

CREATE INDEX IF NOT EXISTS idx_obs_loc_time
    ON observations (location_id, observed_at DESC);
"""


# ── Export ────────────────────────────────────────────────────────────────────

def export(output_path: Path, dry_run: bool = False) -> None:
    print(f"Connecting to PostgreSQL...")
    pg = Database()

    print(f"Fetching all labeled observations...")
    rows = pg.get_observations_for_dashboard()
    print(f"  Found {len(rows)} labeled observations")

    if dry_run:
        print("[dry-run] Would write to:", output_path)
        _print_summary(rows)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Writing SQLite: {output_path}")
    conn = sqlite3.connect(output_path)
    conn.executescript(SQLITE_SCHEMA)

    # Seed locations
    print(f"  Seeding {len(LOCATIONS)} locations...")
    conn.executemany(
        """
        INSERT OR IGNORE INTO locations
            (id, name, lon, lat, description, expected_water_status,
             category, baseline_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                loc.id, loc.name, loc.lon, loc.lat,
                loc.description, loc.expected_water_status,
                loc.category,
                str(loc.baseline_date) if loc.baseline_date else None,
            )
            for loc in LOCATIONS
        ],
    )

    # Insert observations
    print(f"  Inserting {len(rows)} observations...")
    conn.executemany(
        """
        INSERT OR IGNORE INTO observations (
            location_id, observed_at,
            water_extent_status, flood_risk, water_clarity, shoreline_encroachment,
            agriculture_present, crop_stress_level, crop_stress_type,
            cultivation_expanding, settlement_visible, bare_soil_expansion,
            image_quality_limited, prose_brief
        ) VALUES (
            ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?
        )
        """,
        [
            (
                r["location_id"],
                str(r["observed_at"]),
                r.get("water_extent_status"),
                r.get("flood_risk"),
                r.get("water_clarity"),
                int(bool(r.get("shoreline_encroachment"))),
                int(bool(r.get("agriculture_present"))),
                r.get("crop_stress_level"),
                r.get("crop_stress_type"),
                int(bool(r.get("cultivation_expanding"))),
                int(bool(r.get("settlement_visible"))),
                int(bool(r.get("bare_soil_expansion"))),
                int(bool(r.get("image_quality_limited"))),
                r.get("prose_brief"),
            )
            for r in rows
        ],
    )

    conn.commit()
    conn.close()

    size_mb = output_path.stat().st_size / 1_048_576
    print(f"\nDone. {output_path} ({size_mb:.2f} MB)")
    _print_summary(rows)


def _print_summary(rows: list[dict]) -> None:
    from collections import Counter
    status_counts = Counter(r.get("water_extent_status") for r in rows)
    site_counts   = Counter(r.get("location_id") for r in rows)
    print(f"\n  Status distribution:")
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"    {status or 'unlabeled'}: {count}")
    print(f"\n  Sites with observations: {len(site_counts)}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Export observations to SQLite for HF Space")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output SQLite path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts without writing the SQLite file",
    )
    args = parser.parse_args()

    export(args.db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
