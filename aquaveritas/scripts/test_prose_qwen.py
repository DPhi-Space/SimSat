"""
test_prose_qwen.py — Probe Qwen2.5-1.5B-Instruct for mission-brief prose generation.

Tests the agreed 3-part format (water body / buffer / Assessment) against the
Lake Chad example prediction. Compares 3 prompt styles to find the best elicitor.

Usage:
    # 1. Start llama-server with Qwen:
    #    llama-server -m data/models/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf \
    #        --port 8080 --ctx-size 8192 -ngl 99 --host 127.0.0.1 --log-disable
    #
    # 2. Run:
    #    python scripts/test_prose_qwen.py
"""

import json
import textwrap
from openai import OpenAI

LLAMA_URL = "http://localhost:8080"
client = OpenAI(base_url=f"{LLAMA_URL}/v1", api_key="none", timeout=60.0)

# ── Example prediction (Lake Chad 2026-05-05) ─────────────────────────────────

LOCATION = "Lake Chad"
DATE     = "2026-05-05"
CORE = {
    "water_extent_status":    "shrinking",
    "flood_risk":             "none",
    "water_clarity":          "turbid",
    "shoreline_encroachment": True,
    "image_quality_limited":  False,
}
BUFFER = {
    "agriculture_present":               True,
    "crop_stress_level":                 "severe",
    "crop_stress_type":                  "drought",
    "cultivation_expanding_toward_water": True,
    "settlement_visible":                False,
    "bare_soil_expansion":               True,
    "image_quality_limited":             False,
}

PAYLOAD = json.dumps({"location": LOCATION, "date": DATE, "core": CORE, "buffer": BUFFER}, indent=2)

# ── Target output (agreed format for reference) ───────────────────────────────

TARGET = """
LAKE CHAD · 2026-05-05

Lake Chad's water extent is actively shrinking, with turbid clarity and confirmed
shoreline encroachment — the lake edge is retreating and its boundary is being
re-drawn. There is no active flood risk.

The surrounding buffer shows severe drought-stress across agricultural land, with
cultivation actively expanding toward the receding waterline. No settlements are
visible, but bare soil exposure is widespread — consistent with desiccation and
abandonment pressure.

**Assessment:** Lake Chad is exhibiting dual-vector stress — the lake is
contracting while cultivation around it expands. The retreating shoreline is not
recovering land; it is being absorbed by agriculture. Net water area is under
immense pressure.
""".strip()

# ── Prompt variants ───────────────────────────────────────────────────────────

SYSTEM_BASE = (
    "You are a satellite freshwater monitoring analyst. "
    "You write concise mission briefs from structured classification data. "
    "Format: location header, water body paragraph (2–3 sentences), "
    "buffer zone paragraph (2–3 sentences), bold Assessment line (1–2 sentences). "
    "Write in plain, precise prose. No bullet points. No hedging."
)

PROMPTS = [
    {
        "name": "Style 1 — Minimal system, JSON in user turn",
        "system": SYSTEM_BASE,
        "user": f"Write a mission brief for this satellite observation:\n\n{PAYLOAD}",
    },
    {
        "name": "Style 2 — Explicit format in system, JSON in user turn",
        "system": (
            "You are a satellite freshwater monitoring analyst writing mission briefs.\n\n"
            "Output format (follow exactly):\n"
            "[LOCATION · DATE]\n\n"
            "[Water body paragraph — what the lake/river is doing: extent, clarity, flood risk, shoreline]\n\n"
            "[Buffer zone paragraph — what surrounds it: crops, stress, settlement, bare soil]\n\n"
            "**Assessment:** [One or two sentences synthesising both zones and the key risk.]\n\n"
            "Rules: plain prose only, no bullet points, no hedging language, precise and understated."
        ),
        "user": f"Classification data:\n\n{PAYLOAD}",
    },
    {
        "name": "Style 3 — Few-shot with Aral Sea example",
        "system": SYSTEM_BASE,
        "user": textwrap.dedent(f"""
            Example input:
            {{"location":"Aral Sea","date":"2026-04-01","core":{{"water_extent_status":"dry","flood_risk":"none","water_clarity":"poor","shoreline_encroachment":false,"image_quality_limited":false}},"buffer":{{"agriculture_present":false,"crop_stress_level":"none","crop_stress_type":"none","cultivation_expanding_toward_water":false,"settlement_visible":false,"bare_soil_expansion":true,"image_quality_limited":false}}}}

            Example output:
            ARAL SEA · 2026-04-01

            The water body is effectively dry with poor water clarity and no active flood risk. Shoreline encroachment is not confirmed — there is no remaining shoreline to encroach upon.

            The surrounding buffer shows no agricultural activity or human settlement. Bare soil expansion is widespread, consistent with the exposed former lakebed.

            **Assessment:** The Aral Sea remains in terminal recession. Bare soil expansion across the buffer reflects the progressive desiccation of the basin with no indicators of recovery.

            ---

            Now write the brief for this observation:
            {PAYLOAD}
        """).strip(),
    },
]

# ── Run tests ─────────────────────────────────────────────────────────────────

def run_prompt(prompt: dict, temperature: float = 0.3) -> str:
    response = client.chat.completions.create(
        model="local",
        messages=[
            {"role": "system", "content": prompt["system"]},
            {"role": "user",   "content": prompt["user"]},
        ],
        max_tokens=350,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


def divider(char="─", width=72):
    print(char * width)


print()
divider("═")
print(f"  Qwen2.5-1.5B-Instruct prose test — {LOCATION} {DATE}")
divider("═")
print("\n  TARGET OUTPUT (agreed format):")
divider("·")
print(TARGET)
divider("·")

for i, prompt in enumerate(PROMPTS, 1):
    print(f"\n[{i}/3] {prompt['name']}")
    divider()
    try:
        output = run_prompt(prompt)
        print(output)
    except Exception as e:
        print(f"ERROR: {e}")
    divider()
    print()

print("Done.")
