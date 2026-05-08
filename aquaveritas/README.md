# AquaVeritas

**Fine-tuned LFM2.5-VL detects freshwater body collapse via Sentinel-2. 20 global sites, real-time inference, analyst-ready prose.**

Built for the [Liquid AI x DPhi Space Hackathon: AI in Space (Hack #05)](https://luma.com/n9cw58h0) on the SimSat platform.

---

## What it does

AquaVeritas is an end-to-end satellite freshwater intelligence system. A fine-tuned LFM2.5-VL-450M vision-language model classifies Sentinel-2 imagery across 16 primary freshwater sites and 4 saline control sites, producing structured labels and analyst-ready prose briefs for each observation.

- **20 monitored sites** across 6 continents: lakes, river deltas, seasonal wetlands, and saline controls
- **11 structured classification fields** per observation: water extent status, flood risk, water clarity, shoreline encroachment, crop stress, bare soil expansion, and more
- **Cloud-aware inference**: PIL-based cloud fraction estimation with three-tier rendering (full, degraded, blocked)
- **Analyst prose**: Claude Haiku converts structured JSON into three-paragraph mission briefs
- **Live prediction loop**: polls the SimSat satellite API every 30 seconds, triggers on proximity to monitored sites
- **Streamlit dashboard**: interactive pydeck globe, per-site observation history, live prediction tab

## Model

The fine-tuned model is hosted on HuggingFace:

- **GGUF (backbone + vision projector):** [Arty1001/aquaveritas-lfm-GGUF](https://huggingface.co/Arty1001/aquaveritas-lfm-GGUF)
- Base model: [LiquidAI/LFM2.5-VL-450M](https://huggingface.co/LiquidAI/LFM2.5-VL-450M)
- Training: 328 curated Sentinel-2 observations, annotated by Claude claude-opus-4-5 oracle
- Accuracy uplift: 38% (base) to 84% (fine-tuned) overall

## Monitored sites

| Category | Sites |
|---|---|
| Chronic shrinkage | Lake Chad |
| Flooding / seasonal | Lake Victoria, Tonle Sap, Okavango Delta |
| Mixed / agricultural | Lake Garda, Mekong Delta, Lake Turkana, Lake Titicaca |
| River deltas | Nile Delta, Tana River, Omo River, Amazon, Danube, Mesopotamian Marshes, Niger Delta, Lower Congo |
| Saline controls | Dead Sea, Lake Urmia, Aral Sea, Salton Sea |

## Requirements

- Python >= 3.10
- Docker and Docker Compose (for SimSat + PostgreSQL)
- [llama-server](https://github.com/ggerganov/llama.cpp) (for local VLM inference)
- Anthropic API key (for prose generation via Claude Haiku)
- Mapbox API token (for dashboard basemap)

## Setup

### 1. Clone and install

```bash
git clone https://github.com/devleks/SimSat.git
cd SimSat/aquaveritas
pip install -e .
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set:
# DATABASE_URL=postgresql://aqua:<password>@localhost:5433/aquaveritas
# ANTHROPIC_API_KEY=sk-...
```

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit and set MAPBOX_TOKEN=pk.eyJ1...
```

### 3. Start infrastructure

```bash
# From SimSat root
docker compose up -d

# Download fine-tuned model weights
# Place in aquaveritas/data/models/:
#   aquaveritas-lfm-q8_0.gguf
#   mmproj-LFM2.5-VL-450m-F16.gguf
# Download from: https://huggingface.co/Arty1001/aquaveritas-lfm-GGUF

# Start inference server
llama-server \
  -m data/models/aquaveritas-lfm-q8_0.gguf \
  --mmproj data/models/mmproj-LFM2.5-VL-450m-F16.gguf \
  --port 8080 --ctx-size 8192 -ngl 99 --host 127.0.0.1 --log-disable
```

### 4. Run the dashboard

```bash
streamlit run app/app.py
# Open http://localhost:8501
```

### 5. Run the live prediction loop

```bash
python scripts/predict.py --interval 30 --model-url http://localhost:8080
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | Yes | For Claude Haiku prose generation |
| `MAPBOX_ACCESS_TOKEN` | Yes | For Docker Compose map basemap |

Mapbox token for the Streamlit dashboard is set in `.streamlit/secrets.toml` (see `.streamlit/secrets.toml.example`).

## Project structure

```
aquaveritas/
├── app/
│   └── app.py                  # Streamlit dashboard (3 tabs: globe, live prediction, dataset)
├── src/aquaveritas/
│   ├── db.py                   # PostgreSQL + PostGIS layer
│   ├── locations.py            # 20 monitored site definitions
│   ├── prose.py                # Claude Haiku prose generation
│   ├── annotator.py            # VLM annotation wrapper
│   └── evaluator.py            # Evaluation framework
├── scripts/
│   ├── collect_data.py         # Sentinel-2 tile collection
│   ├── triage_images.py        # Image quality triage
│   ├── label_data.py           # Claude oracle annotation
│   ├── predict.py              # Live satellite prediction loop
│   ├── evaluate.py             # Model evaluation
│   └── train.py                # HuggingFace dataset export
├── configs/
│   └── aquaveritas_finetune_modal.yaml   # leap-finetune + Modal H100 config
├── docs/
│   └── COMMANDS.md             # Full command reference
├── data/
│   ├── models/                 # GGUF model weights (gitignored, download separately)
│   └── images/                 # Observation imagery (gitignored)
├── pyproject.toml
└── .env.example
```

## Fine-tuning

Fine-tuning used [leap-finetune](https://github.com/LiquidAI/leap-finetune) on a Modal H100, following the [Liquid AI wildfire prevention cookbook](https://github.com/Liquid4All/cookbook/blob/main/examples/wildfire-prevention/README.md). Full weight fine-tuning (not LoRA) was required to retrain the multimodal projector on out-of-distribution satellite multispectral imagery.

```bash
# Export dataset to HuggingFace
python scripts/train.py --hf-repo devleks/aquaveritas-water-stress

# Run fine-tuning on Modal H100
python scripts/finetune.py
cd leap-finetune && uv run leap-finetune ../configs/aquaveritas_finetune_modal.yaml
```

## Licence

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**, inherited from the [SimSat](https://github.com/DPhi-Space/SimSat) upstream platform on which it is built. See [LICENSE](LICENSE) for the full text.

The fine-tuned model weights are governed separately by the **LFM Open License v1.0** from Liquid AI. Commercial use is permitted for organisations with annual revenue below $10M USD. See the [model card](https://huggingface.co/Arty1001/aquaveritas-lfm-GGUF) for details.

## Acknowledgements

- [DPhi Space](https://dphi.tech/) and [Liquid AI](https://www.liquid.ai/) for the SimSat platform and LFM2.5-VL model
- [Sentinel-2](https://sentinel.esa.int/web/sentinel/missions/sentinel-2) (ESA Copernicus) for satellite imagery
- [Anthropic](https://www.anthropic.com/) for Claude claude-opus-4-5 (oracle annotation) and Claude claude-haiku-4-5 (prose generation)
