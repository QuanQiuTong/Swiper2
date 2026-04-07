# Swiper2: Android UI Automation & Dataset Synthesis

Swiper2 is an automated exploration and interaction synthesis tool designed for Android UI testing. It focuses on collecting high-quality dynamic sliding (swipe) and clicking interactions without human intervention.

## Pipeline Overview

- **Phase 1 (Automated Exploration):** Rapidly explores application pages using DFS/BFS algorithms based on XML accessibility trees, building a structured state-graph of the application UI.
- **Phase 2 (Interaction Synthesis):** Leverages a Vision-Language Model (VLM) offline to identify slidable regions and generate natural language intents. It then physically replays trajectories to verify and collect valid `<Before_Image, Intent, Action, After_Image>` pairs.

## Installation

1. Install basic dependencies:
```bash
pip install -r requirements.txt
```
2. *(Optional)* If using a local VLM for offline synthesis, install PyTorch and Transformers:
```bash
pip install torch transformers pillow
```

## Usage

1. **Device Connection:**
   Connect your Android device (physical smartphone or emulator) and ensure it is authorized via ADB (`adb devices`).

2. **Configuration:**
   Specify the target Application package names in `utils/packages.py`.

3. **Run Exploration & Synthesis:**
```bash
python explore.py
```
*Note: After execution, all screenshots, XML view hierarchies, and trajectory JSONs will be saved in the `./outputs/{package_name}_dataset` directory.*

4. **Data Aggregation:**
To aggregate and clean the verified interaction data into a unified dataset structure, run the ultimate summary script:
```bash
python utils/summary_ultimate.py
```
This will output the final clean dataset into the `./summary/all` directory.
