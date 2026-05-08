# AquaVeritas — Command Reference

Full pipeline from environment setup to live prediction.
All commands run from the `aquaveritas/` directory.

---

## 0. Environment

### Start the stack
```bash
docker compose up -d
```
**Purpose:** Starts PostgreSQL/PostGIS container (port 5433) and SimSat API (port 9005).  
**Sample output:**
```
[+] Running 2/2
 ✔ Container aquaveritas-postgres  Started
 ✔ Container aquaveritas-simsat    Started
```
> **Note (AVS-001):** Port is 5433, not 5432. Homebrew postgres occupies 5432. If you see
> `role "aqua" does not exist`, a local Homebrew postgres is intercepting. Use
> `lsof -i :5432` to check.

### Verify SimSat is reachable
```bash
curl http://localhost:9005/data/current/position
```
**Sample output:**
```json
{"lon-lat-alt": [34.2, 3.5, 512.0], "timestamp": "2021-06-01T08:22:11Z"}
```

### Install Python dependencies
```bash
pip install -e .
```
**Purpose:** Installs the `aquaveritas` package from `src/` in editable mode.

### Configure environment variables (.env)
Copy the example and fill in real values:
```bash
cp .env.example .env
# Edit .env and set:
#   DATABASE_URL=postgresql://aqua:<password>@localhost:5433/aquaveritas
#   ANTHROPIC_API_KEY=sk-ant-...
#   HF_TOKEN=hf_...
#   MAPBOX_TOKEN=pk.eyJ1...
```
> **Note (AVS-042):** `DATABASE_URL` **must** be set in `.env` — there is no hardcoded fallback.
> If the env var is missing, `db.py` raises `RuntimeError` with a descriptive message.
> The `.env` file is gitignored. Never commit credentials to source.

---

## 1. Data Collection

### Collect all 20 locations across 84 months (full training run)
```bash
python scripts/collect_data.py --workers 3
```
**Purpose:** Fetches Sentinel-2 imagery (RGB + SWIR) for every location × month from
2018-01-01 to 2024-12-01. Saves PNGs to `data/images/<location>/<YYYY-MM-DD>/` and
inserts unlabeled observation records into Postgres.  
**Sample output:**
```
Collecting 1680 observations (20 locations × 84 months)
100%|████████████████████| 1680/1680 [1:12:04<00:00,  2.57 obs/s]
Collection complete: {'ok': 1634, 'skipped': 0, 'quality_limited': 26, 'partial': 4, 'error': 0}
```

### Collect a single location
```bash
python scripts/collect_data.py --location lake_chad
```
**Sample output:**
```
Collecting 84 observations (1 locations × 84 months)
100%|████████████████████| 84/84 [03:21<00:00,  2.40 obs/s]
Collection complete: {'ok': 82, 'skipped': 0, 'quality_limited': 2, 'partial': 0, 'error': 0}
```

### Collect a date range
```bash
python scripts/collect_data.py --start 2022-01-01 --end 2022-12-01 --workers 4
```
**Purpose:** Useful for collecting a single year after extending the location list.

### Resume / re-run safely
```bash
python scripts/collect_data.py --workers 3
```
**Purpose:** Fully idempotent. Already-collected observations are skipped (ON CONFLICT DO NOTHING).  
**Sample output:**
```
Collection complete: {'ok': 0, 'skipped': 1680, 'quality_limited': 0, ...}
```

---

## 2. Image Triage (run before labelling)

Triage classifies every collected image into **PASS / MARGINAL / FAIL** before
the labelling model ever sees it. FAILs are excluded from labelling but all
Postgres records and image files are kept intact.

### Pass 1 — Heuristic (fast, no GPU)
```bash
python scripts/triage_images.py --heuristic
```
**Purpose:** PIL/numpy check. Catches black no-data tiles, MGRS tile-boundary artefacts,
and missing files. Emits PASS or FAIL only — cannot assess cloud cover.  
**Sample output:**
```
Triaging 1654 observations [mode=heuristic]
100%|████████████████████| 1654/1654 [02:50<00:00,  9.70 img/s]

Triage complete  (1654 processed)
  PASS      1634  (98.8%)
  MARGINAL     0  (0.0%)
  FAIL        20  (1.2%)  ← excluded from labelling

Database totals: {'fail': 20, 'pass': 1634}
```

### Pass 2 — Vision model re-evaluation of heuristic PASSes
```bash
python scripts/triage_images.py --model lfm2.5-vl-450m-mlx --retriage-heuristic
```
**Purpose:** Sends all 1634 heuristic PASSes to the loaded LM Studio vision model for
fine-grained scoring: cloud cover, water visibility, shoreline, agriculture, spatial
context. Overwrites heuristic PASS verdicts. Heuristic FAILs are never re-evaluated.  
**Sample output:**
```
Model: lfm2.5-vl-450m-mlx
Triaging 1634 heuristic-PASS observations for vision re-evaluation [mode=lmstudio] [--retriage-heuristic]
100%|████████████████████| 1634/1634 [48:12<00:00,  1.77 img/s]

Triage complete  (1634 processed)
  PASS      1489  (91.1%)
  MARGINAL    98  (6.0%)
  FAIL        47  (2.9%)  ← excluded from labelling

Database totals: {'fail': 67, 'marginal': 98, 'pass': 1489}
```

### Specify a different LM Studio model
```bash
python scripts/triage_images.py --model llava-1.6-mistral-7b-gguf --retriage-heuristic
```
**Purpose:** Override the auto-detected model. Useful when comparing multiple vision
models against the same image set.

### Triage a single location only
```bash
python scripts/triage_images.py --heuristic --location congo_delta
```
**Sample output:**
```
Triaging 84 observations [mode=heuristic] [location=congo_delta]
Triage complete  (84 processed)
  PASS      21  (25.0%)
  FAIL      63  (75.0%)  ← excluded from labelling
```

### Dry-run — preview verdicts without writing to DB
```bash
python scripts/triage_images.py --model lfm2.5-vl-450m-mlx --retriage-heuristic --dry-run
```
**Sample output:**
```
  [DRY-RUN] lake_chad                  2018-01-01  →  PASS      Clean water body, shoreline, green agricultural plots visible.
  [DRY-RUN] aral_sea                   2018-01-01  →  MARGINAL  Partial cloud on eastern shoreline, water body visible.
  [DRY-RUN] congo_delta                2019-06-01  →  FAIL      >70% cloud cover, surface not visible.
```

### Export rejection manifest (JSON + CSV)
```bash
python scripts/triage_images.py --export-manifest --export-only
```
**Purpose:** Writes all FAIL-triaged observations to `data/triage/rejection_manifest_<timestamp>.json`
and `.csv`. Files and DB records are unchanged — manifest is audit trail only.  
**Sample output:**
```
Rejection manifest written:
  JSON → data/triage/rejection_manifest_20260503T091500Z.json
  CSV  → data/triage/rejection_manifest_20260503T091500Z.csv
  67 FAIL observations recorded
```

---

## 2b. Image Pre-processing (run after triage, before labelling)

Resizes PNGs that exceed the Anthropic API's 5 MB hard limit. Only images over
4 MB are touched; everything else is left untouched.

### Resize all oversized images in-place
```bash
python scripts/resize_images.py
```
**Purpose:** Walks `data/images/` and resizes any PNG over 4 MB (Anthropic limit is
5 MB; 4 MB gives a safe margin) down to a max 1024 px dimension using LANCZOS.
Images already within limits are skipped.  
**Sample output:**
```
Processing 3367 PNGs (limit: 4 MB / 1024 px)…
  okavango/2018-11-01/rgb_core.png: resized (4.7 MB → 2.1 MB)
  okavango/2019-01-01/rgb_core.png: resized (4.7 MB → 2.2 MB)
  ... (253 okavango images)
Done — 3114 already within limits, resized: 253, skipped: 0, errors: 0
```

### Dry-run — preview what would be resized
```bash
python scripts/resize_images.py --dry-run
```

> **When to run:** Once after `collect_data.py` completes, before `label_data.py`.
> Re-running is safe (already-small images are skipped).  
> **LM Studio backend:** Skip this step when labelling with `--backend lmstudio` —
> LM Studio has no file-size limit.

---

## 3. Labelling

### Label all unlabeled PASS/MARGINAL observations (Claude oracle)
```bash
python scripts/label_data.py
```
**Purpose:** Reads the labelling queue from Postgres (PASS + MARGINAL, excludes FAIL
and already-labelled rows), calls the Claude annotator for each image pair (RGB + SWIR),
and writes structured labels back to the DB.  
**Sample output:**
```
Backend: Anthropic Claude oracle
Labeling 200 observations…
100%|████████████████████| 200/200 [12:44<00:00,  3.82 s/obs]
Labeling complete: {'ok': 195, 'skipped': 3, 'error': 2}
```

