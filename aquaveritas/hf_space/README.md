---
title: AquaVeritas
emoji: 🛰
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: agpl-3.0
---

# AquaVeritas

**Fine-tuned LFM2.5-VL-450M detects freshwater body collapse via Sentinel-2.**

Built for the [Liquid AI x DPhi Space Hackathon: AI in Space (Hack #05)](https://luma.com/n9cw58h0).

## What this Space shows

This Space is a **read-only showcase** of the AquaVeritas pipeline. It displays
pre-computed observations for 20 global freshwater sites stored in a SQLite snapshot
exported from the live system.

| Tab | Contents |
|---|---|
| Global Monitor | Globe map of all 20 sites, time-series charts, latest observation card |
| Dataset | Filterable observation table, status distribution, site coverage charts |

**Live prediction (on-demand VLM inference) runs on local hardware only** and is
not available in this Space. To run the full 4-tab system locally, see
[SETUP.md](https://github.com/devleks/AquaVeritas/blob/main/SETUP.md).

## Links

- **Model:** [Arty1001/aquaveritas-lfm-GGUF](https://huggingface.co/Arty1001/aquaveritas-lfm-GGUF)
- **Code:** [github.com/devleks/AquaVeritas](https://github.com/devleks/AquaVeritas)
- **Dataset:** [devleks/aquaveritas-water-stress](https://huggingface.co/datasets/devleks/aquaveritas-water-stress)
- **Setup guide:** [SETUP.md](https://github.com/devleks/AquaVeritas/blob/main/SETUP.md)

## Space secrets

| Secret name | Required | Purpose |
|---|---|---|
| `MAPBOX_TOKEN` | Optional | Mapbox dark satellite base map (falls back to CartoDB if absent) |
