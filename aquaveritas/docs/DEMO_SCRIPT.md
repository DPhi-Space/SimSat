# AquaVeritas — Video Demo Script
**Hackathon submission · Liquid AI × DPhi Space · Hack #05**
*Target runtime: 3–4 minutes*

---

## SCENE 1 — Hook (0:00–0:20)

**[Screen: black. Text fades in.]**

> *"1.8 billion people live in areas of physical water scarcity."*
> *"Every week, another lake disappears."*

**[Cut to: satellite imagery of the Aral Sea — 1990 vs today. Side by side.]**

**NARRATION:**
> Traditional water monitoring relies on ground stations, manual surveys, and slow-moving reports. By the time the data reaches decision makers, the damage is done.
>
> What if a satellite could detect collapse in real time — and tell you exactly what it sees, in plain language?

---

## SCENE 2 — Introducing AquaVeritas (0:20–0:45)

**[Screen: AquaVeritas dashboard loads. Global Monitor tab visible with the globe showing 20 coloured site markers.]**

**NARRATION:**
> This is AquaVeritas. An on-board satellite AI system that monitors 20 critical freshwater bodies across the globe — continuously — using Sentinel-2 multispectral imagery and a fine-tuned vision-language model running directly on the satellite.

**[Screen: slow pan across the globe. Red dots on Lake Chad, Aral Sea, Lake Urmia. Green on Lake Garda, Lake Victoria.]**

> Each coloured marker tells a story. Red: the water body is shrinking. Green: recovering. We're monitoring the Dead Sea, Lake Chad, the Aral Sea — sites that scientists have been watching for decades, now tracked from orbit, automatically, every pass.

---

## SCENE 3 — The SimSat API (0:45–1:05)

**[Screen: split — SimSat Django dashboard on left showing the satellite orbit. Terminal on right showing a quick API call.]**

**NARRATION:**
> AquaVeritas is built entirely on the SimSat platform. The SimSat API gives us the satellite's current position and timestamp, and serves Sentinel-2 imagery for any location on demand.

**[Screen: show the API response JSON with `lon-lat-alt` and `timestamp`.]**

> From that, we fetch four images per site — RGB and SWIR bands, for the core water body and the surrounding agricultural buffer. Four images, two zones, one pass.

**[Screen: show two Sentinel-2 image tiles side by side — RGB true colour and SWIR false colour — of Lake Urmia or Aral Sea.]**

---

## SCENE 4 — Live Prediction (1:05–2:10)

**[Screen: switch to AquaVeritas dashboard, Live Prediction tab.]**

**NARRATION:**
> Now for the intelligence layer. Let me run a live prediction.

**[ACTION: Select "Aral Sea South Basin" from the sidebar dropdown. The coordinates auto-fill.]**

> I'm selecting the Aral Sea South Basin — one of the most dramatic water body collapses in recorded history.

**[ACTION: Click "Run Prediction". Progress indicator starts.]**

> AquaVeritas fetches the four Sentinel-2 tiles, encodes them as base64, and sends them to our fine-tuned LFM2.5-VL-450M model — running on-board via llama-server. No cloud, no round-trip to Earth.

**[Screen: images appear — RGB shows arid, reddish terrain with minimal water. SWIR shows clear boundary lines. Model response starts populating.]**

> The model classifies across eleven fields simultaneously: water extent status, flood risk, water clarity, shoreline encroachment — and in the agricultural buffer zone: crop stress level, cultivation expansion, settlement presence.

**[Screen: badge panel fills in. "Water Extent Status: Shrinking" in red. "Flood Risk: None". "Water Clarity: Poor". "Shoreline Encroachment: true".]**

> And then — in plain language:

**[Screen: prose summary appears in the observation card.]**

> *"Severe and ongoing water body contraction is evident across both the core and buffer zones. The shoreline has retreated significantly, exposing extensive salt flats and bare soil. Agricultural activity in the buffer zone shows signs of water stress, with reduced crop vigour visible in the SWIR composite."*

