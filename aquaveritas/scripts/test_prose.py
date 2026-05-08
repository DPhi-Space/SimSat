"""
test_prose.py — Probe LFM2.5-VL-450M base model for narrative generation quality.

Tests three prompt styles against the Lake Chad example prediction to find
which elicits the best mission-brief prose from the 450M model.

Usage:
    python scripts/test_prose.py
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

# ── Prompt variants ───────────────────────────────────────────────────────────

PROMPTS = [
    {
        "name": "Style 1 — Direct instruction, minimal scaffolding",
        "system": (
            "You are a satellite freshwater monitoring analyst. "
            "Write a concise mission-brief assessment from structured satellite classification data. "
            "Use three parts: water body status, buffer zone status, and a one-sentence Assessment. "
            "Be precise and understated. No bullet points."
        ),
        "user": (
            f"Write a mission-brief assessment for the following satellite observation:\n\n"
            f"{PAYLOAD}"
        ),
    },
    {
        "name": "Style 2 — Few-shot with structure labels",
        "system": (
            "You are a satellite freshwater monitoring analyst writing mission briefs. "
            "Each brief has three sections: the water body paragraph, the buffer zone paragraph, "
            "and a bold Assessment line. Write in plain, precise prose. No bullet points."
        ),
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
    {
        "name": "Style 3 — Role + output format specified explicitly",
        "system": (
            "You are an environmental intelligence analyst specialising in satellite-derived "
            "freshwater monitoring. Given JSON classification fields from a Sentinel-2 observation, "
            "produce a structured brief in this exact format:\n\n"
            "[LOCATION · DATE]\n\n"
            "[Water body paragraph — 2 sentences max]\n\n"
            "[Buffer zone paragraph — 2 sentences max]\n\n"
            "**Assessment:** [One sentence synthesising both zones and the key risk.]\n\n"
            "Write with precision. No hedging. No bullets."
        ),
        "user": f"Classification data:\n\n{PAYLOAD}",
    },
]

# ── Run tests ─────────────────────────────────────────────────────────────────

def run_prompt(prompt: dict) -> str:
    response = client.chat.completions.create(
        model="local",
        messages=[
            {"role": "system",  "content": prompt["system"]},
            {"role": "user",    "content": prompt["user"]},
        ],
        max_tokens=300,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def divider(char="─", width=72):
    print(char * width)


print()
divider("═")
print(f"  LFM2.5-VL-450M prose test — {LOCATION} {DATE}")
divider("═")

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
