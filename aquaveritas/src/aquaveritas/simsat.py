"""SimSat API client — fetches satellite position and imagery."""

import json
import os
from dataclasses import dataclass, field
from typing import Optional

import requests

SIMSAT_URL = os.environ.get("SIMSAT_URL", "http://localhost:9005")
DEFAULT_WINDOW_SECONDS = 2_592_000   # 30 days — maximises cloud-free hit rate
RGB_BANDS   = ["red", "green", "blue"]
SWIR_BANDS  = ["swir16", "nir", "red"]
CORE_KM     = 15.0   # 15km tile = 3×3 grid of 5km sub-tiles; coord at shoreline
BUFFER_KM   = 15.0   # same tile for agricultural assessment (coord is at transition)


@dataclass
class ImageResult:
    image: Optional[bytes]
    metadata: dict
    available: bool


@dataclass
class LocationImages:
    """All four images for one location at one timestamp."""
    rgb_core:    ImageResult
    swir_core:   ImageResult
    rgb_buffer:  ImageResult
    swir_buffer: ImageResult
    timestamp:   str
    location_id: str = ""

    @property
    def any_core_available(self) -> bool:
        return self.rgb_core.available and self.swir_core.available

    @property
    def any_buffer_available(self) -> bool:
        return self.rgb_buffer.available and self.swir_buffer.available


class SimSatClient:
    def __init__(self, base_url: str = SIMSAT_URL):
        self.base_url = base_url.rstrip("/")
        self.session  = requests.Session()

    # ── Position ──────────────────────────────────────────────────────────────

    def get_current_position(self) -> dict:
        """Returns {lon-lat-alt: [lon, lat, alt_km], timestamp: str}."""
        resp = self.session.get(f"{self.base_url}/data/current/position", timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ── Single image fetch ────────────────────────────────────────────────────

    def fetch_sentinel(
        self,
        lon: float,
        lat: float,
        timestamp: str,
        bands: list[str],
        size_km: float,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> ImageResult:
        """Fetch a single Sentinel-2 image for given coords/timestamp/bands."""
        params = {
            "lon":            lon,
            "lat":            lat,
            "timestamp":      timestamp,
            "spectral_bands": bands,
            "size_km":        size_km,
            "return_type":    "png",
            "window_seconds": window_seconds,
        }
        try:
            resp = self.session.get(
                f"{self.base_url}/data/image/sentinel",
                params=params,
                timeout=120,    # Sentinel API is slow
            )
            resp.raise_for_status()
            metadata = json.loads(resp.headers.get("sentinel_metadata", "{}"))
            if metadata.get("image_available"):
                return ImageResult(image=resp.content, metadata=metadata, available=True)
            return ImageResult(image=None, metadata=metadata, available=False)
        except requests.RequestException as exc:
            return ImageResult(image=None, metadata={"error": str(exc)}, available=False)

    def fetch_sentinel_current(
        self,
        bands: list[str],
        size_km: float,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> ImageResult:
        """Fetch Sentinel-2 image at the simulator's current position."""
        params = {
            "spectral_bands": bands,
            "size_km":        size_km,
            "return_type":    "png",
            "window_seconds": window_seconds,
        }
        try:
            resp = self.session.get(
                f"{self.base_url}/data/current/image/sentinel",
                params=params,
                timeout=120,
            )
            resp.raise_for_status()
            metadata = json.loads(resp.headers.get("sentinel_metadata", "{}"))
            if metadata.get("image_available"):
                return ImageResult(image=resp.content, metadata=metadata, available=True)
            return ImageResult(image=None, metadata=metadata, available=False)
        except requests.RequestException as exc:
            return ImageResult(image=None, metadata={"error": str(exc)}, available=False)

    # ── Four-image location fetch ─────────────────────────────────────────────

    def fetch_location_images(
        self,
        lon: float,
        lat: float,
        timestamp: str,
        location_id: str = "",
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> LocationImages:
        """
        Fetch all four images for a location at a given timestamp:
          1. RGB  5km  (core water body)
          2. SWIR 5km  (core water body)
          3. RGB  10km (agricultural buffer)
          4. SWIR 10km (agricultural buffer)
        """
        rgb_core    = self.fetch_sentinel(lon, lat, timestamp, RGB_BANDS,  CORE_KM,   window_seconds)
        swir_core   = self.fetch_sentinel(lon, lat, timestamp, SWIR_BANDS, CORE_KM,   window_seconds)
        rgb_buffer  = self.fetch_sentinel(lon, lat, timestamp, RGB_BANDS,  BUFFER_KM, window_seconds)
        swir_buffer = self.fetch_sentinel(lon, lat, timestamp, SWIR_BANDS, BUFFER_KM, window_seconds)

        return LocationImages(
            rgb_core    = rgb_core,
            swir_core   = swir_core,
            rgb_buffer  = rgb_buffer,
            swir_buffer = swir_buffer,
            timestamp   = timestamp,
            location_id = location_id,
        )
