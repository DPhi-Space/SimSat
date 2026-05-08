"""Claude oracle annotator — labels satellite images with structured JSON."""

import base64
import json
import os
import re
import time
from typing import Optional

import anthropic

from .locations import Location

ORACLE_MODEL = "claude-opus-4-6"

# ── System prompts ─────────────────────────────────────────────────────────────

CORE_SYSTEM = """\
You are an expert remote sensing analyst specialising in freshwater body monitoring.
You are analysing Sentinel-2 satellite imagery of {name} (lat {lat}°, lon {lon}°).

LOCATION CONTEXT:
{description}

BASELINE: {expected_water_status}

You will receive two images, each covering a 15km × 15km area organised as a \
3×3 grid of 5km × 5km sub-tiles. The coordinate is positioned at the water/land \
boundary so the tile captures open water, the shoreline transition, and the \
adjacent land within a single view.

1. RGB true-colour composite (red/green/blue bands, 15km tile)
2. SWIR false-colour composite (swir16/nir/red bands, 15km tile)
   - Dark / black  = open water (SWIR strongly absorbed by water)
   - Bright green  = healthy, well-watered vegetation
   - Amber / yellow = moderate moisture stress
   - Magenta / pink = bare soil or dried lakebed
   - Deep red/brown = severely stressed or dead vegetation
   - White / pale   = cloud or salt flat

Focus your assessment on the water body portion of the tile. \
Analyse both images and respond with ONLY a valid JSON object — no prose, no markdown fences:
{{
  "water_extent_status": "shrinking|stable|flooded|recovering|dry",
  "flood_risk": "none|elevated|active",
  "water_clarity": "clear|turbid|heavily_silted",
  "shoreline_encroachment": true|false,
  "image_quality_limited": true|false
}}

Set image_quality_limited to true if cloud cover obscures >50% of the water body \
or if the image is clearly unusable.
"""

BUFFER_SYSTEM = """\
You are an expert remote sensing analyst specialising in agricultural stress monitoring.
You are analysing Sentinel-2 satellite imagery of the land surrounding \
{name} (lat {lat}°, lon {lon}°).

LOCATION CONTEXT:
{description}

You will receive two images, each covering a 15km × 15km area organised as a \
3×3 grid of 5km × 5km sub-tiles. The coordinate is at the water/land boundary, \
so the tile shows both the lake margin and the surrounding agricultural zone.

1. RGB true-colour composite (red/green/blue bands, 15km tile)
   - Shows field patterns, roads, settlements, irrigation canals, land use change
2. SWIR false-colour composite (swir16/nir/red bands, 15km tile)
   - Bright green  = healthy, well-watered crops or natural vegetation
   - Amber / yellow = moderate moisture stress in crops
   - Magenta / pink = bare soil, recently harvested, or dry fields
   - Deep red/brown = severe crop stress or crop failure
   - Dark / black   = open water, irrigation canals

Focus your assessment on the agricultural land portion of the tile. \
Analyse both images and respond with ONLY a valid JSON object — no prose, no markdown fences:
{{
  "agriculture_present": true|false,
  "crop_stress_level": "none|low|moderate|severe",
  "crop_stress_type": "drought|flood_damage|none",
  "cultivation_expanding_toward_water": true|false,
  "settlement_visible": true|false,
  "bare_soil_expansion": true|false,
  "image_quality_limited": true|false
}}
"""


# ── Annotator class ────────────────────────────────────────────────────────────

class Annotator:
    def __init__(self, model: str = ORACLE_MODEL):
        self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self.model  = model

    def annotate_core(
        self,
        rgb_bytes:  bytes,
        swir_bytes: bytes,
        location:   Location,
    ) -> Optional[dict]:
        """Label the core (5km) zone — returns water body JSON or None."""
        system = CORE_SYSTEM.format(
            name                  = location.name,
            lat                   = location.lat,
            lon                   = location.lon,
            description           = location.description,
            expected_water_status = location.expected_water_status,
        )
        return self._call(system, rgb_bytes, swir_bytes)

    def annotate_buffer(
        self,
        rgb_bytes:  bytes,
        swir_bytes: bytes,
        location:   Location,
    ) -> Optional[dict]:
        """Label the buffer (10km) zone — returns agricultural JSON or None."""
        system = BUFFER_SYSTEM.format(
            name        = location.name,
            lat         = location.lat,
            lon         = location.lon,
            description = location.description,
        )
        return self._call(system, rgb_bytes, swir_bytes)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _call(
        self,
        system:     str,
        rgb_bytes:  bytes,
        swir_bytes: bytes,
        retries:    int = 2,
    ) -> Optional[dict]:
        for attempt in range(retries):
            try:
                msg = self.client.messages.create(
                    model      = self.model,
                    max_tokens = 512,
                    system     = system,
                    messages   = [{
                        "role":    "user",
                        "content": [
                            _image_block(rgb_bytes),
                            _image_block(swir_bytes),
                            {"type": "text", "text": "Analyse these two satellite images and return the JSON assessment."},
                        ],
                    }],
                )
                result = _parse_json(msg.content[0].text)
                if result is not None:
                    return result
            except anthropic.RateLimitError:
                time.sleep(30 * (attempt + 1))
            except anthropic.APIError:
                if attempt == retries - 1:
                    raise
                time.sleep(5)
        return None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _encode(image_bytes: bytes) -> str:
    return base64.standard_b64encode(image_bytes).decode("utf-8")


def _image_block(image_bytes: bytes) -> dict:
    return {
        "type": "image",
        "source": {
            "type":       "base64",
            "media_type": "image/png",
            "data":       _encode(image_bytes),
        },
    }


def _parse_json(text: str) -> Optional[dict]:
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None