### Label using LM Studio (local, no API cost, no 5 MB limit)
```bash
python scripts/label_data.py --backend lmstudio
```
**Purpose:** Uses the locally-running LM Studio server at `http://localhost:8234/v1`
with `zai-org/glm-4.6v-flash` (default). No Anthropic API key needed, no 5 MB limit.
Accuracy is lower than Claude oracle; use for bulk pre-labelling or cost control.  
**Sample output:**
```
Backend: LM Studio (zai-org/glm-4.6v-flash)
Labeling 200 observations…
100%|████████████████████| 200/200 [04:12<00:00,  1.26 s/obs]
Labeling complete: {'ok': 190, 'skipped': 3, 'error': 7}
```

### Label with a specific LM Studio model
```bash
python scripts/label_data.py --backend lmstudio --lmstudio-model google/gemma-4-e4b
```
**Available vision-capable LM Studio models:**
| Model | Notes |
|-------|-------|
| `zai-org/glm-4.6v-flash` | Default — strong instruction following |
| `google/gemma-4-e4b` | Gemma 4 edge, 4B |
| `google/gemma-3n-e4b` | Gemma 3n edge, 4B |
| `google/gemma-3-4b` | Gemma 3, 4B |

### Label a specific location
```bash
python scripts/label_data.py --location lake_chad
```

### Larger batch
```bash
python scripts/label_data.py --batch 500
```
**Purpose:** Increases the max observations fetched per run from the default 200.

---

## 4. Dataset Export

### Export labeled data to HuggingFace Hub
```bash
python scripts/train.py --hf-repo YOUR_HF_USERNAME/aquaveritas-water-stress
```
**Purpose:** Reads all labeled observations from Postgres, formats them as
conversational JSONL (system prompt + two images + assistant JSON), splits into
train (before 2024-01-01) and test (2024-01-01 onwards), and pushes to HuggingFace.  
**Sample output:**
```
Processing 1489 labeled observations…
Train examples: 1280
Test examples:  209
Pushing to hub: YOUR_HF_USERNAME/aquaveritas-water-stress
Dataset pushed successfully.
```

### Dry-run — inspect JSONL without pushing
```bash
python scripts/train.py --hf-repo YOUR_HF_USERNAME/aquaveritas-water-stress --dry-run
```

---

## 5. Fine-tuning

