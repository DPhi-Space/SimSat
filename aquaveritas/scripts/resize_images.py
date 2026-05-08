"""
Image Pre-processor
-------------------
Walks data/images/ and resizes any PNG that exceeds the API byte or pixel
limit in-place. Run once after collect_data.py and before label_data.py.

Limits applied:
  - Max file size : 4 MB  (Anthropic hard limit is 5 MB; 4 MB gives safe margin)
  - Max dimension : 1024 px  (Claude vision processes at 1568 px max internally)

LM Studio backends do not enforce the 5 MB cap, but smaller images are faster
and cheaper regardless of backend.

Usage:
    python scripts/resize_images.py
    python scripts/resize_images.py --images-dir /path/to/images
    python scripts/resize_images.py --max-bytes 4194304 --max-px 1024
    python scripts/resize_images.py --dry-run
"""

import argparse
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image
from tqdm import tqdm

# Defaults
# Primary gate: file size over 4 MB (Anthropic limit is 5 MB; 4 MB is safe margin)
# Pixel cap: applied only to images that are already over the byte limit,
#            to bring them under it — not applied independently to small images.
_DEFAULT_MAX_BYTES = 4 * 1024 * 1024   # 4 MB
_DEFAULT_MAX_PX    = 1024


def resize_one(path: Path, max_bytes: int, max_px: int, dry_run: bool) -> str:
    """Resize a single PNG in-place. Returns a status string.

    Only resizes when the file exceeds max_bytes. The max_px cap is applied
    during the resize to bring the file under the byte limit; images already
    within the byte limit are left untouched regardless of their dimensions.
    """
    size = path.stat().st_size
    if size <= max_bytes:
        return "ok"

    if dry_run:
        return f"would resize ({size / 1024 / 1024:.1f} MB)"

    try:
        img = Image.open(path).convert("RGB")
        w, h = img.size

        if max(w, h) > max_px:
            scale = max_px / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()

        # If still oversized after spatial downsample, keep halving
        while len(data) > max_bytes and max(img.size) > 256:
            w2, h2 = img.size
            img = img.resize((w2 // 2, h2 // 2), Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="PNG", optimize=True)
            data = buf.getvalue()

        path.write_bytes(data)
        return f"resized ({size / 1024 / 1024:.1f} MB → {len(data) / 1024 / 1024:.1f} MB)"

    except Exception as exc:
        return f"error ({exc})"


def main():
    parser = argparse.ArgumentParser(description="Resize oversized satellite PNGs in-place")
    parser.add_argument(
        "--images-dir", default=None,
        help="Root images directory (default: data/images/ next to this script)",
    )
    parser.add_argument(
        "--max-bytes", type=int, default=_DEFAULT_MAX_BYTES,
        help=f"Max file size in bytes before resize (default: {_DEFAULT_MAX_BYTES})",
    )
    parser.add_argument(
        "--max-px", type=int, default=_DEFAULT_MAX_PX,
        help=f"Max image dimension in pixels (default: {_DEFAULT_MAX_PX})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would be resized without writing any files",
    )
    args = parser.parse_args()

    if args.images_dir:
        images_root = Path(args.images_dir)
    else:
        images_root = Path(__file__).parent.parent / "data" / "images"

    if not images_root.exists():
        print(f"Images directory not found: {images_root}", file=sys.stderr)
        sys.exit(1)

    pngs = sorted(images_root.rglob("*.png"))
    if not pngs:
        print("No PNG files found.")
        return

    if args.dry_run:
        print(f"DRY RUN — {len(pngs)} PNGs found, checking limits "
              f"(>{args.max_bytes // 1024 // 1024} MB or >{args.max_px} px)…")
    else:
        print(f"Processing {len(pngs)} PNGs "
              f"(limit: {args.max_bytes // 1024 // 1024} MB / {args.max_px} px)…")

    counters = {"ok": 0, "resized": 0, "skipped": 0, "error": 0}

    for png in tqdm(pngs, unit="img"):
        status = resize_one(png, args.max_bytes, args.max_px, args.dry_run)
        if status == "ok":
            counters["ok"] += 1
        elif status.startswith("resized") or status.startswith("would"):
            counters["resized"] += 1
            tqdm.write(f"  {png.relative_to(images_root)}: {status}")
        elif status.startswith("skip"):
            counters["skipped"] += 1
            tqdm.write(f"  {png.relative_to(images_root)}: {status}")
        else:
            counters["error"] += 1
            tqdm.write(f"  ERROR {png.relative_to(images_root)}: {status}")

    label = "Would resize" if args.dry_run else "Resized"
    print(f"\nDone — {counters['ok']} already within limits, "
          f"{label.lower()}: {counters['resized']}, "
          f"skipped: {counters['skipped']}, errors: {counters['error']}")


if __name__ == "__main__":
    main()
