"""
AquaVeritas — GGUF Conversion on Modal
========================================
Reads the fine-tuned LFM2.5-VL-450M checkpoint from the aquaveritas-data
Modal volume, converts to GGUF via llama.cpp, quantises backbone to Q8_0,
keeps mmproj at F16, then pushes both files to Arty1001/aquaveritas-lfm-GGUF.

Run: cd /Users/ml_labs/claudey/SimSat && modal run aquaveritas/scripts/convert_gguf_modal.py
"""

import modal

# ── Constants ─────────────────────────────────────────────────────────────────

RUN_DIR = (
    "LFM2.5-VL-450M-vlm_sft-train.json-all-lr2em05-w0p1-no_lora-20260504_125054"
)
HF_REPO      = "Arty1001/aquaveritas-lfm-GGUF"
HF_TOKEN     = "hf_<redacted>"
VOLUME_NAME  = "aquaveritas-data"
GGUF_SUBDIR  = "gguf"

# ── Modal image: Debian slim + llama.cpp built from source ────────────────────

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install(
        "git", "cmake", "build-essential", "ninja-build", "libcurl4-openssl-dev"
    )
    .run_commands(
        # Clone llama.cpp (latest main — LFM2-VL support is recent)
        "git clone --depth 1 https://github.com/ggerganov/llama.cpp /llama.cpp",
        # Build only llama-quantize (fast — no GPU needed)
        "cmake -B /llama.cpp/build -S /llama.cpp "
        "  -DGGML_NATIVE=OFF "
        "  -DCMAKE_BUILD_TYPE=Release "
        "  -DLLAMA_BUILD_TESTS=OFF "
        "  -DLLAMA_BUILD_EXAMPLES=OFF",
        "cmake --build /llama.cpp/build --config Release -j $(nproc) --target llama-quantize",
        # Python deps for convert_hf_to_gguf.py
        "pip install -r /llama.cpp/requirements/requirements-convert_hf_to_gguf.txt",
        "pip install huggingface_hub",
    )
)

app    = modal.App("aquaveritas-gguf")
volume = modal.Volume.from_name(VOLUME_NAME)


# ── Conversion function ───────────────────────────────────────────────────────

@app.function(
    image=image,
    volumes={"/data": volume},
    cpu=8,
    memory=32768,
    timeout=3600,
)
def convert_and_quantize():
    import os, subprocess

    model_dir = f"/data/{RUN_DIR}"
    gguf_dir  = f"/data/{GGUF_SUBDIR}"
    os.makedirs(gguf_dir, exist_ok=True)

    def run(cmd, **kw):
        print(f"\n$ {' '.join(str(c) for c in cmd)}")
        subprocess.run(cmd, check=True, **kw)

    def ls(path):
        print(f"\nFiles in {path}:")
        for f in sorted(os.listdir(path)):
            mb = os.path.getsize(f"{path}/{f}") / 1024**2
            print(f"  {f:60s}  {mb:8.1f} MB")

    # ── Step 1: HF safetensors → F16 GGUF ────────────────────────────────────
    print("=" * 60)
    print("STEP 1: convert_hf_to_gguf — F16")
    print("=" * 60)
    run([
        "python3", "/llama.cpp/convert_hf_to_gguf.py",
        model_dir,
        "--outtype", "f16",
        "--outfile", f"{gguf_dir}/aquaveritas-lfm-f16.gguf",
    ])
    ls(gguf_dir)

    # ── Step 2: Quantise backbone to Q8_0 ────────────────────────────────────
    # Backbone file — skip anything named mmproj (keep those at F16)
    backbone_f16  = f"{gguf_dir}/aquaveritas-lfm-f16.gguf"
    backbone_q8   = f"{gguf_dir}/aquaveritas-lfm-q8_0.gguf"

    # Detect whether convert produced a separate mmproj file
    produced = os.listdir(gguf_dir)
    mmproj_files = [f for f in produced if "mmproj" in f.lower()]
    backbone_files = [f for f in produced if "mmproj" not in f.lower() and f.endswith(".gguf")]

    print(f"\nDetected backbone files : {backbone_files}")
    print(f"Detected mmproj files   : {mmproj_files}")

    if os.path.exists(backbone_f16):
        print("\n" + "=" * 60)
        print("STEP 2: llama-quantize — Q8_0")
        print("=" * 60)
        run([
            "/llama.cpp/build/bin/llama-quantize",
            backbone_f16,
            backbone_q8,
            "Q8_0",
        ])
        # Remove the intermediate F16 backbone to save space
        os.remove(backbone_f16)
        print(f"Removed intermediate F16 backbone ({backbone_f16})")
    else:
        print(f"WARNING: expected backbone at {backbone_f16} — skipping Q8_0 step")

    ls(gguf_dir)

    # ── Step 3: Push to HuggingFace ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"STEP 3: Push to HuggingFace — {HF_REPO}")
    print("=" * 60)

    push_script = f"""
from huggingface_hub import HfApi
import os

api = HfApi(token="{HF_TOKEN}")
api.create_repo("{HF_REPO}", repo_type="model", exist_ok=True, private=False)

gguf_dir = "{gguf_dir}"
for fname in sorted(os.listdir(gguf_dir)):
    fpath = f"{{gguf_dir}}/{{fname}}"
    size_mb = os.path.getsize(fpath) / 1024**2
    print(f"Uploading {{fname}} ({{size_mb:.1f}} MB)...")
    api.upload_file(
        path_or_fileobj=fpath,
        path_in_repo=fname,
        repo_id="{HF_REPO}",
        repo_type="model",
    )
    print(f"  ✓ {{fname}}")

print("\\nAll files pushed to https://huggingface.co/{HF_REPO}")
"""
    run(["python3", "-c", push_script])

    # Persist changes to volume
    volume.commit()
    print("\n✓ GGUF conversion complete. Files saved to Modal volume and HuggingFace.")


# ── Entry point ───────────────────────────────────────────────────────────────

@app.local_entrypoint()
def main():
    convert_and_quantize.remote()
