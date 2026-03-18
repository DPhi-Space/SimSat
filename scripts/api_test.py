import argparse
import io
import json
from typing import Any, Dict, List, Optional

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import requests


BASE_URL = "http://localhost:9005"
REQUEST_TIMEOUT_SECONDS = 30


def _request_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[requests.Response]:
    url = f"{BASE_URL}{endpoint}"
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        print(f"Request failed for {url}: {exc}")
        return None

    if response.status_code != 200:
        print(f"Error from {url}: status code {response.status_code}")
        print(f"Response body: {response.text}")
        return None

    return response


def _show_png(content: bytes, title: str) -> bool:
    if not content:
        print("Empty PNG payload.")
        return False
    try:
        image = mpimg.imread(io.BytesIO(content), format="PNG")
    except Exception as exc:
        print(f"Could not decode PNG image: {exc}")
        return False

    plt.figure(figsize=(8, 8))
    plt.imshow(image)
    plt.title(title)
    plt.axis("off")
    plt.show()
    return True


def _test_sentinel_endpoint(endpoint: str, params: Dict[str, Any]) -> None:
    response = _request_get(endpoint, params=params)
    if response is None:
        return

    if params.get("return_type", "png") == "png":
        try:
            metadata = json.loads(response.headers.get("sentinel_metadata", ""))
        except json.JSONDecodeError:
            metadata = None

        print(f"Sentinel metadata: {metadata}")
        if not metadata.get("image_available"):
            print("No image available")
            return
        _show_png(response.content, "Sentinel image")
        return

    try:
        payload = response.json()
    except ValueError:
        print("Invalid JSON body.")
        return

    metadata = payload.get("sentinel_metadata")

    print(f"Sentinel metadata: {metadata}")
    if not metadata.get("image_available"):
        print("No image available")
        return

    image = payload.get("image")
    shape = image.get("metadata", {}).get("shape") if isinstance(image, dict) else None
    print(f"Sentinel image shape: {shape}" if shape is not None else "Image available but shape metadata is missing.")


def _test_mapbox_endpoint(endpoint: str, params: Dict[str, Any]) -> None:
    response = _request_get(endpoint, params=params)
    if response is None:
        return

    try:
        metadata = json.loads(response.headers.get("mapbox_metadata", ""))
    except json.JSONDecodeError:
        metadata = None

    print(f"Mapbox metadata: {metadata}")
    if not metadata.get("image_available"):
        print("No image available")
        return

    _show_png(response.content, "Mapbox image")


def test_sentinel_current() -> None:
    params = {
        "spectral_bands": ["red", "green", "blue"],
        "size_km": 10.0,
        "return_type": "png",
        #"window_seconds": 60.0
    }
    _test_sentinel_endpoint("/data/current/image/sentinel", params=params)


def test_sentinel() -> None:
    params = {
        "lon": 6.6323,
        "lat": 46.5197,
        "timestamp": "2026-03-01T16:00:00Z",
        "spectral_bands": ["red", "green", "blue"],
        "size_km": 5.0,
        "return_type": "png",
        #"window_seconds": 60.0
    }
    _test_sentinel_endpoint("/data/image/sentinel", params=params)


def test_sentinel_multispectral() -> None:
    band_sets: List[List[str]] = [
        ["red", "green", "blue"],
        ["nir", "red", "green"],
        ["swir22", "nir", "green"],
        ["swir22", "swir16", "red"],
        ["rededge1", "rededge2", "rededge3"],
    ]

    # Freeze location (and timestamp when available) once so every band set
    # is requested at the exact same satellite coordinates.
    position_response = _request_get("/data/current/position")
    if position_response is None:
        return
    try:
        position_data = position_response.json()
    except ValueError:
        print("Invalid JSON body for /data/current/position.")
        return

    lon_lat_alt = position_data.get("lon-lat-alt")
    timestamp = position_data.get("timestamp")

    images = []
    for spectral_bands in band_sets:
        params = {
            "lon": lon_lat_alt[0],
            "lat": lon_lat_alt[1],
            "timestamp": timestamp,
            "spectral_bands": spectral_bands,
            "size_km": 5.0,
            "return_type": "png",
            #"window_seconds": 60.0
        }
        response = _request_get("/data/image/sentinel", params=params)
        if response is None:
            continue

        try:
            metadata = json.loads(response.headers.get("sentinel_metadata", ""))
        except json.JSONDecodeError:
            metadata = None

        if not isinstance(metadata, dict) or not metadata.get("image_available"):
            print(f"No image available for bands {spectral_bands}")
            continue

        try:
            image = mpimg.imread(io.BytesIO(response.content), format="PNG")
        except Exception as exc:
            print(f"Could not decode image for bands {spectral_bands}: {exc}")
            continue

        images.append((image, "_".join(spectral_bands)))

    if not images:
        print("No hyperspectral images available to display.")
        return

    n_images = len(images)
    fig, axes = plt.subplots(1, n_images, figsize=(5 * n_images, 5))
    if n_images == 1:
        axes = [axes]

    for axis, (image, bands_label) in zip(axes, images):
        axis.imshow(image)
        axis.set_title(f"Bands: {bands_label}")
        axis.axis("off")
    plt.tight_layout()
    plt.show()


def test_mapbox_current() -> None:
    params = {
        #"lon": 6.6323,
        #"lat": 46.5197,
    }
    _test_mapbox_endpoint("/data/current/image/mapbox", params)


def test_mapbox() -> None:
    params = {
        "lon_target": 6.6323,
        "lat_target": 46.5197,
        "lon_satellite": 6.6323,
        "lat_satellite": 46.5197,
        "alt_satellite": 500,
    }
    _test_mapbox_endpoint("/data/image/mapbox", params)


if __name__ == "__main__":
    tests = {
        "sentinel": test_sentinel,
        "sentinel_current": test_sentinel_current,
        "sentinel_multispectral": test_sentinel_multispectral,
        "mapbox": test_mapbox,
        "mapbox_current": test_mapbox_current,
    }

    parser = argparse.ArgumentParser(description="Run API test functions.")
    parser.add_argument("test", nargs="?", default="sentinel_current", choices=sorted(tests.keys()))
    args = parser.parse_args()
    tests[args.test]()