Uses [leap-finetune](https://github.com/LiquidAI/leap-finetune) — full fine-tuning
(not LoRA, `use_peft: false`) on a Modal H100. Full fine-tuning is used because
satellite multispectral imagery is underrepresented in VLM pretraining, so the
multimodal projector needs to genuinely re-learn how to map SWIR/RGB patches into
tokens. At 450M parameters this fits on a single H100 without LoRA.

### Step 1 — Install leap-finetune
```bash
git clone https://github.com/LiquidAI/leap-finetune.git
cd leap-finetune && uv sync && cd ..
```

### Step 2 — Authenticate
```bash
cd leap-finetune
uv run huggingface-cli login   # to pull base model + push fine-tuned model
uv run python -m modal setup   # to submit training job to Modal H100
cd ..
```

### Step 3 — Prepare dataset and push to Modal volume
```bash
python scripts/finetune.py --hf-model-repo YOUR_HF_USERNAME/aquaveritas-lfm
```
**Purpose:** Uploads `data/train.jsonl` and `data/test.jsonl` (produced by `train.py`)
to a Modal volume named `aquaveritas-data`, ready for the training job.  
**Prerequisites:** `modal token new`, `HF_TOKEN` env var, `data/train.jsonl` present
(run `train.py` first).  
**Sample output:**
```
Training examples: 1280
Uploading dataset to Modal volume…
Done. Data ready in volume: aquaveritas-data
```

### Step 4 — Kick off fine-tuning
```bash
cd leap-finetune
uv run leap-finetune ../configs/aquaveritas_finetune_modal.yaml
```
**Purpose:** Submits the training job to Modal's serverless H100 infrastructure.
Downloads the base `LFM2.5-VL-450M` weights from HuggingFace, reads JSONL from the
Modal volume, runs full SFT for the configured epochs, and saves checkpoints back to
the volume.  
**Sample output:**
```
Downloading base model: LiquidAI/LFM2.5-VL-450M
Reading training data from volume: aquaveritas-data
Epoch 1/3: loss=1.842 → 0.431
Epoch 2/3: loss=0.431 → 0.218
Epoch 3/3: loss=0.218 → 0.147
Checkpoint saved to /outputs/aquaveritas-run-20260503/
```

### Step 5 — Retrieve checkpoint from Modal volume
```bash
uv run modal volume ls aquaveritas-data /outputs/
uv run modal volume get aquaveritas-data /outputs/<run-name> ./outputs
```

### Step 6 — Quantize to GGUF (produces two files)
```bash
cd leap-finetune
uv run scripts/quantize.py \
    --checkpoint ./outputs/<run-name>/<checkpoint> \
    --output ./outputs/aquaveritas-lfm-Q8_0.gguf
```
**Output:** Two files in `./outputs/`:
- `aquaveritas-lfm-Q8_0.gguf` — language model backbone (Q8_0)
- `mmproj-aquaveritas-lfm-Q8_0.gguf` — vision tower + projector (always F16)

### Dry-run (dataset validation only)
```bash
python scripts/finetune.py --hf-model-repo YOUR_HF_USERNAME/aquaveritas-lfm --dry-run
```

---

## 6. Evaluation

The evaluation workflow has two backends:

| Backend | Class | What it calls | When to use |
|---|---|---|---|
| `llama` | `LlamaBackend` | `llama-server` at `localhost:8080` loaded with fine-tuned LFM2.5-VL-450M GGUF | Post fine-tune accuracy |
| `claude` | `AnthropicBackend` | Claude claude-opus-4-6 (Anthropic API) | Oracle baseline — the model that generated labels |

### Step 1 — Produce GGUF artifacts from the fine-tune checkpoint

`quantize.py` (from the leap-finetune cookbook) produces **two** GGUF files from
a single checkpoint. Both are required to run llama-server:

```bash
cd leap-finetune
uv run scripts/quantize.py \
    --checkpoint ./outputs/<run-name>/<checkpoint> \
    --output ./outputs/aquaveritas-lfm-Q8_0.gguf
```

| File | Contents | Quant |
|---|---|---|
| `aquaveritas-lfm-Q8_0.gguf` | Language model backbone | Q8_0 (or Q4_K_M etc.) |
| `mmproj-aquaveritas-lfm-Q8_0.gguf` | Vision tower + multimodal projector | Always F16 |

The `mmproj-` file is written automatically to the same directory with `mmproj-`
prepended to the backbone filename. Both files are required — the mmproj encodes
satellite images into visual tokens.

> To use a different backbone quantization: `--quant Q4_K_M` (also `Q4_0`, `Q5_K_M`, `Q6_K`, `F16`).
> The mmproj is always F16 regardless of `--quant`.

### (Optional) Push both GGUFs to HuggingFace
```bash
uv run scripts/push_gguf_to_hf.py \
    --backbone ./outputs/aquaveritas-lfm-Q8_0.gguf \
    --mmproj   ./outputs/mmproj-aquaveritas-lfm-Q8_0.gguf \
    --repo YOUR_HF_USERNAME/aquaveritas-lfm
```

### Step 2 — Start llama-server with both GGUF files

`llama-server` requires both the backbone and the mmproj to serve a VLM:

```bash
llama-server \
    --model  ./outputs/aquaveritas-lfm-Q8_0.gguf \
    --mmproj ./outputs/mmproj-aquaveritas-lfm-Q8_0.gguf \
    --host 0.0.0.0 \
    --port 8080 \
    --ctx-size 8192 \
    -ngl 99
```
**Purpose:** Starts an OpenAI-compatible inference server. `LlamaBackend` in
`evaluator.py` connects to `http://localhost:8080/v1` by default and sends requests
as `model="aquaveritas"`.  
**Sample output:**
```
llama_model_load: loading model from outputs/aquaveritas-lfm-Q8_0.gguf
clip_model_load: loading mmproj from outputs/mmproj-aquaveritas-lfm-Q8_0.gguf
llama server listening at http://0.0.0.0:8080
```

> **Override the URL** via env var if llama-server is on a different host/port:
> ```bash
> export LLAMA_SERVER_URL=http://localhost:8080
> ```

### Step 3 — Evaluate the fine-tuned LFM2.5-VL-450M
```bash
python scripts/evaluate.py --backend llama
```
**Purpose:** Loads the test split (observations from 2024-01-01 onwards) from Postgres,
runs core zone + buffer zone inference via `llama-server` (must be running with both
backbone + mmproj GGUFs loaded — see Step 2), and computes per-field accuracy against
the Claude oracle ground-truth labels stored in the DB.

Fields evaluated:

| Zone | Fields |
|---|---|
| Core (water body) | `water_extent_status`, `flood_risk`, `water_clarity`, `shoreline_encroachment` |
| Buffer (agriculture) | `agriculture_present`, `crop_stress_level`, `crop_stress_type`, `cultivation_expanding_toward_water`, `settlement_visible`, `bare_soil_expansion` |

**Sample output:**
```
Backend: llama-server at http://localhost:8080/v1
Evaluating 209 test observations…
100%|████████████████████| 209/209 [08:14<00:00,  2.36 s/obs]

## Overall Accuracy: 0.859

## Per-Field Accuracy

### Water Body (Core Zone)
- water_extent_status: 0.891
- flood_risk: 0.843
- water_clarity: 0.812
- shoreline_encroachment: 0.876

### Agricultural Buffer Zone
- agriculture_present: 0.934
- crop_stress_level: 0.798
- crop_stress_type: 0.771
- cultivation_expanding_toward_water: 0.823
- settlement_visible: 0.911
- bare_soil_expansion: 0.856

## Per-Location Accuracy
- lake_chad: 0.923
- dead_sea: 0.901
- aral_sea: 0.887
- okavango: 0.874
...
- congo_delta: 0.731      ← persistent cloud degrades accuracy
```

### Step 3 — Evaluate Claude oracle baseline (for comparison)
```bash
python scripts/evaluate.py --backend claude
```
**Purpose:** Runs the same 209 test observations through the Claude oracle.
Since Claude generated the ground-truth labels, this is the upper-bound baseline —
any gap between `llama` and `claude` scores is the cost of fine-tuning compression.  
**Sample output:**
```
Backend: claude-oracle
Evaluating 209 test observations…
100%|████████████████████| 209/209 [18:41<00:00,  5.37 s/obs]

## Overall Accuracy: 0.961
```

### Side-by-side comparison
```bash
python scripts/evaluate.py --backend llama  --output data/reports/eval_lfm.json
python scripts/evaluate.py --backend claude --output data/reports/eval_oracle.json
```
Then diff the two JSON files to see per-field and per-location accuracy gaps between
the fine-tuned LFM2.5-VL-450M and the oracle.

### Point the evaluator at a non-default llama-server URL
```bash
LLAMA_SERVER_URL=http://192.168.1.50:8080 python scripts/evaluate.py --backend llama
```
**Purpose:** Use when llama-server is running on a GPU machine on the local network
rather than localhost.

### Quick smoke test (20 observations)
```bash
python scripts/evaluate.py --backend llama --limit 20
```
**Purpose:** Sanity-check that llama-server is responding and producing valid JSON
before committing to the full 209-observation test run.  
**Sample output:**
```
Backend: llama-server at http://localhost:8080/v1
Evaluating 20 test observations…
100%|████████████████████| 20/20 [01:38<00:00,  4.92 s/obs]
## Overall Accuracy: 0.847
```

---

## 7. Live Prediction

### Start the live inference loop
```bash
python scripts/predict.py
```
**Purpose:** Polls SimSat every 30 seconds for the satellite's current position. When
the satellite passes within 50km of a monitored water body (and hasn't observed it
in 24h), fetches 4 images, runs core + buffer inference via `llama-server`, writes
the labeled observation to Postgres, and optionally generates prose via Claude Haiku
if `ANTHROPIC_API_KEY` is set.  
**Prerequisites:** `docker compose up`, `llama-server` running with fine-tuned GGUF,
SimSat simulation started.  
**Sample output:**
```
AquaVeritas Live Prediction Loop
========================================
llama-server: OK (http://localhost:8080)
Monitoring 20 water bodies | poll every 30s

[08:22:11] Satellite at (34.20, 3.50) — 1 location(s) triggered
  → Lake Turkana [lake_turkana] ✓ water=stable crop=none flood=none
```
> **Note (AVS-041):** The loop is crash-resilient against Postgres connection drops.
> If the DB is idle for many hours (e.g. SimSat paused overnight), the connection
> may be terminated by the container. The loop catches this, logs a warning, and
> retries on the next poll cycle — it does not exit.

### Custom poll interval and model URL
```bash
python scripts/predict.py --interval 60 --model-url http://localhost:8080
```

### Custom database URL
```bash
python scripts/predict.py --db-url postgresql://aqua:<password>@localhost:5433/aquaveritas
```

### Restart a stopped predict loop
```bash
pkill -f "predict.py" 2>/dev/null; sleep 1
python scripts/predict.py --interval 30 &
echo "Predict loop restarted (PID $!)"
```

---

## 8. Dashboard

### Launch Streamlit monitoring dashboard
```bash
streamlit run app/app.py
```
**Purpose:** Opens a web UI at `http://localhost:8501` with four tabs:
- **Global Monitor** — pydeck globe of all 20 water bodies, colour-coded by latest status, zoom-to-selected, sustained shrinkage alerts, time-series trend charts
- **Live Prediction** — select water body → fetch Sentinel-2 imagery → run VLM inference → display 11-field structured result + Claude Haiku prose brief
- **Model Evaluation** — three-way accuracy table (oracle vs base vs fine-tuned), per-field and per-location breakdown
- **Dataset** — browse and filter all historical observations with location/date/status filters  
**Sample output:**
```
  You can now view your Streamlit app in your browser.
  Local URL: http://localhost:8501
```

### Restart a stopped dashboard
```bash
pkill -f "streamlit run" 2>/dev/null; sleep 1
streamlit run app/app.py --server.port 8501
```

---

## 8b. HuggingFace Space

### Push the HF Space (export SQLite snapshot + upload)
```bash
bash scripts/push_hf_space.sh
```
**Purpose:** Exports the current PostgreSQL observations to a SQLite bundle
(`hf_space/data/observations.db`), then uploads the full `hf_space/` directory
to `Arty1001/aquaveritas` on HuggingFace Spaces.

### Upload manually via Python API (if CLI not in PATH)
```bash
python3 -c "
from huggingface_hub import HfApi
api = HfApi()
api.upload_folder(
    folder_path='hf_space/',
    repo_id='Arty1001/aquaveritas',
    repo_type='space',
)
print('Done')
"
```

### Check Space is live
```bash
curl -s https://huggingface.co/spaces/Arty1001/aquaveritas | grep -i "running\|error" | head -5
```

---

## 8c. Prose Generation

The dashboard generates human-readable mission-brief prose from structured VLM predictions
using Claude Haiku (`claude-haiku-4-5`). Requires `ANTHROPIC_API_KEY` in `.env`.

### Prose output format
```
LAKE CHAD · 2026-05-05

Lake Chad's water extent is actively shrinking, with turbid clarity and confirmed
shoreline encroachment — the lake edge is retreating and its boundary is being re-drawn.
There is no active flood risk.

The surrounding buffer shows severe drought-stress across agricultural land, with
cultivation actively expanding toward the receding waterline. No settlements are
visible, but bare soil exposure is widespread.

**Assessment:** Lake Chad is exhibiting dual-vector stress — the lake is contracting
while cultivation around it expands. The retreating shoreline is not recovering land;
it is being absorbed by agriculture.
```

### Cloud-cover detection thresholds
```python
CLOUD_FRACTION_WARN  = 0.40   # ≥40% cloud → amber warning banner, low-confidence labels
CLOUD_FRACTION_BLOCK = 0.65   # ≥65% cloud → no prose generated, informational card only
```
Cloud fraction is estimated by PIL: pixels with all RGB channels > 238 counted as cloud.
The VLM's own `image_quality_limited` field is used as a secondary signal.

### Verify prose API key is resolving
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from aquaveritas.prose import _prose_available, _get_api_key
key = _get_api_key()
print('Key found:', key[:8] + '...' if key else 'NOT FOUND')
print('Prose available:', _prose_available())
"
```

### Smoke-test prose generation (Lake Chad)
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from aquaveritas.prose import generate_prose
core = {'water_extent_status': 'shrinking', 'flood_risk': 'none',
        'water_clarity': 'turbid', 'shoreline_encroachment': True, 'image_quality_limited': False}
buf  = {'agriculture_present': True, 'crop_stress_level': 'severe', 'crop_stress_type': 'drought',
        'cultivation_expanding_toward_water': True, 'settlement_visible': False,
        'bare_soil_expansion': True, 'image_quality_limited': False}
print(generate_prose('Lake Chad', '2026-05-05', core, buf))
"
```

### Smoke-test cloud-degraded mode
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from aquaveritas.prose import generate_prose
core = {'water_extent_status': 'stable', 'flood_risk': 'none',
        'water_clarity': 'clear', 'shoreline_encroachment': False, 'image_quality_limited': False}
buf  = {'agriculture_present': False, 'crop_stress_level': 'none', 'crop_stress_type': 'none',
        'cultivation_expanding_toward_water': False, 'settlement_visible': False,
        'bare_soil_expansion': False, 'image_quality_limited': False}
# cloud_degraded=True: Haiku acknowledges cloud cover, omits Assessment line
print(generate_prose('Tana River Delta', '2026-05-05', core, buf, cloud_degraded=True))
"
```

### Test Qwen2.5-1.5B as local prose backend (requires download)
```bash
# Download Qwen GGUF first (1GB)
curl -L -o data/models/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf \
  "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf"

# Start second llama-server on port 8081 (text-only, no mmproj needed)
llama-server -m data/models/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf \
  --port 8081 --ctx-size 2048 --host 127.0.0.1

# Run prose test suite
python scripts/test_prose_qwen.py
```

---

## 8d. Modal Volume Inspection

### List all Modal apps (check for running jobs)
```bash
modal app list
```

### List Modal volumes
```bash
modal volume list
```

### Browse volume root
```bash
modal volume ls aquaveritas-data
```

### Browse subdirectories
```bash
modal volume ls aquaveritas-data gguf
modal volume ls aquaveritas-data aquaveritas-bundle
```

### List Modal environments
```bash
modal environment list
```

### Download a file from the volume
```bash
modal volume get aquaveritas-data gguf/aquaveritas-lfm-q8_0.gguf ./data/models/
```

---

## 8e. GitHub PR — Hackathon Submission

### View the submission PR
```bash
gh pr view 5 --repo DPhi-Space/SimSat
```

### Update the PR body
```bash
gh pr edit 5 --repo DPhi-Space/SimSat --body "$(cat <<'EOF'
...body content...
EOF
)"
```

### Create submission branch from upstream main
```bash
git remote add upstream https://github.com/DPhi-Space/SimSat.git
git fetch upstream
git checkout -b submission upstream/main
```

### Copy AquaVeritas files onto submission branch (avoids cherry-pick conflicts)
```bash
git checkout main -- aquaveritas/
git checkout main -- docker-compose.yaml
git checkout main -- SETUP.md
git checkout main -- README.md
git push origin submission
```

### Open the PR
```bash
gh pr create \
  --repo DPhi-Space/SimSat \
  --head devleks:submission \
  --base main \
  --title "feat: AquaVeritas — on-board freshwater monitoring with fine-tuned LFM2.5-VL-450M" \
  --body "$(cat <<'EOF'
