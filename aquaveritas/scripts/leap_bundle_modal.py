"""
AquaVeritas — LEAP Bundle Creation on Modal
=============================================
Downloads the fine-tuned checkpoint from the aquaveritas-data Modal volume
and runs `leap-bundle create` to upload to the Liquid AI LEAP inference platform.

Requires a LEAP API token — set LEAP_TOKEN env var or pass via Modal secret.

Run: cd /Users/ml_labs/claudey/SimSat && LEAP_TOKEN=<your-token> modal run aquaveritas/scripts/leap_bundle_modal.py
"""

import modal
import os
import sys

# ── Constants ─────────────────────────────────────────────────────────────────

RUN_DIR     = (
    "LFM2.5-VL-450M-vlm_sft-train.json-all-lr2em05-w0p1-no_lora-20260504_125054"
)
VOLUME_NAME = "aquaveritas-data"
BUNDLE_NAME = "aquaveritas-lfm"

LEAP_TOKEN  = os.environ.get("LEAP_TOKEN", "leap_25c84d84e17c475646cac46b0e676f7b")

# ── Validate token before building anything ───────────────────────────────────

if not LEAP_TOKEN:
    print(
        "\n⚠️  LEAP_TOKEN not set.\n"
        "   Run: leap-bundle login   (browser-based, stores token locally)\n"
        "   Then find your token at: ~/.config/leap_bundle/ or run: leap-bundle whoami\n"
        "   Then re-run with: LEAP_TOKEN=<token> modal run aquaveritas/scripts/leap_bundle_modal.py\n"
    )
    sys.exit(1)

# ── Modal image ───────────────────────────────────────────────────────────────

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("leap-bundle==0.9.0")
)

app    = modal.App("aquaveritas-leap-bundle")
volume = modal.Volume.from_name(VOLUME_NAME)


# ── Bundle function ───────────────────────────────────────────────────────────

@app.function(
    image=image,
    volumes={"/data": volume},
    cpu=4,
    memory=8192,
    timeout=7200,   # 2 hours — upload may be slow
)
def create_bundle(leap_token: str):
    import os, subprocess

    model_dir = f"/data/{RUN_DIR}"

    print("=" * 60)
    print(f"LEAP Bundle: {BUNDLE_NAME}")
    print(f"Source     : {model_dir}")
    print("=" * 60)

    # Write token to ~/.liquid-leap (YAML format, leap-bundle v0.9.0)
    creds_path = os.path.expanduser("~/.liquid-leap")
    with open(creds_path, "w") as f:
        f.write(f"api_token: {leap_token}\nversion: 1\n")
    print("✓ LEAP credentials configured")

    def run(cmd, **kw):
        print(f"\n$ {' '.join(str(c) for c in cmd)}")
        subprocess.run(cmd, check=True, **kw)

    # ── Stage a clean bundle dir (model files only — no optimizer states) ─────
    # The full run dir is ~21 GB (3 epoch checkpoints + DeepSpeed states).
    # LEAP limit is 10 GB. Copy only the files needed for inference.
    BUNDLE_FILES = [
        "model.safetensors",
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "generation_config.json",
        "processor_config.json",
        "chat_template.jinja",
        "special_tokens_map.json",
        "preprocessor_config.json",
    ]
    bundle_dir = "/data/aquaveritas-bundle"
    os.makedirs(bundle_dir, exist_ok=True)

    print(f"\nSTEP 1: Staging clean bundle dir → {bundle_dir}")
    import shutil
    copied = []
    for fname in BUNDLE_FILES:
        src = f"{model_dir}/{fname}"
        dst = f"{bundle_dir}/{fname}"
        if os.path.exists(src):
            shutil.copy2(src, dst)
            size_mb = os.path.getsize(dst) / 1024**2
            print(f"  ✓ {fname}  ({size_mb:.1f} MB)")
            copied.append(fname)
        else:
            print(f"  – {fname}  (not present, skipping)")

    total_mb = sum(
        os.path.getsize(f"{bundle_dir}/{f}") / 1024**2
        for f in os.listdir(bundle_dir)
    )
    print(f"\nBundle dir total: {total_mb:.0f} MB  ({total_mb/1024:.2f} GB)")

    # Validate the clean bundle dir
    print("\nSTEP 2: Validating bundle directory...")
    run(["leap-bundle", "validate", bundle_dir])

    # Create the bundle (uploads to LEAP platform — LEAP handles GGUF conversion)
    print("\nSTEP 3: Creating and uploading bundle...")
    run([
        "leap-bundle", "create",
        bundle_dir,
        "--quantization", "Q8_0",
        "--mmproj-quantization", "f16",
    ])

    print("\n✓ LEAP bundle submitted. Check status with: leap-bundle list")


# ── Entry point ───────────────────────────────────────────────────────────────

@app.local_entrypoint()
def main():
    create_bundle.remote(LEAP_TOKEN)
