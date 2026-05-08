# AquaVeritas — Setup Guide

## What this guide covers

| Section | For whom |
|---|---|
| [Local app](#local-app) | Running the full 4-tab dashboard on your machine |
| [HF Space deployment](#hf-space-deployment) | Pushing a SQLite snapshot to the HuggingFace Space |

---

## Local app

The local app runs the full pipeline: PostgreSQL, llama-server (GGUF inference), and Streamlit.

### Prerequisites

- Python 3.11+
- Docker + Docker Compose (for the SimSat satellite simulator)
- PostgreSQL 15+ with PostGIS (`brew install postgresql@18 postgis` on macOS)
- A [Mapbox](https://www.mapbox.com/) account with a free access token
- A Hugging Face account (for the GGUF model download)

---

### 1. Clone and install

```bash
git clone https://github.com/devleks/AquaVeritas.git
cd AquaVeritas

# Install the aquaveritas package and dependencies
pip install -e aquaveritas/
```

---

### 2. Environment variables

Create `aquaveritas/.env`:

```bash
# PostgreSQL (Docker maps 5433 on host → 5432 in container)
DATABASE_URL=postgresql://aqua:aqua@localhost:5433/aquaveritas

# Mapbox — required for globe base map
MAPBOX_TOKEN=pk.eyJ1IjoiY...

# SimSat simulator
SIMSAT_URL=http://localhost:9005

# Llama server (local GGUF inference)
LLAMA_SERVER_URL=http://localhost:8080
```

---

### 3. Start PostgreSQL with PostGIS

```bash
# macOS Homebrew — start only if not already running
brew services start postgresql@18

# Create the database and role
psql -U $(whoami) -c "CREATE ROLE aqua WITH LOGIN PASSWORD 'aqua';"
psql -U $(whoami) -c "CREATE DATABASE aquaveritas OWNER aqua;"
psql -U $(whoami) -d aquaveritas -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

> **Port note:** The Docker SimSat container uses PostgreSQL on port 5432. To avoid
> conflicts, the Docker Compose file maps the Postgres service to port **5433** on
> the host (`5433:5432`). The `DATABASE_URL` above reflects this.

---

### 4. Start the SimSat simulator

```bash
docker compose up -d
```

Then open [http://localhost:8000](http://localhost:8000), press **Start** in the
Simulation Controls panel, and leave the simulator running.

---

### 5. Download and run the GGUF model

```bash
# Download both GGUF files (mmproj + main model)
huggingface-cli download Arty1001/aquaveritas-lfm-GGUF \
  --local-dir ~/.cache/aquaveritas-gguf

# Start llama-server (adjust --n-gpu-layers for your hardware)
llama-server \
  --model ~/.cache/aquaveritas-gguf/aquaveritas-lfm-Q4_K_M.gguf \
  --mmproj ~/.cache/aquaveritas-gguf/aquaveritas-lfm-mmproj.gguf \
  --port 8080 \
  --n-gpu-layers 999
```

> llama.cpp must be built with your GPU backend (Metal on Apple Silicon, CUDA on
> NVIDIA). See [llama.cpp](https://github.com/ggerganov/llama.cpp) for build
> instructions.

---

### 6. Run the pipeline

First, collect observations for all 20 sites:

```bash
cd aquaveritas/
python -m aquaveritas.pipeline
```

This may take 10–30 minutes on first run (Sentinel-2 API is slow). Subsequent runs
only process new timestamps.

---

### 7. Launch the dashboard

```bash
streamlit run aquaveritas/app/app.py
```

Open [http://localhost:8501](http://localhost:8501).

The dashboard has four tabs:

| Tab | What it shows |
|---|---|
| Global Monitor | Globe map of all 20 sites + time-series charts |
| Location Detail | Per-site deep-dive with observation history |
| Model Evaluation | Annotation audit and VLM accuracy metrics |
| Live Prediction | On-demand inference for any site at any timestamp |

---

## HF Space deployment

The HuggingFace Space at [Arty1001/aquaveritas](https://huggingface.co/spaces/Arty1001/aquaveritas)
runs a read-only 2-tab showcase (Global Monitor + Dataset). It uses a SQLite snapshot
of the PostgreSQL database — no live inference, no llama-server required.

### Prerequisites

- `huggingface-cli` logged in (`huggingface-cli login`)
- Local PostgreSQL running with data (see steps 1–6 above)
- The HF Space repo cloned or accessible (the script handles this automatically)

### Update the Space

```bash
bash scripts/push_hf_space.sh
```

This script:

1. Exports the PostgreSQL `observations` table to `aquaveritas/hf_space/data/observations.db`
2. Pushes the entire `aquaveritas/hf_space/` directory to the HF Space repo

### HuggingFace secrets

In the Space settings, add the following secret:

| Secret name | Value |
|---|---|
| `MAPBOX_TOKEN` | Your Mapbox public access token |

The Space reads `MAPBOX_TOKEN` from the environment. If absent, it falls back to a
CartoDB dark-matter base map (no token required, but lower quality).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `role "aqua" does not exist` | PostgreSQL not initialised | Run the `CREATE ROLE` command in step 3 |
| `Connection refused :5432` | Homebrew PostgreSQL intercepting Docker port | Ensure `DATABASE_URL` uses port 5433 |
| Black wedges in satellite images | MGRS tile boundary straddled | Expected for some sites; use 30-day window |
| `image_available: false` | Site over ocean or polar gap | Normal for ocean-adjacent tiles |
| llama-server OOM | Model too large for VRAM | Lower `--n-gpu-layers` or use Q2_K quantisation |