...body...
EOF
)"
```

---

## 8f. leap-finetune Health Check

### Verify installation and version
```bash
cd /Users/ml_labs/leap-finetune
uv run leap-finetune --help
```

### Check repo is at latest upstream commit
```bash
git log --oneline -5
git fetch origin --dry-run
git log origin/main..HEAD --oneline
```

### List available job config templates
```bash
ls job_configs/
```

---

## 8g. LEAP Bundle (Liquid Edge AI Platform)

Converts the fine-tuned HF model to a Liquid-platform-native GGUF bundle.
`leap-bundle` takes a local HF model directory and uploads it to the LEAP
platform, which runs `convert_hf_to_gguf.py` server-side. The resulting bundle
is separate from the GGUFs on HuggingFace — it is for on-board deployment via
the Liquid Edge AI Platform.

Run all commands from `/Users/ml_labs/leap-finetune` using `uv run`.

### Check available commands
```bash
cd /Users/ml_labs/leap-finetune
uv run leap-bundle --help
```

### List all bundle requests (most recent 50)
```bash
cd /Users/ml_labs/leap-finetune
uv run leap-bundle list
```
**Sample output:**
```
Bundle Requests (50 most recent)
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ID ┃ Input Path               ┃ Status            ┃ Creation                 ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 1  │ /data/aquaveritas-bundle │ Processing Failed │ 2026-05-04T14:34:31.719Z │
└────┴──────────────────────────┴───────────────────┴──────────────────────────┘
```

### Cancel a failed request
```bash
cd /Users/ml_labs/leap-finetune
uv run leap-bundle cancel 1
```

### Step 1 — Download fine-tuned model files from Modal volume
```bash
mkdir -p /Users/ml_labs/claudey/SimSat/aquaveritas/data/bundle-upload

modal volume get aquaveritas-data aquaveritas-bundle/config.json           /Users/ml_labs/claudey/SimSat/aquaveritas/data/bundle-upload/config.json
modal volume get aquaveritas-data aquaveritas-bundle/model.safetensors     /Users/ml_labs/claudey/SimSat/aquaveritas/data/bundle-upload/model.safetensors
modal volume get aquaveritas-data aquaveritas-bundle/tokenizer.json        /Users/ml_labs/claudey/SimSat/aquaveritas/data/bundle-upload/tokenizer.json
modal volume get aquaveritas-data aquaveritas-bundle/tokenizer_config.json /Users/ml_labs/claudey/SimSat/aquaveritas/data/bundle-upload/tokenizer_config.json
modal volume get aquaveritas-data aquaveritas-bundle/processor_config.json /Users/ml_labs/claudey/SimSat/aquaveritas/data/bundle-upload/processor_config.json
modal volume get aquaveritas-data aquaveritas-bundle/generation_config.json /Users/ml_labs/claudey/SimSat/aquaveritas/data/bundle-upload/generation_config.json
modal volume get aquaveritas-data aquaveritas-bundle/chat_template.jinja   /Users/ml_labs/claudey/SimSat/aquaveritas/data/bundle-upload/chat_template.jinja
```
**Purpose:** Downloads the 7 model files from the Modal volume to a local directory.
`leap-bundle create` requires a local path — it cannot read Modal volumes directly.

### Step 2 — Validate the directory before uploading
```bash
cd /Users/ml_labs/leap-finetune
uv run leap-bundle validate /Users/ml_labs/claudey/SimSat/aquaveritas/data/bundle-upload
```
**Purpose:** Checks for required files without uploading or creating a request.
If this reports missing files, fetch them from the base model on HuggingFace before proceeding.

### Step 3 — Create the bundle (Q8_0 backbone + F16 mmproj)
```bash
cd /Users/ml_labs/leap-finetune
uv run leap-bundle create \
  /Users/ml_labs/claudey/SimSat/aquaveritas/data/bundle-upload \
  --quantization Q8_0 \
  --mmproj-quantization f16
```
**Purpose:** Uploads the local model directory to the LEAP platform. The platform
runs `convert_hf_to_gguf.py` server-side and produces two GGUF files: backbone
(Q8_0) and vision projector (F16) — matching the existing HuggingFace artefacts.

### Monitor conversion progress
```bash
cd /Users/ml_labs/leap-finetune
uv run leap-bundle list
```
Status will move from `Uploading` → `Processing` → `Completed` (or `Processing Failed`).

### Download the completed bundle
```bash
cd /Users/ml_labs/leap-finetune
uv run leap-bundle download 2 --output-path /Users/ml_labs/claudey/SimSat/aquaveritas/data/models/leap-bundle
```
**Note:** The flag is `--output-path`, not `--output`. The LEAP platform produces a **single GGUF** (`LFM2_VL-450M-Q8_0.gguf`, 430MB) packaged for the LEAP Edge SDK. This is the fine-tuned backbone only — the mmproj is handled separately by the SDK. For local inference via `llama-server`, continue using the two-file setup in `data/models/` (`aquaveritas-lfm-q8_0.gguf` + `mmproj-LFM2.5-VL-450m-F16.gguf`).

**Downloaded artefact:**
```
data/models/leap-bundle/LFM2_VL-450M-Q8_0.gguf    430MB   fine-tuned backbone (LEAP Edge SDK format)
```

**LEAP Edge SDK deployment docs:** https://docs.liquid.ai/leap

### Resume a failed upload (network interruption)
```bash
cd /Users/ml_labs/leap-finetune
uv run leap-bundle resume <bundle-id>
```

---

## 9. Incident Report

### Regenerate the incident registry PDF
```bash
python docs/generate_incident_report.py
```
**Purpose:** Rebuilds the Precision Incident Management SOP PDF with all current
tickets (AVS-001 to AVS-042). Outputs to `docs/AVS_Incident_Registry_<date>_vN.pdf`.  
**Sample output:**
```
PDF written: aquaveritas/docs/AVS_Incident_Registry_2026-05-06_v9.pdf
```
> **Note (AVS-042):** Credentials must never appear in fix descriptions or examples.
> Use `<redacted>` for passwords in all ticket fields.

---

## 10. Troubleshooting

Known issues, root causes, and fixes drawn from the AVS incident registry.

---

### Infrastructure

**`psycopg2.OperationalError: role "aqua" does not exist`** (AVS-001)
```
Cause:  Homebrew postgresql@18 is running on port 5432 and intercepts Docker connections.
Check:  lsof -i :5432
Fix:    Docker maps to 5433 — ensure DATABASE_URL uses port 5433, not 5432.
        DATABASE_URL=postgresql://aqua:<password>@localhost:5433/aquaveritas
```

**Docker container rejected on Apple Silicon** (AVS-002)
```
Cause:  postgis/postgis image is amd64-only; 'platform: linux/arm64' in docker-compose.yaml
        causes hard rejection.
Fix:    Remove the platform constraint entirely. Docker runs via Rosetta 2 transparently.
        The "WARNING: platform mismatch" in logs is cosmetic — container works fine.
```

**SimSat API not reachable**
```
Check:  curl http://localhost:9005/data/current/position
Fix:    docker compose up -d  (stack may not be running)
        docker compose logs simsat  (check for startup errors)
```

---

### Data Collection

**Black strips / wedges in satellite images** (AVS-004)
```
Cause:  15km bounding box straddles an MGRS UTM tile boundary. odc.stac loads only
        one tile, leaving the other as black no-data. No error is raised.
Fix:    Move the location coordinate away from UTM zone boundaries.
        Run a preview first: python scripts/collect_data.py --location X --preview
        and inspect the image before running full collection.
