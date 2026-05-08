"""
Data Collection
---------------
Fetches Sentinel-2 imagery for all 12 monitored locations across the training
time range (2018-01-01 to 2024-12-01) at monthly intervals.

Saves images to disk and inserts unlabeled observation records into Postgres.
Labels are NOT applied here — run label_data.py afterwards.

Usage:
    python scripts/collect_data.py
    python scripts/collect_data.py --location lake_chad
    python scripts/collect_data.py --start 2022-01-01 --end 2022-12-01
    python scripts/collect_data.py --location all --workers 4
"""

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aquaveritas.db import Database
from aquaveritas.locations import LOCATIONS, LOCATIONS_BY_ID
from aquaveritas.simsat import SimSatClient

IMAGE_DIR  = Path(__file__).parent.parent / "data" / "images"
START_DATE = date(2018, 1, 1)
END_DATE   = date(2024, 12, 1)


def monthly_timestamps(start: date, end: date) -> list[str]:
    """Generate first-of-month ISO timestamps between start and end inclusive."""
    timestamps = []
    current = start.replace(day=1)
    while current <= end:
        timestamps.append(current.strftime("%Y-%m-%dT00:00:00Z"))
        month = current.month + 1
        year  = current.year + (month > 12)
        current = current.replace(year=year, month=month % 12 or 12, day=1)
    return timestamps


def save_image(image_bytes: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image_bytes)


def collect_one(
    location_id: str,
    timestamp:   str,
    client:      SimSatClient,
    db:          Database,
) -> str:
    """Fetch and store one location/timestamp. Returns status string."""
    loc = LOCATIONS_BY_ID[location_id]

    if db.observation_exists(location_id, timestamp):
        return "skipped (exists)"

    images = client.fetch_location_images(
        lon=loc.lon, lat=loc.lat, timestamp=timestamp, location_id=loc.id
    )

    # With CORE_KM=15 the tile covers water + shoreline + agriculture — both
    # rgb_core and swir_core are the 15km grid tiles used for all assessments.
    quality_limited = not images.rgb_core.available and not images.swir_core.available

    # Save available images to disk
    ts_slug = timestamp[:10]  # YYYY-MM-DD
    img_dir = IMAGE_DIR / location_id / ts_slug
    paths   = {}

    for name, result in [
        ("rgb_core",  images.rgb_core),
        ("swir_core", images.swir_core),
    ]:
        if result.available and result.image:
            path = img_dir / f"{name}.png"
            save_image(result.image, path)
            paths[f"{name}_path"] = str(path)
        else:
            paths[f"{name}_path"] = None

    core_fp = images.rgb_core.metadata.get("footprint")

    db.insert_observation(
        location_id           = location_id,
        observed_at           = timestamp,
        sat_lon               = loc.lon,
        sat_lat               = loc.lat,
        sat_alt_km            = 0.0,
        core_footprint        = core_fp,
        buffer_footprint      = None,
        image_quality_limited = quality_limited,
        rgb_core_path         = paths.get("rgb_core_path"),
        swir_core_path        = paths.get("swir_core_path"),
        rgb_buffer_path       = None,
        swir_buffer_path      = None,
    )

    status = "ok"
    if quality_limited:
        status = "quality_limited"
    elif not images.rgb_core.available:
        status = "partial (no rgb)"
    return status


def run_collection(
    location_ids: list[str],
    start:        date,
    end:          date,
    workers:      int,
):
    client = SimSatClient()
    db     = Database()
    db.init_schema()
    db.seed_locations(LOCATIONS)

    timestamps = monthly_timestamps(start, end)
    tasks      = [(loc_id, ts) for loc_id in location_ids for ts in timestamps]

    print(f"Collecting {len(tasks)} observations "
          f"({len(location_ids)} locations × {len(timestamps)} months)")

    counters = {"ok": 0, "skipped": 0, "quality_limited": 0, "partial": 0, "error": 0}

    with tqdm(total=len(tasks), unit="obs") as bar:
        def _task(args):
            loc_id, ts = args
            try:
                status = collect_one(loc_id, ts, client, db)
                return status
            except Exception as exc:
                return f"error: {exc}"

        if workers == 1:
            for args in tasks:
                result = _task(args)
                _update_counters(counters, result)
                bar.update(1)
                bar.set_postfix(counters)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_task, t): t for t in tasks}
                for fut in as_completed(futures):
                    result = fut.result()
                    _update_counters(counters, result)
                    bar.update(1)
                    bar.set_postfix(counters)

    print("\nCollection complete:", counters)


def _update_counters(counters, result):
    if result.startswith("skipped"):
        counters["skipped"] += 1
    elif result == "ok":
        counters["ok"] += 1
    elif result == "quality_limited":
        counters["quality_limited"] += 1
    elif result.startswith("partial"):
        counters["partial"] += 1
    else:
        counters["error"] += 1


def main():
    parser = argparse.ArgumentParser(description="Collect AquaVeritas training images")
    parser.add_argument("--location", default="all",
                        help="Location ID or 'all' (default: all)")
    parser.add_argument("--start", default=START_DATE.isoformat(),
                        help="Start date YYYY-MM-DD")
    parser.add_argument("--end",   default=END_DATE.isoformat(),
                        help="End date YYYY-MM-DD")
    parser.add_argument("--workers", type=int, default=3,
                        help="Parallel workers across locations (default: 3)")
    args = parser.parse_args()

    if args.location == "all":
        location_ids = [loc.id for loc in LOCATIONS]
    elif args.location in LOCATIONS_BY_ID:
        location_ids = [args.location]
    else:
        print(f"Unknown location: {args.location}. "
              f"Valid: {list(LOCATIONS_BY_ID.keys())}")
        sys.exit(1)

    start = date.fromisoformat(args.start)
    end   = date.fromisoformat(args.end)

    run_collection(location_ids, start, end, args.workers)


if __name__ == "__main__":
    main()
