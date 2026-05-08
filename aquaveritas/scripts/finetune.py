"""
Fine-tuning — LFM2.5-VL-450M on Modal H100
--------------------------------------------
1. Pulls the JSONL dataset from data/train.jsonl (produced by train.py)
2. Uploads it to a Modal volume
3. Submits a leap-finetune job on Modal H100
4. On completion, quantizes to GGUF and pushes to HuggingFace

Requires:
    - modal token set (run `modal token new`)
    - HF_TOKEN env var set
    - data/train.jsonl and data/test.jsonl present (run train.py first)

Usage:
    python scripts/finetune.py --hf-model-repo YOUR_HF_USERNAME/aquaveritas-lfm
    python scripts/finetune.py --hf-model-repo ... --dry-run
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

DATA_DIR    = Path(__file__).parent.parent / "data"
CONFIGS_DIR = Path(__file__).parent.parent / "configs"
BASE_MODEL  = "liquid-ai/LFM2.5-VL-450M"


def check_prerequisites():
    train_jsonl = DATA_DIR / "train.jsonl"
    if not train_jsonl.exists():
        print("ERROR: data/train.jsonl not found. Run scripts/train.py first.")
        sys.exit(1)

    count = sum(1 for _ in train_jsonl.open())
    print(f"Training examples: {count}")
    if count < 100:
        print("WARNING: fewer than 100 training examples — consider collecting more data.")
    return count


def run_modal_finetune(hf_model_repo: str, dry_run: bool):
    import modal

    app    = modal.App("aquaveritas-finetune")
    volume = modal.Volume.from_name("aquaveritas-data", create_if_missing=True)

    # Upload JSONL files to Modal volume
    print("Uploading dataset to Modal volume…")
    if not dry_run:
        with volume.batch_upload() as batch:
            batch.put_file(DATA_DIR / "train.jsonl", "/data/train.jsonl")
            batch.put_file(DATA_DIR / "test.jsonl",  "/data/test.jsonl")

    # Build fine-tune image
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .pip_install("leap-finetune", "huggingface_hub", "transformers", "torch")
    )

    config_path = CONFIGS_DIR / "aquaveritas_finetune_modal.yaml"

    @app.function(
        image      = image,
        gpu        = modal.gpu.H100(),
        timeout    = 3 * 3600,
        volumes    = {"/data": volume},
        secrets    = [modal.Secret.from_name("huggingface-secret")],
    )
    def train():
        import subprocess
        result = subprocess.run(
            ["leap-finetune", "train", "--config", "/data/finetune_config.yaml"],
            capture_output=False,
            check=True,
        )
        return result.returncode

    # Write config to volume
    config_content = config_path.read_text().replace(
        "OUTPUT_HF_REPO", hf_model_repo
    )

    if dry_run:
        print("Dry run — finetune config preview:")
        print(config_content)
        print("\nWould submit Modal H100 job.")
        return

    if not dry_run:
        with volume.batch_upload() as batch:
            from io import BytesIO
            batch.put_file(BytesIO(config_content.encode()), "/data/finetune_config.yaml")

    print("Submitting fine-tune job on Modal H100…")
    with app.run():
        returncode = train.remote()

    if returncode == 0:
        print(f"Fine-tuning complete. Model pushed to: {hf_model_repo}")
        print("\nNext step: run quantize to create GGUF for llama-server:")
        print(f"  python scripts/finetune.py --quantize --hf-model-repo {hf_model_repo}")
    else:
        print(f"Fine-tuning failed with return code {returncode}")
        sys.exit(1)


def run_quantize(hf_model_repo: str):
    """Download fine-tuned model, quantize to GGUF, push GGUF to HF."""
    from huggingface_hub import snapshot_download, HfApi
    import shutil

    model_dir = DATA_DIR / "finetuned_model"
    gguf_dir  = DATA_DIR / "gguf"
    gguf_dir.mkdir(exist_ok=True)

    print(f"Downloading fine-tuned model from {hf_model_repo}…")
    snapshot_download(hf_model_repo, local_dir=str(model_dir))

    # Use llama.cpp convert script for quantization
    backbone_gguf = gguf_dir / "aquaveritas-backbone-Q8_0.gguf"
    mmproj_gguf   = gguf_dir / "aquaveritas-mmproj-F16.gguf"

    print("Quantizing backbone to Q8_0…")
    subprocess.run([
        sys.executable, "-m", "llama_cpp.convert_hf_to_gguf",
        str(model_dir), "--outfile", str(backbone_gguf), "--outtype", "q8_0",
    ], check=True)

    print("Quantizing vision projector to F16…")
    subprocess.run([
        sys.executable, "-m", "llama_cpp.convert_hf_to_gguf",
        str(model_dir / "mmproj"), "--outfile", str(mmproj_gguf), "--outtype", "f16",
    ], check=True)

    # Push GGUF files to HuggingFace
    gguf_repo = hf_model_repo + "-GGUF"
    api = HfApi()
    api.create_repo(gguf_repo, repo_type="model", exist_ok=True)
    for gguf_file in [backbone_gguf, mmproj_gguf]:
        print(f"Uploading {gguf_file.name} to {gguf_repo}…")
        api.upload_file(
            path_or_fileobj=str(gguf_file),
            path_in_repo=gguf_file.name,
            repo_id=gguf_repo,
        )

    print(f"\nGGUF model available at: https://huggingface.co/{gguf_repo}")
    print("\nTo run locally:")
    print(f"  llama-server \\")
    print(f"    --model {backbone_gguf} \\")
    print(f"    --mmproj {mmproj_gguf} \\")
    print(f"    --port 8080 --ctx-size 4096")


def main():
    parser = argparse.ArgumentParser(description="Fine-tune LFM2.5-VL-450M for AquaVeritas")
    parser.add_argument("--hf-model-repo", required=True,
                        help="HuggingFace model repo for output, e.g. user/aquaveritas-lfm")
    parser.add_argument("--quantize", action="store_true",
                        help="Quantize existing fine-tuned model to GGUF (skip training)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Preview without submitting Modal job")
    args = parser.parse_args()

    if args.quantize:
        run_quantize(args.hf_model_repo)
        return

    n = check_prerequisites()
    print(f"Starting fine-tune of {BASE_MODEL} with {n} examples on Modal H100…")
    run_modal_finetune(args.hf_model_repo, args.dry_run)


if __name__ == "__main__":
    main()