Permanent: volga_delta removed — 48°E UTM boundary bisects the entire delta.
```

**Tile shows 100% open water — no shoreline** (AVS-005)
```
Cause:  Coordinate is placed inside the lake, not at the water/land boundary.
Fix:    Shift the coordinate toward the shore. For Lake Turkana: lon 36.05 → 36.25.
```

**Tile shows wrong feature (interior, not coast/mouth)** (AVS-006, AVS-007)
```
Cause:  Coordinate too far inland (tana_river) or too far from the coast (nile_delta).
Fix:    Cross-check coordinates against satellite preview before full collection.
```

**Near-100% cloud cover across all months** (AVS-009)
```
Locations: amazon_delta, congo_delta
Cause:  Equatorial ITCZ and Benguela stratus — persistent cloud year-round.
Action: Kept in dataset. The 30-day collection window finds clear months across 84 months.
        image_quality_limited=true is flagged by the annotator where cloud blocks the view.
```

---

### Image Pre-processing

**`anthropic.BadRequestError: image exceeds 5 MB maximum`** (AVS-016)
```
Cause:  Anthropic's 5 MB limit applies to the base64-encoded image, not the raw file.
        Base64 adds 33% overhead: a 3.75 MB raw PNG → 5 MB base64. Old threshold was 4 MB.
Fix:    _MAX_IMAGE_BYTES is now 3.5 MB raw (→ 4.67 MB base64), safely under the cap.
        If error recurs, run: python scripts/resize_images.py  (pre-processes all PNGs)
```

**resize_images.py reports 0 resized but labelling still crashes** (AVS-012)
```
Cause:  Dense scenes (Okavango) can still exceed the byte limit after a 1024 px resize.
        The iterative halving loop in _resize_image() handles this automatically.
Check:  Confirm annotator.py has the while loop after img.resize() in _resize_image().
Fix:    Already fixed — _resize_image() halves dimensions until under _MAX_IMAGE_BYTES.
```

---

### Triage

**`No untriaged observations found` after heuristic pass** (AVS-011)
```
Cause:  get_untriaged() queries WHERE triage_verdict IS NULL. After the heuristic pass,
        all rows have a verdict set — zero rows match.
Fix:    Use --retriage-heuristic flag to re-evaluate heuristic PASSes:
        python scripts/triage_images.py --model lfm2.5-vl-450m-mlx --retriage-heuristic
```

**79% FAIL rate from LM Studio vision model triage**
```
Cause:  Base LFM2.5-VL-450M (pre-fine-tune) produces degenerate scores zero-shot on
        satellite imagery. AGRICULTURE=0 for all images, avg_total=2.29/18.
Action: Revert all vision-model verdicts back to heuristic PASS:
        UPDATE observations SET triage_verdict='pass', triage_model='heuristic-pil'
          WHERE triage_model != 'heuristic-pil';
        Vision model triage is only meaningful after fine-tuning.
```

---

### Labelling

**`error: annotator returned None` for all LM Studio observations** (AVS-013)
```
Cause:  glm-4.6v-flash and gemma-4-e4b are thinking models. With max_tokens=512 they
        consume the entire budget on reasoning (510/512 tokens), leaving content=''.
        Check LM Studio server logs for reasoning_tokens ≈ max_tokens.
Fix:    LMStudioAnnotator already uses max_tokens=4096. If still failing:
        python scripts/label_data.py --backend lmstudio --verbose --batch 1
        to inspect the raw response.
```

**LM Studio labelling too slow for bulk run** (AVS-015)
```
Observed speeds:
  glm-4.6v-flash    136 s/obs  →  60+ hours for 1,600 obs  (thinking overhead)
  gemma-4-e4b        14 s/obs  →  ~6 hours for 1,600 obs   (thinking overhead)
  lfm2.5-vl-450m-mlx  2 s/obs  →  fast but incomplete JSON
Recommendation: Use Claude oracle for bulk labelling:
        python scripts/label_data.py --batch 500
```

**Labelling crashes mid-batch with `anthropic.RateLimitError`**
```
Cause:  Anthropic API rate limit hit (typically Tier 1: ~50 req/min on Opus).
Fix:    The retry logic sleeps 30s/60s and continues automatically.
        If persistent, reduce workers or add a manual sleep between batches:
        python scripts/label_data.py --batch 200  (smaller batches with natural pauses)
```

**High `error` count in labelling output**
```
Debug:  python scripts/label_data.py --batch 20 --verbose
        Verbose mode prints the raw model response for each failed parse.
Common causes:
  - Image file missing from disk (FileNotFoundError) — re-run collect_data.py
  - Model returned prose instead of JSON — check COMBINED_SYSTEM prompt formatting
  - API key not loaded — confirm ANTHROPIC_API_KEY in SimSat/.env (not aquaveritas/.env)
```

**ANTHROPIC_API_KEY not found / empty**
```
Cause:  Key set as empty string in shell env; load_dotenv skips existing vars by default.
        annotator.py uses override=True to force .env values.
Check:  python -c "import os; from dotenv import load_dotenv; from pathlib import Path;
        load_dotenv(Path('src/aquaveritas/annotator.py').resolve().parents[3]/'.env',
        override=True); print(os.environ.get('ANTHROPIC_API_KEY','NOT SET')[:8])"
Fix:    Ensure ANTHROPIC_API_KEY is set in SimSat/.env (the root .env, not aquaveritas/.env)
```

---

### Fine-tuning & Evaluation

**`llama-server` loads model but vision requests fail / return garbled output**
```
Cause:  Started with --model only, missing --mmproj. A VLM requires BOTH files.
Fix:    Always start llama-server with both GGUF files:
        llama-server \
            --model  ./outputs/aquaveritas-lfm-Q8_0.gguf \
            --mmproj ./outputs/mmproj-aquaveritas-lfm-Q8_0.gguf \
            --port 8080
```

**`quantize.py` produces only one GGUF file**
```
Cause:  Expecting two outputs: backbone + mmproj. The mmproj is auto-named with
        the mmproj- prefix in the same output directory.