> That is LFM2.5-VL-450M — a 450 million parameter model — producing analyst-grade prose from satellite imagery. On-board. Under 30 seconds per site.

---

## SCENE 5 — Model Performance (2:10–2:45)

**[Screen: Model Evaluation tab. Three-way accuracy table visible.]**

**NARRATION:**
> How good is it? We evaluated against a Claude Opus oracle on a held-out test set — observations the model never saw during training.

**[Screen: highlight the three-way comparison row: Oracle 86.3%, Base 18.0%, Fine-tuned 85.4%.]**

> The base LFM2.5-VL-450M scores 18% out of the box. After fine-tuning on 1,280 labeled observations — that becomes 85.4%. A 67-point lift.

**[Screen: highlight individual field rows — water clarity 96.7%, shoreline encroachment 96.7%.]**

> On water clarity and shoreline encroachment, the fine-tuned model actually outscores the oracle. 96.7% accuracy. The model has learned to read the spectral signature of sediment, salinity, and exposed shoreline directly from SWIR bands.

**[Screen: show the training stats — 3 epochs, Modal H100, final loss 0.011.]**

> Three epochs on a Modal H100. Final training loss: 0.011. The model is compact enough to run on constrained hardware — exactly what you need at the edge.

---

## SCENE 6 — Global Monitor (2:45–3:05)

**[Screen: back to Global Monitor tab. Select "— All sites —" to show the full globe.]**

**NARRATION:**
> Zoom out. Twenty sites, real data, real observations. The time series panel shows water extent status month by month. You can see sustained shrinkage alerts — sites where the model has classified "shrinking" for three or more consecutive passes.

**[Screen: scroll down to the Sustained Shrinkage Alerts section. Highlight a site like Lake Turkana or Aral Sea with a 6+ streak.]**

> These are the sites that need immediate attention. AquaVeritas surfaces them automatically, every pass, without a human analyst in the loop.

---

## SCENE 7 — Live Demo & Closing (3:05–3:30)

**[Screen: open browser to HF Space — Arty1001/aquaveritas.]**

**NARRATION:**
> You can explore the full observation dataset right now at the HuggingFace Space — link in the description. All 1,656 observations, 20 sites, interactive globe, filterable dataset.

**[Screen: show the globe with light Mapbox basemap. Click on Lake Chad marker — observation card appears.]**

> The full system — SimSat integration, live inference, PostgreSQL pipeline, and Streamlit dashboard — is open source on GitHub.

**[Screen: final frame — AquaVeritas title card with logos, links, and the tagline.]**

> AquaVeritas. Freshwater intelligence, from orbit.
>
> Built for Hack #05 — AI in Space. Liquid AI × DPhi Space.

---

## PRODUCTION NOTES

**Sections to record:**
| Scene | Duration | Screen content |
|---|---|---|
| 1 — Hook | ~20s | Aral Sea before/after imagery (find CC images) |
| 2 — Dashboard intro | ~25s | Global Monitor globe, all 20 markers |
| 3 — SimSat API | ~20s | SimSat dashboard + quick terminal API call |
| 4 — Live Prediction | ~65s | Full prediction run on Aral Sea South Basin |
| 5 — Model Performance | ~35s | Eval tab, three-way comparison, field accuracies |
| 6 — Global Monitor | ~20s | Full globe, shrinkage alerts |
| 7 — HF Space + close | ~25s | HF Space live, GitHub, title card |

**Key numbers to call out:**
- 20 global freshwater sites
- 85.4% overall accuracy (vs 18% base model)
- +67.4% uplift from fine-tuning
- 96.7% on water clarity and shoreline encroachment
- 1,656 observations in the dataset
- 450M parameter model — runs on-board

**Tone:** Confident, technical, urgent. Not sales-y. This is a systems demo for engineers and researchers.

**Music:** Sparse, cinematic underscore. No beat drops. Something that reads as "serious science."
