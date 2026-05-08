"""
prose.py — Mission-brief prose generation for AquaVeritas predictions.

Converts structured JSON classification output (core + buffer zone) into
concise, analyst-grade mission-brief prose using Claude Haiku.

Designed to be swappable: the `generate_prose()` function accepts an optional
`client` argument so the backend can be replaced (e.g. local llama-server via
OpenAI-compatible API) without changing call sites.

Usage:
    from aquaveritas.prose import generate_prose

    brief = generate_prose(
        location="Lake Chad",
        date="2026-05-05",
        core=core_result,
        buffer=buffer_result,
    )
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# System prompt — agreed format from AquaVeritas design session 2026-05-05
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a satellite freshwater monitoring analyst writing mission briefs.

Output format — follow exactly, no deviation:

[LOCATION · DATE]

[Water body paragraph — 2–3 sentences. Cover: water extent status, clarity,
flood risk, and shoreline encroachment. Be specific about what the data shows.]

[Buffer zone paragraph — 2–3 sentences. Cover: agriculture presence, crop
stress level and type, cultivation encroachment toward water, settlement
visibility, and bare soil expansion.]

**Assessment:** [1–2 sentences synthesising both zones into a single risk
statement. Name the dominant threat and its direction of travel.]

Rules:
- Plain precise prose only. No bullet points. No hedging language.
- Past/present tense as appropriate for satellite observation data.
- Understated tone — let the data speak.
- Do not repeat the format labels (do not write "Water body paragraph:").
- If image_quality_limited is true for a zone, note it briefly in that paragraph.
"""

_USER_TEMPLATE = "Classification data:\n\n{payload}"

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_CLOUD_DEGRADED_PREFIX = (
    "Note: imagery quality is limited due to significant cloud cover. "
    "Acknowledge this briefly at the start of the water body paragraph "
    "(one clause is enough — do not dwell on it). "
    "Still write all three paragraphs but omit the **Assessment:** line entirely.\n\n"
)


def generate_prose(
    location: str,
    date: str,
    core: dict[str, Any] | None,
    buffer: dict[str, Any] | None,
    *,
    client=None,
    model: str = "claude-haiku-4-5",
    max_tokens: int = 400,
    temperature: float = 0.3,
    cloud_degraded: bool = False,
) -> str:
    """
    Generate a mission-brief prose narrative from structured prediction fields.

    Args:
        location:       Water body name (e.g. "Lake Chad")
        date:           Acquisition date string (e.g. "2026-05-05")
        core:           Core zone prediction dict, or None if unavailable
        buffer:         Buffer zone prediction dict, or None if unavailable
        client:         Optional pre-constructed Anthropic client. If None, one is
                        created from ANTHROPIC_API_KEY in the environment.
        model:          Claude model ID (default: claude-haiku-4-5 — fast, cheap)
        max_tokens:     Maximum tokens in response (default: 400)
        temperature:    Sampling temperature (default: 0.3 — consistent format)
        cloud_degraded: If True, prepends a cloud-cover caveat to the system
                        prompt and suppresses the Assessment line.

    Returns:
        Prose string ready for display. Returns an empty string if both core
        and buffer are None. Returns a fallback message on API error.
    """
    if core is None and buffer is None:
        return ""

    payload = json.dumps(
        {
            "location": location,
            "date": date,
            "core": core or {},
            "buffer": buffer or {},
        },
        indent=2,
    )

    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=_get_api_key() or None)

    system = (_CLOUD_DEGRADED_PREFIX + _SYSTEM_PROMPT) if cloud_degraded else _SYSTEM_PROMPT

    try:
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[
                {"role": "user", "content": _USER_TEMPLATE.format(payload=payload)}
            ],
        )
        return msg.content[0].text.strip()

    except Exception as exc:  # noqa: BLE001
        return f"[Prose generation unavailable: {exc}]"


def estimate_cloud_fraction(image_bytes: bytes, threshold: int = 238) -> float:
    """
    Estimate the fraction of near-white (cloud-covered) pixels in a satellite image.

    Sentinel-2 RGB tiles render cloud as bright-white. Pixels where all three
    channels exceed `threshold` (0-255) are counted as cloud.

    Args:
        image_bytes: Raw PNG/JPEG bytes of the RGB tile.
        threshold:   Per-channel brightness cutoff (default 238 ≈ 93% white).

    Returns:
        Float in [0.0, 1.0]. Values above ~0.50 indicate significant cloud cover.
        Returns 0.0 if the image cannot be decoded (fail-open — don't block inference).
    """
    try:
        from PIL import Image
        import numpy as np

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(img, dtype=np.uint8)
        white = (arr[:, :, 0] > threshold) & (arr[:, :, 1] > threshold) & (arr[:, :, 2] > threshold)
        return float(white.mean())
    except Exception:
        return 0.0


CLOUD_FRACTION_WARN  = 0.40   # ≥40 % → show warning banner, classify as low-confidence
CLOUD_FRACTION_BLOCK = 0.65   # ≥65 % → skip prose entirely, image too degraded


def _get_api_key() -> str:
    """
    Resolve the Anthropic API key from all available sources, in priority order:
    1. ANTHROPIC_API_KEY env var (if non-empty)
    2. The project .env file (read directly via dotenv_values to bypass
       override=False issues when the var exists as an empty string in env)
    3. ANTHROPIC_AUTH_TOKEN env var
    Returns empty string if not found.
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key and key.startswith("sk-"):
        return key

    # Walk up from this file to find the project .env
    _here = Path(__file__).resolve()
    for parent in _here.parents:
        env_path = parent / ".env"
        if env_path.exists():
            try:
                from dotenv import dotenv_values
                vals = dotenv_values(str(env_path))
                k = vals.get("ANTHROPIC_API_KEY", "").strip()
                if k and k.startswith("sk-"):
                    return k
            except ImportError:
                pass
            break   # stop at first .env found regardless

    return os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip()


def _prose_available() -> bool:
    """Return True if a usable Anthropic API key is present."""
    return bool(_get_api_key())