Check:  ls ./outputs/*.gguf  — should show both files.
Fix:    Re-run quantize.py and confirm both files exist before starting llama-server.
```

**Evaluation accuracy unexpectedly low on `image_quality_limited` field**
```
Cause:  image_quality_limited is excluded from accuracy scoring by default
        (it is a metadata flag, not a semantic label).
Check:  evaluate.py computes accuracy on CORE_FIELDS and BUFFER_FIELDS only —
        confirm image_quality_limited is not in either list in evaluator.py.
```

---

### Database

**Check label coverage**
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from aquaveritas.db import Database
db = Database()
rows = db.get_unlabeled(limit=9999)
print(f'Remaining unlabeled: {len(rows)}')
"
```

**Check triage summary**
```bash
python -c "
import sys; sys.path.insert(0, 'src')
from aquaveritas.db import Database
db = Database()
print(db.get_triage_summary())
"
```

**Reset all labels for a location (re-label from scratch)**
```bash
psql postgresql://aqua:<password>@localhost:5433/aquaveritas \
  -c "UPDATE observations SET labeled_at=NULL, core_labels=NULL, buffer_labels=NULL
      WHERE location_id='lake_chad';"
```

**Reset vision-model triage verdicts back to heuristic**
```bash
psql postgresql://aqua:<password>@localhost:5433/aquaveritas \
  -c "UPDATE observations
      SET triage_verdict='pass', triage_model='heuristic-pil', triage_score=NULL
      WHERE triage_model != 'heuristic-pil';"
```

---

### Process Management

**Check if a script is currently running**
```bash
pgrep -f "label_data.py" 2>&1
pgrep -f "collect_data.py" 2>&1
pgrep -f "triage_images.py" 2>&1
```
Returns the PID if running, nothing if not.

**Stop a running script**
```bash
kill 83695 2>&1 && echo "stopped"
```
Replace `83695` with the PID from `pgrep`. Use `-9` only if the process ignores a normal kill:
```bash
kill -9 83695 2>&1 && echo "force stopped"
```

**Find PID and stop in one command**
```bash
pkill -f "label_data.py" && echo "stopped"
```

**Monitor a background task output in real time**
```bash
tail -f /private/tmp/claude-501/-Users-ml-labs-claudey-SimSat/d3538835-1c89-4d09-92e6-763d5b4c6eea/tasks/<task-id>.output
```
Task output paths are printed when a background job is launched from Claude Code.

**Check all Python processes**
```bash
ps aux | grep python | grep -v grep
```

---

### LM Studio Diagnostics

**Check which models are loaded**
```bash
curl -s http://localhost:8234/v1/models | python3 -m json.tool
```
**Sample output:**
```json
{
  "data": [
    {"id": "glm-4.6v-flash", "object": "model"},
    {"id": "lfm2.5-vl-450m-mlx", "object": "model"},
    {"id": "google/gemma-4-e4b", "object": "model"}
  ]
}
```

**Test a model responds (text-only, no image)**
```bash
curl -s http://localhost:8234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"glm-4.6v-flash","max_tokens":200,"messages":[{"role":"user","content":"Reply with ONLY this JSON: {\"status\": \"ok\"}"}]}' \
  | python3 -m json.tool
```
Check `choices[0].message.content` and `usage.completion_tokens_details.reasoning_tokens`.
If `reasoning_tokens ≈ max_tokens` and `content` is empty → thinking model token budget exhausted (AVS-013).

**Check LM Studio is reachable**
```bash
curl -s http://localhost:8234/v1/models 2>&1 | head -5
```
If connection refused → LM Studio server not running. Start it from LM Studio app → Developer tab.

---

**`map background is black on HF Space`** (AVS-046)
```
Cause:  pydeck reads MAPBOX_API_KEY from the environment natively — not MAPBOX_TOKEN.
        HF Spaces injects secrets under the name you give them in the Space settings.
Fix:    After reading the token, set both:
          os.environ["MAPBOX_API_KEY"] = token
          pdk.settings.mapbox_key = token
        Fallback style when no token: CartoDB Positron (no auth required):
          "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
```

**`map markers fill entire viewport at zoom`** (AVS-047)
```
Cause:  get_radius is in metres. At zoom 5, get_radius=8_000 renders as ~100px+.
        No upper pixel cap was set.
Fix:    Add radius_max_pixels to every ScatterplotLayer:
          layer = pdk.Layer("ScatterplotLayer", ...,
              get_radius=8_000,
              radius_min_pixels=5,
              radius_max_pixels=11)
        Also fix pitch: pitch=25 makes markers oval. Set pitch=0.
```

**`LlamaBackend.__init__() got an unexpected keyword argument 'timeout'`** (AVS-048)
```
Cause:  app.py called LlamaBackend(base_url=llama_url, timeout=120.0).
        The LlamaBackend constructor only accepts base_url.
Fix:    Remove the timeout kwarg:
          backend = LlamaBackend(base_url=llama_url)
        Timeout is set on the underlying OpenAI client inside LlamaBackend.__init__().
```

**`leap-bundle: Processing Failed — convert_hf_to_gguf.py returned non-zero exit status 1`**
```
Cause:  leap-bundle create was pointed at a Modal container-internal path (/data/aquaveritas-bundle)
        rather than a local directory. The platform received no files to convert.
        Also possible: the bundle directory contains only safetensors but is missing
        config.json, tokenizer_config.json, or processor_config.json.
Fix:    1. Download all model files from Modal volume to a local directory (see §8g Step 1).
        2. Run: uv run leap-bundle validate <local-dir>  (confirms files are complete).
        3. Cancel the failed request: uv run leap-bundle cancel <id>
        4. Re-submit: uv run leap-bundle create <local-dir> --quantization Q8_0 --mmproj-quantization f16
```

**`HF Space changes corrupted the live app — tabs missing, KeyError, NameError`** (AVS-045)
```
Cause:  app/app.py was shared between the live app and hf_space/app.py.
        HF-specific changes (removing PostgreSQL, reducing to 2 tabs, renaming
        columns) leaked into the production file on git operations.
Fix:    Live app and HF Space must be separate files:
          app/app.py          ← production, 4 tabs, PostgreSQL
          hf_space/app.py     ← read-only showcase, 2 tabs, SQLite
        They share modules (db.py, evaluator.py, prose.py) but never share app.py.
Prevention: Never run git checkout main -- app/app.py from inside hf_space/.
```

---

### Image Size Inspection

**Find the largest PNG files on disk**
```bash
find data/images -name "*.png" -not -path "*/preview*" \
  | xargs stat -f "%z %N" \
  | sort -rn \
  | head -10
```
**Sample output:**
```
4734594 data/images/okavango/2020-07-01/rgb_core.png
4717429 data/images/okavango/2019-06-01/rgb_core.png
3922199 data/images/okavango/2019-06-01/swir_core.png
```

**Count images over the 3.5 MB raw threshold**
```bash
find data/images -name "*.png" \
  | xargs stat -f "%z" \
  | awk '$1 > 3670016' \
  | wc -l
```
3670016 = 3.5 × 1024 × 1024. Anything above this will be resized by `_resize_image()`.

**Check total image dataset size**
```bash
du -sh data/images/
```

---

### Port & Connectivity Checks

**Check what is listening on key ports**
```bash
lsof -i :5432   # postgres default (should be Homebrew — NOT the Docker container)
lsof -i :5433   # aquaveritas Docker postgres
lsof -i :8080   # llama-server
lsof -i :8081   # llama-server prose instance (Qwen)
lsof -i :8234   # LM Studio
lsof -i :8501   # Streamlit dashboard (local app)
lsof -i :7860   # HF Space local preview
lsof -i :9005   # SimSat API
```

**Quick connectivity matrix**
```bash
curl -s http://localhost:9005/data/current/position  && echo "SimSat OK"
curl -s http://localhost:8234/v1/models | grep -q id  && echo "LM Studio OK"
curl -s http://localhost:8080/v1/models | grep -q id  && echo "llama-server OK"
psql postgresql://aqua:<password>@localhost:5433/aquaveritas -c "SELECT 1;" && echo "Postgres OK"
```

---

### Environment & API Key

**Verify ANTHROPIC_API_KEY is loading from .env**
```bash
python -c "
import os
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path('src/aquaveritas/annotator.py').resolve().parents[3] / '.env', override=True)
key = os.environ.get('ANTHROPIC_API_KEY', 'NOT SET')
print(f'Key prefix: {key[:8]}...' if key != 'NOT SET' else 'NOT SET')
"
```

**Print all loaded env vars relevant to this project**
```bash
python -c "
import os
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path('src/aquaveritas/annotator.py').resolve().parents[3] / '.env', override=True)
for k in ['ANTHROPIC_API_KEY','DATABASE_URL','LMSTUDIO_BASE_URL','LLAMA_SERVER_URL','HF_TOKEN']:
    v = os.environ.get(k, 'NOT SET')
    print(f'{k}: {v[:12]}...' if v != 'NOT SET' else f'{k}: NOT SET')
"
```

---

## Pipeline Order

```
docker compose up -d
         ↓
python scripts/collect_data.py --workers 3          # ~72 min, 1680 obs
         ↓
python scripts/triage_images.py --heuristic          # ~3 min,  fast PIL pass
         ↓
python scripts/triage_images.py \
    --model lfm2.5-vl-450m-mlx \
    --retriage-heuristic                             # ~50 min, vision scoring
         ↓
python scripts/triage_images.py \
    --export-manifest --export-only                  # rejection manifest
         ↓
python scripts/label_data.py --batch 500             # Claude oracle labels
         ↓
python scripts/train.py \
    --hf-repo <HF_REPO>                              # export to HuggingFace
         ↓
python scripts/finetune.py \
    --hf-model-repo <HF_REPO> --quantize             # Modal H100 fine-tune
         ↓
python scripts/evaluate.py --backend llama           # accuracy report
         ↓
python scripts/predict.py                            # live inference loop (prose auto-generated if ANTHROPIC_API_KEY set)
         ↓
streamlit run app/app.py                             # monitoring dashboard (prose + cloud detection in Live Prediction tab)
```

---

## 11. Model Prompts, Expected JSON & Jinja Format

Reference for anyone testing the model directly — via llama-server, LM Studio,
the Anthropic API, or the LEAP inference platform.

---

### System Prompts

Three system prompts are defined in `src/aquaveritas/annotator.py`. All use
Python `.format()` substitution for `{name}`, `{lat}`, `{lon}`, `{description}`,
and `{expected_water_status}`.

#### Combined (default — one call, both zones)

Used by `Annotator.annotate()` and `LMStudioAnnotator.annotate()`. Returns a
single JSON object with `core` and `buffer` keys.

```
You are an expert remote sensing analyst specialising in freshwater body
and agricultural stress monitoring.
You are analysing Sentinel-2 satellite imagery of {name} (lat {lat}°, lon {lon}°).

LOCATION CONTEXT:
{description}

BASELINE: {expected_water_status}

You will receive two images, each covering a 15km × 15km area organised as a
3×3 grid of 5km × 5km sub-tiles. The coordinate is at the water/land boundary
so the tile captures open water, the shoreline transition, and the adjacent
agricultural land within a single view.

1. RGB true-colour composite (red/green/blue bands, 15km tile)
   - Shows water colour, field patterns, roads, settlements, irrigation canals
2. SWIR false-colour composite (swir16/nir/red bands, 15km tile)
   - Dark / black  = open water (SWIR strongly absorbed by water)
   - Bright green  = healthy, well-watered vegetation or crops
   - Amber / yellow = moderate moisture stress
   - Magenta / pink = bare soil, dried lakebed, or harvested fields
   - Deep red/brown = severely stressed or dead vegetation / crop failure
   - White / pale   = cloud or salt flat

Analyse BOTH the water body AND the surrounding agricultural land, then respond
with ONLY a single valid JSON object — no prose, no markdown fences, ALL fields present:
{
  "core": {
    "water_extent_status": "shrinking|stable|flooded|recovering|dry",
    "flood_risk": "none|elevated|active",
    "water_clarity": "clear|turbid|heavily_silted",
    "shoreline_encroachment": true|false,
    "image_quality_limited": true|false
  },
  "buffer": {
    "agriculture_present": true|false,
    "crop_stress_level": "none|low|moderate|severe",
    "crop_stress_type": "drought|flood_damage|none",
    "cultivation_expanding_toward_water": true|false,
    "settlement_visible": true|false,
    "bare_soil_expansion": true|false,
    "image_quality_limited": true|false
  }
}

