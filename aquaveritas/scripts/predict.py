"""
Live Prediction Loop
---------------------
Polls the SimSat API for the current satellite position, checks if the
satellite is within 50km of any monitored water body (and hasn't been
observed there in 24h), fetches 4 images, runs 2 inference calls via
llama-server, and writes the merged observation to Postgres.

Prerequisites:
    - docker compose up          (SimSat + Postgres running)
    - llama-server running       (fine-tuned GGUF loaded)
    - Simulation started         (press Start in SimSat dashboard)

Usage:
    python scripts/predict.py
    python scripts/predict.py --interval 30 --model-url http://localhost:8080
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aquaveritas.db import Database
from aquaveritas.evaluator import LlamaBackend
from aquaveritas.locations import LOCATIONS_BY_ID
from aquaveritas.simsat import SimSatClient

IMAGE_DIR = Path(__file__).parent.parent / "data" / "images"


def save_image(image_bytes: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image_bytes)


def process_location(
    location_id: str,
    sat_lon: float,
    sat_lat: float,
    sat_alt_km: float,
    timestamp: str,
    client: SimSatClient,
    backend: LlamaBackend,
    db: Database,
):
    loc = LOCATIONS_BY_ID[location_id]
    print(f"  → {loc.name} [{location_id}]", end=" ", flush=True)

    images = client.fetch_location_images(
        lon=loc.lon, lat=loc.lat, timestamp=timestamp, location_id=loc.id
    )

    if not images.any_core_available:
        print("⚠ no core images — skipping")
        return

    # ── Save images to disk ───────────────────────────────────────────────────
    ts_slug  = timestamp[:16].replace(":", "-")
    img_dir  = IMAGE_DIR / location_id / ts_slug
    paths    = {}

    for name, result in [
        ("rgb_core",    images.rgb_core),
        ("swir_core",   images.swir_core),
        ("rgb_buffer",  images.rgb_buffer),
        ("swir_buffer", images.swir_buffer),
    ]:
        if result.available and result.image:
            path = img_dir / f"{name}.png"
            save_image(result.image, path)
            paths[f"{name}_path"] = str(path)
        else:
            paths[f"{name}_path"] = None

    # ── Insert unlabeled observation ──────────────────────────────────────────
    core_fp   = images.rgb_core.metadata.get("footprint")
    buffer_fp = images.rgb_buffer.metadata.get("footprint")

    obs_id = db.insert_observation(
        location_id           = location_id,
        observed_at           = timestamp,
        sat_lon               = sat_lon,
        sat_lat               = sat_lat,
        sat_alt_km            = sat_alt_km,
        core_footprint        = core_fp,
        buffer_footprint      = buffer_fp,
        image_quality_limited = False,
        **paths,
    )

    if obs_id == -1:
        print("⚠ duplicate — skipping inference")
        return

    # ── Run inference ─────────────────────────────────────────────────────────
    core_output   = None
    buffer_output = None

    if paths.get("rgb_core_path") and paths.get("swir_core_path"):
        rgb  = Path(paths["rgb_core_path"]).read_bytes()
        swir = Path(paths["swir_core_path"]).read_bytes()
        core_output = backend.infer_core(rgb, swir, loc)

    if paths.get("rgb_buffer_path") and paths.get("swir_buffer_path"):
        rgb  = Path(paths["rgb_buffer_path"]).read_bytes()
        swir = Path(paths["swir_buffer_path"]).read_bytes()
        buffer_output = backend.infer_buffer(rgb, swir, loc)

    db.apply_labels(obs_id, core_output, buffer_output)

    # ── Log result ────────────────────────────────────────────────────────────
    water_status = (core_output or {}).get("water_extent_status", "unknown")
    crop_stress  = (buffer_output or {}).get("crop_stress_level", "unknown")
    flood_risk   = (core_output or {}).get("flood_risk", "unknown")
    print(f"✓ water={water_status} crop={crop_stress} flood={flood_risk}")


def check_llama_server(base_url: str) -> bool:
    import requests
    try:
        resp = requests.get(f"{base_url}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="AquaVeritas live prediction loop")
    parser.add_argument("--interval",   type=int, default=30,
                        help="Poll interval in seconds (default: 30)")
    parser.add_argument("--model-url",  default="http://localhost:8080",
                        help="llama-server base URL (default: http://localhost:8080)")
    parser.add_argument("--db-url",     default=None,
                        help="Postgres connection URL (overrides DATABASE_URL env var)")
    args = parser.parse_args()

    # ── Pre-flight checks ─────────────────────────────────────────────────────
    print("AquaVeritas Live Prediction Loop")
    print("=" * 40)

    if not check_llama_server(args.model_url):
        print(f"ERROR: llama-server not reachable at {args.model_url}")
        print("Start it with:")
        print("  llama-server --model aquaveritas-backbone-Q8_0.gguf "
              "--mmproj aquaveritas-mmproj-F16.gguf --port 8080")
        sys.exit(1)
    print(f"llama-server: OK ({args.model_url})")

    import os
    if args.db_url:
        os.environ["DATABASE_URL"] = args.db_url

    db      = Database()
    client  = SimSatClient()
    backend = LlamaBackend(base_url=args.model_url)

    db.init_schema()

    print(f"Monitoring {len(LOCATIONS_BY_ID)} water bodies | poll every {args.interval}s")
    print("Press Ctrl+C to stop.\n")

    # ── Main loop ─────────────────────────────────────────────────────────────
    while True:
        try:
            pos = client.get_current_position()
        except Exception as exc:
            print(f"[{_now()}] SimSat unreachable: {exc} — retrying in {args.interval}s")
            time.sleep(args.interval)
            continue

        sat_lon, sat_lat, sat_alt_km = pos["lon-lat-alt"]
        timestamp = pos["timestamp"]

        triggered = db.get_trigger_locations(sat_lon, sat_lat)

        if triggered:
            print(f"[{_now()}] Satellite at ({sat_lon:.2f}, {sat_lat:.2f}) "
                  f"— {len(triggered)} location(s) triggered")
            for loc_row in triggered:
                process_location(
                    location_id = loc_row["id"],
                    sat_lon     = sat_lon,
                    sat_lat     = sat_lat,
                    sat_alt_km  = sat_alt_km,
                    timestamp   = timestamp,
                    client      = client,
                    backend     = backend,
                    db          = db,
                )
        else:
            print(f"[{_now()}] ({sat_lon:.2f}, {sat_lat:.2f}) — no locations triggered",
                  end="\r", flush=True)

        time.sleep(args.interval)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


if __name__ == "__main__":
    main()
