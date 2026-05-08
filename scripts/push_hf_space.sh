#!/usr/bin/env bash
# push_hf_space.sh — Export SQLite snapshot and push hf_space/ to HuggingFace
#
# Usage:
#   bash scripts/push_hf_space.sh
#
# Prerequisites:
#   - huggingface-cli logged in (huggingface-cli login)
#   - Local PostgreSQL running with aquaveritas database populated
#   - DATABASE_URL set (or defaults from aquaveritas/.env)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HF_SPACE_DIR="$REPO_ROOT/aquaveritas/hf_space"
HF_REPO="Arty1001/aquaveritas"

echo "==> Exporting PostgreSQL -> SQLite"
cd "$REPO_ROOT"
python aquaveritas/scripts/export_sqlite.py

echo "==> SQLite written to $HF_SPACE_DIR/data/observations.db"
ls -lh "$HF_SPACE_DIR/data/observations.db"

echo "==> Pushing hf_space/ to HuggingFace Space: $HF_REPO"
huggingface-cli upload "$HF_REPO" "$HF_SPACE_DIR" . \
  --repo-type space \
  --commit-message "Update space: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "==> Done. Space will rebuild at https://huggingface.co/spaces/$HF_REPO"