Set image_quality_limited to true in either section if cloud cover obscures
>50% of that zone or if the image is clearly unusable.
```

#### Core only (water body)

Used by `annotate_core()` and in training JSONL `zone: "core"` records.

```
You are an expert remote sensing analyst specialising in freshwater body monitoring.
You are analysing Sentinel-2 satellite imagery of {name} (lat {lat}°, lon {lon}°).

LOCATION CONTEXT:
{description}

BASELINE: {expected_water_status}

You will receive two images, each covering a 15km × 15km area organised as a
3×3 grid of 5km × 5km sub-tiles. The coordinate is positioned at the water/land
boundary so the tile captures open water, the shoreline transition, and the
adjacent land within a single view.

1. RGB true-colour composite (red/green/blue bands, 15km tile)
2. SWIR false-colour composite (swir16/nir/red bands, 15km tile)
   - Dark / black  = open water (SWIR strongly absorbed by water)
   - Bright green  = healthy, well-watered vegetation
   - Amber / yellow = moderate moisture stress
   - Magenta / pink = bare soil or dried lakebed
   - Deep red/brown = severely stressed or dead vegetation
   - White / pale   = cloud or salt flat

Focus your assessment on the water body portion of the tile.
Analyse both images and respond with ONLY a valid JSON object — no prose, no markdown fences:
{
  "water_extent_status": "shrinking|stable|flooded|recovering|dry",
  "flood_risk": "none|elevated|active",
  "water_clarity": "clear|turbid|heavily_silted",
  "shoreline_encroachment": true|false,
  "image_quality_limited": true|false
}

Set image_quality_limited to true if cloud cover obscures >50% of the water body
or if the image is clearly unusable.
```

#### Buffer only (agricultural land)

Used by `annotate_buffer()` and in training JSONL `zone: "buffer"` records.

```
You are an expert remote sensing analyst specialising in agricultural stress monitoring.
You are analysing Sentinel-2 satellite imagery of the land surrounding
{name} (lat {lat}°, lon {lon}°).

LOCATION CONTEXT:
{description}

You will receive two images, each covering a 15km × 15km area organised as a
3×3 grid of 5km × 5km sub-tiles. The coordinate is at the water/land boundary,
so the tile shows both the lake margin and the surrounding agricultural zone.

1. RGB true-colour composite (red/green/blue bands, 15km tile)
   - Shows field patterns, roads, settlements, irrigation canals, land use change
2. SWIR false-colour composite (swir16/nir/red bands, 15km tile)
   - Bright green  = healthy, well-watered crops or natural vegetation
   - Amber / yellow = moderate moisture stress in crops
   - Magenta / pink = bare soil, recently harvested, or dry fields
   - Deep red/brown = severe crop stress or crop failure
   - Dark / black   = open water, irrigation canals

Focus your assessment on the agricultural land portion of the tile.
Analyse both images and respond with ONLY a valid JSON object — no prose, no markdown fences:
{
  "agriculture_present": true|false,
  "crop_stress_level": "none|low|moderate|severe",
  "crop_stress_type": "drought|flood_damage|none",
  "cultivation_expanding_toward_water": true|false,
  "settlement_visible": true|false,
  "bare_soil_expansion": true|false,
  "image_quality_limited": true|false
}
```

---

### Expected JSON Output

#### Combined response (COMBINED_SYSTEM)

```json
{
  "core": {
    "water_extent_status": "stable",
    "flood_risk": "none",
    "water_clarity": "turbid",
    "shoreline_encroachment": false,
    "image_quality_limited": false
  },
  "buffer": {
    "agriculture_present": true,
    "crop_stress_level": "low",
    "crop_stress_type": "drought",
    "cultivation_expanding_toward_water": false,
    "settlement_visible": true,
    "bare_soil_expansion": false,
    "image_quality_limited": false
  }
}
```

#### Core-only response (CORE_SYSTEM)

```json
{
  "water_extent_status": "shrinking",
  "flood_risk": "none",
  "water_clarity": "turbid",
  "shoreline_encroachment": true,
  "image_quality_limited": false
}
```

**Valid values per field:**

| Field | Type | Valid values |
|---|---|---|
| `water_extent_status` | string | `shrinking` `stable` `flooded` `recovering` `dry` |
| `flood_risk` | string | `none` `elevated` `active` |
| `water_clarity` | string | `clear` `turbid` `heavily_silted` |
| `shoreline_encroachment` | bool | `true` `false` |
| `image_quality_limited` | bool | `true` `false` (or `null` — treated as `false`) |

#### Buffer-only response (BUFFER_SYSTEM)

```json
{
  "agriculture_present": true,
  "crop_stress_level": "moderate",
  "crop_stress_type": "drought",
  "cultivation_expanding_toward_water": false,
  "settlement_visible": false,
  "bare_soil_expansion": true,
  "image_quality_limited": false
}
```

**Valid values per field:**

| Field | Type | Valid values |
|---|---|---|
| `agriculture_present` | bool | `true` `false` |
| `crop_stress_level` | string | `none` `low` `moderate` `severe` |
| `crop_stress_type` | string | `drought` `flood_damage` `none` |
| `cultivation_expanding_toward_water` | bool | `true` `false` |
| `settlement_visible` | bool | `true` `false` |
| `bare_soil_expansion` | bool | `true` `false` |
| `image_quality_limited` | bool | `true` `false` (or `null` — treated as `false`) |

---

### User Turn (inference-time message)

Both Claude and LM Studio/llama-server backends send this as the user turn content
after the system prompt:

```
[image: rgb_core.png]  ← RGB true-colour composite (base64 PNG)
[image: swir_core.png] ← SWIR false-colour composite (base64 PNG)
Analyse these two satellite images and return the complete JSON assessment with ALL fields present.
```

---

### Training JSONL Format

Every line in `data/train.jsonl` and `data/test.jsonl` is a single JSON object
with a `messages` array (OpenAI chat format) and a `metadata` block.

#### Core zone example

```json
{
  "messages": [
    {
      "role": "system",
      "content": [
        {
          "type": "text",
          "text": "<CORE_SYSTEM prompt — see above, filled with location values>"
        }
      ]
    },
    {
      "role": "user",
      "content": [
        { "type": "image", "image": "amazon_delta/2018-01-01/rgb_core.png" },
        { "type": "image", "image": "amazon_delta/2018-01-01/swir_core.png" },
        { "type": "text",  "text": "Analyse these satellite images and return the JSON assessment." }
      ]
    },
    {
      "role": "assistant",
      "content": [
        {
          "type": "text",
          "text": "{\"water_extent_status\": \"stable\", \"flood_risk\": \"none\", \"water_clarity\": \"turbid\", \"shoreline_encroachment\": false, \"image_quality_limited\": null}"
        }
      ]
    }
  ],
  "metadata": {
    "location_id": "amazon_delta",
    "observed_at": "2018-01-01 00:00:00+00:00",
    "zone": "core"
  }
}
```

#### Buffer zone example

```json
{
  "messages": [
    {
      "role": "system",
      "content": [{ "type": "text", "text": "<BUFFER_SYSTEM prompt>" }]
    },
    {
      "role": "user",
      "content": [
        { "type": "image", "image": "amazon_delta/2018-01-01/rgb_core.png" },
        { "type": "image", "image": "amazon_delta/2018-01-01/swir_core.png" },
        { "type": "text",  "text": "Analyse these satellite images and return the JSON assessment." }
      ]
    },
    {
      "role": "assistant",
      "content": [
        {
          "type": "text",
          "text": "{\"agriculture_present\": false, \"crop_stress_level\": \"none\", \"crop_stress_type\": \"none\", \"cultivation_expanding_toward_water\": false, \"settlement_visible\": false, \"bare_soil_expansion\": false, \"image_quality_limited\": null}"
        }
      ]
    }
  ],
  "metadata": {
    "location_id": "amazon_delta",
    "observed_at": "2018-01-01 00:00:00+00:00",
    "zone": "buffer"
  }
}
```

**Notes:**
- Image paths in the JSONL are relative to `aquaveritas/data/images/`
- `image_quality_limited: null` in ground-truth is treated as `false` by the evaluator
- Train split: observations before 2024-01-01. Test split: 2024-01-01 onwards
- Each observation produces **two** JSONL records — one `zone: core`, one `zone: buffer`

---

### LFM2.5-VL-450M Chat Template (Jinja)

LFM2.5-VL-450M uses a custom Jinja2 chat template (`chat_template.jinja`) that
implements the ChatML format with image token injection. This template is baked
into `tokenizer_config.json` and applied automatically by `apply_chat_template()`.

**Rendered wire format** (what the tokeniser actually produces):

```
<|im_start|>system
{system_prompt}<|im_end|>
<|im_start|>user
<image><image>{user_text}<|im_end|>
<|im_start|>assistant
{json_response}
```

- `<image>` tokens are injected once per image in the user turn
- Images are inserted in the order they appear in the `content` array
- The assistant block is generated without a closing `<|im_end|>` during inference
  (when `continue_final_message=True`) — the model generates until EOS or `<|im_end|>`

**Full template** (source: `LiquidAI/LFM2.5-VL-450M` on HuggingFace):

```jinja
{{- bos_token -}}
{%- set keep_past_thinking = keep_past_thinking | default(false) -%}

{%- macro parse_content(content) -%}
    {%- if content is string -%}
        {{- content -}}
    {%- else -%}
        {%- set _ns = namespace(result="") -%}
        {%- for item in content -%}
            {%- if item.type == "image" -%}
                {%- set _ns.result = _ns.result + "<image>" -%}
            {%- elif item.type == "text" -%}
                {%- set _ns.result = _ns.result + item.text -%}
            {%- else -%}
                {%- set _ns.result = _ns.result + item | tojson -%}
            {%- endif -%}
        {%- endfor -%}
        {{- _ns.result -}}
    {%- endif -%}
{%- endmacro -%}

{%- set ns = namespace(system_prompt="", last_assistant_index=-1) -%}
{%- if messages[0].role == "system" -%}
    {%- set ns.system_prompt = parse_content(messages[0].content) -%}
    {%- set messages = messages[1:] -%}
{%- endif -%}
{%- if ns.system_prompt -%}
    {{- "<|im_start|>system\n" + ns.system_prompt + "<|im_end|>\n" -}}
{%- endif -%}
{%- for message in messages -%}
    {%- if message.role == "assistant" -%}
        {%- set ns.last_assistant_index = loop.index0 -%}
    {%- endif -%}
{%- endfor -%}
{%- for message in messages -%}
    {{- "<|im_start|>" + message.role + "\n" -}}
    {%- if message.role == "assistant" -%}
        {%- generation -%}
        {%- if message.thinking is defined and (keep_past_thinking or loop.index0 == ns.last_assistant_index) -%}
            {{- "<think>" + message.thinking + "</think>" -}}
        {%- endif -%}
        {%- if message.content is defined -%}
            {%- set content = parse_content(message.content) -%}
            {{- content + ("" if (continue_final_message and loop.last) else "<|im_end|>\n") -}}
        {%- endif -%}
        {%- endgeneration -%}
    {%- else %}
        {%- if message.content is defined -%}
            {{- parse_content(message.content) + "<|im_end|>\n" -}}
        {%- endif -%}
    {%- endif %}
{%- endfor -%}
{%- if add_generation_prompt -%}
    {{- "<|im_start|>assistant\n" -}}
{%- endif -%}
```

**Key behaviours:**
- `<image>` placeholder per image content item — the vision processor replaces these with visual token embeddings
- `<think>...</think>` block supported for reasoning traces (stripped from past turns by default; only kept on the last assistant turn if `keep_past_thinking=True`)
- Tool calls rendered as `<|tool_call_start|>[func(arg=val)]<|tool_call_end|>` — not used by AquaVeritas
- `add_generation_prompt=True` appends `<|im_start|>assistant\n` to prompt inference (standard for generation)

---

### Smoke-test a running llama-server (curl)

Test that the fine-tuned model accepts the prompt and returns valid JSON:

```bash
# Text-only sanity check — no images required
curl -s http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "aquaveritas",
    "max_tokens": 256,
    "temperature": 0,
    "messages": [
      {
        "role": "system",
        "content": "You are an expert remote sensing analyst. Respond with ONLY valid JSON — no prose."
      },
      {
        "role": "user",
        "content": "Return a JSON object with key \"status\" set to \"ok\"."
      }
    ]
  }' | python3 -m json.tool
```
Expected: `choices[0].message.content` contains `{"status": "ok"}`.

```bash
# Full vision test — send real images as base64
RGB=$(base64 < data/images/lake_chad/2022-06-01/rgb_core.png)
SWIR=$(base64 < data/images/lake_chad/2022-06-01/swir_core.png)

curl -s http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"aquaveritas\",
    \"max_tokens\": 512,
    \"temperature\": 0,
    \"messages\": [
      {
        \"role\": \"system\",
        \"content\": \"You are an expert remote sensing analyst specialising in freshwater body monitoring. You are analysing Sentinel-2 satellite imagery of Lake Chad (lat 13.3°, lon 14.1°). Respond with ONLY a valid JSON object — no prose, no markdown fences.\"
      },
      {
        \"role\": \"user\",
        \"content\": [
          {\"type\": \"image_url\", \"image_url\": {\"url\": \"data:image/png;base64,${RGB}\"}},
          {\"type\": \"image_url\", \"image_url\": {\"url\": \"data:image/png;base64,${SWIR}\"}},
          {\"type\": \"text\",      \"text\": \"Analyse these satellite images and return the complete JSON assessment with ALL fields present.\"}
        ]
      }
    ]
  }" | python3 -m json.tool
```

Expected response shape:
```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "{\"water_extent_status\": \"shrinking\", \"flood_risk\": \"none\", \"water_clarity\": \"turbid\", \"shoreline_encroachment\": true, \"image_quality_limited\": false}"
      }
    }
  ]
}
```

---

### Smoke-test via LM Studio (curl)

LM Studio serves on port 8234 using the same OpenAI API format:

```bash
curl -s http://localhost:8234/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Arty1001/aquaveritas-lfm-GGUF",
    "max_tokens": 512,
    "temperature": 0,
    "messages": [
      {"role": "system", "content": "Respond with ONLY valid JSON."},
      {"role": "user",   "content": "Return {\"status\": \"ok\"}"}
    ]
  }' | python3 -c "import json,sys; r=json.load(sys.stdin); print(r['choices'][0]['message']['content'])"
```

> **Vision test with LM Studio:** same as the llama-server curl above but replace
> `http://localhost:8080` with `http://localhost:8234` and `"model": "aquaveritas"` with
> `"model": "Arty1001/aquaveritas-lfm-GGUF"` (or the model ID shown in
> `GET /v1/models`).

---

### Quick Python test (Anthropic SDK)

```python
import anthropic, base64, json
from pathlib import Path

client = anthropic.Anthropic()

def b64(path): return base64.standard_b64encode(Path(path).read_bytes()).decode()

msg = client.messages.create(
    model      = "claude-opus-4-6",
    max_tokens = 512,
    system     = (
        "You are an expert remote sensing analyst specialising in freshwater body monitoring. "
        "You are analysing Sentinel-2 satellite imagery of Lake Chad (lat 13.3°, lon 14.1°). "
        "Respond with ONLY a valid JSON object — no prose, no markdown fences."
    ),
    messages   = [{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": b64("data/images/lake_chad/2022-06-01/rgb_core.png")}},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": b64("data/images/lake_chad/2022-06-01/swir_core.png")}},
            {"type": "text", "text": "Analyse these satellite images and return the complete JSON assessment with ALL fields present."},
        ],
    }],
)
result = json.loads(msg.content[0].text)
print(json.dumps(result, indent=2))
```

---

## Quick Reference

| Command | Stage | Duration |
|---|---|---|
| `docker compose up -d` | Setup | seconds |
| `collect_data.py --workers 3` | Collection | ~72 min |
| `triage_images.py --heuristic` | Triage P1 | ~3 min |
| `triage_images.py --model X --retriage-heuristic` | Triage P2 | ~50 min |
| `triage_images.py --export-manifest --export-only` | Audit | seconds |
| `label_data.py --batch 500` | Labelling | ~hours |
| `train.py --hf-repo X` | Export | ~10 min |
| `finetune.py --hf-model-repo X --quantize` | Fine-tune | ~2–4 hrs |
| `llama-server --model <gguf> --port 8080` | Load model | seconds |
| `evaluate.py --backend llama` | Eval — fine-tuned LFM | ~15 min |
| `evaluate.py --backend claude` | Eval — oracle baseline | ~30 min |
| `predict.py` | Live loop | continuous |
| `streamlit run app/app.py` | Dashboard | continuous |
| `bash scripts/push_hf_space.sh` | HF Space push | ~2 min |
| `modal app list` | Check running Modal jobs | seconds |
| `modal volume ls aquaveritas-data` | Inspect volume contents | seconds |
| `gh pr view 5 --repo DPhi-Space/SimSat` | View submission PR | seconds |
| `test_prose_qwen.py` | Prose model test | ~30s |
| `generate_incident_report.py` | PDF registry rebuild | seconds |
| `leap-bundle list` | List LEAP bundle requests | seconds |
| `leap-bundle validate <dir>` | Validate model dir before upload | seconds |
| `leap-bundle cancel <id>` | Cancel a failed/stale bundle | seconds |
| `leap-bundle create <dir> --quantization Q8_0 --mmproj-quantization f16` | Submit bundle to LEAP platform | ~5–15 min |
| `leap-bundle download <id> --output-path <dir>` | Download completed bundle | variable |
| `leap-bundle resume <id>` | Resume interrupted upload | variable |
