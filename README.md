# QGIS LOOM Transit Map Generator

A cross-platform QGIS plugin that wraps the [LOOM](https://github.com/ad-freiburg/loom) transit map generation suite with a friendly GUI. Generate schematic and geographically accurate transit maps directly inside QGIS — no command line required.

**LOOM** © University of Freiburg (Hannah Bast, Patrick Brosi, Sabine Storandt), GPL-3.0.  
**Windows port & QGIS plugin** by [Transport for Cairo](https://transportforcairo.com), 2026.

---

## Installation

Works with **QGIS 3.16+ and QGIS 4.x** on:

| Platform | Pre-built binaries |
|---|---|
| Windows 10/11 x64 | ✔ |
| macOS 12+ on Apple Silicon (M1 or newer) | ✔ — no Homebrew needed |
| Linux x64 (glibc 2.34+: Ubuntu 22.04+, Debian 12+, Fedora 35+) | ✔ — no extra packages needed |
| Intel Macs, ARM Linux | ✘ — build LOOM from source and put it on your `PATH` |

1. Download the latest plugin ZIP from the [Releases](../../releases) page.
2. In QGIS: **Plugins → Manage and Install Plugins → Install from ZIP**.
3. Enable **LOOM Transit Map Generator** in the plugin list.
4. Click the toolbar button — on first run the plugin will automatically download the pre-built LOOM binaries for your platform (~3–35 MB, one-time).

No compiling required.

---

## Usage

1. Open the plugin via **Plugins → LOOM Transit Maps** or the toolbar button.
2. **Input tab** — select a QGIS vector layer, a GeoJSON file, or a GTFS zip. For GTFS, keep **All modes** or tick any combination of transport modes (bus, tram, metro, rail, …).
3. **Options tab** — choose render style, labels, line widths, ILP solver.
4. **Output tab** — set a save path and/or load the result directly into QGIS.
5. Click **Run Pipeline**.

### Render styles

| Style | Description |
|---|---|
| Geographic | Lines on their real-world geometry |
| Octilinear | Schematic map on a 45°/90° grid (metro-map style) |
| Orthoradial | Schematic map on a radial/concentric grid |

### Pipeline

```
[gtfs2graph]  →  topo  →  loom  →  [octi]  →  transitmap  →  SVG / MVT
```

All stages run as `subprocess.PIPE` chains — no shell redirection, works identically on Windows, macOS, and Linux.

---

## Binaries

Pre-built binaries are hosted at [transportforcairo/loom_binaries](https://github.com/transportforcairo/loom_binaries) and downloaded automatically on first run. To re-download or update, go to the plugin's **Diagnostics tab → Re-download binaries**.

Each plugin version downloads from a fixed tag of that repo (`BINARIES_REF` in `downloader.py`) and checks the ZIP against the tag's `SHA256SUMS` before installing. When binaries from an older build are found, the plugin offers to update them.

GTFS zips are unzipped by the plugin and passed to `gtfs2graph` as a folder, so the binaries do not need libzip.

### Releasing a new plugin version that needs new binaries

1. In `loom_binaries`: rebuild (Actions → *Build and Commit Binaries*), make sure *Verify checksums* is green, then push a tag, e.g. `git tag v1.2.0 && git push origin v1.2.0`.
2. Here: set `BINARIES_REF` in `downloader.py` to that tag, bump `version` and `changelog` in `metadata.txt`, and release.

The tag must exist before the plugin is published, otherwise downloads fail.

---

## Repository structure

```
loom_qgis/
├── __init__.py            QGIS classFactory entry point
├── loom_plugin.py         Plugin lifecycle (menu, toolbar, first-run / update check)
├── dialog.py              Main Qt dialog (Input / Options / Output / Diagnostics)
├── runner.py              Subprocess pipeline runner (unzips GTFS input)
├── binary_resolver.py     OS detection and binary path resolution
├── downloader.py          Binary downloader (pinned tag + SHA-256 check)
├── download_dialog.py     Download / update UI
├── webmap_generator.py    Interactive HTML web map from the SVG
├── metadata.txt           QGIS plugin metadata
├── bin/
│   ├── windows/           Populated automatically by downloader
│   ├── macos/             Populated automatically by downloader
│   └── linux/             Populated automatically by downloader
├── resources/
│   └── icon.png
├── .github/workflows/
│   └── qgis4-check.yml    PyQGIS 4 checker + Qt 6 smoke test
├── README.md
└── LICENSE
```

---

## Documentation

More details are available in the **User Guide (PDF)**:  
[**loom_qgis_user_guide.pdf**](https://github.com/transportforcairo/loom_qgis/blob/main/loom_qgis_user_guide.pdf)

---

## Attribution

This plugin uses [LOOM](https://github.com/ad-freiburg/loom), developed by Hannah Bast, Patrick Brosi, and Sabine Storandt at the University of Freiburg, licensed under GPL-3.0. Windows port by [Transport for Cairo](https://transportforcairo.com), 2026.

Key publications:
- Bast, Brosi, Storandt. *Efficient Generation of Geographically Accurate Transit Maps.* SIGSPATIAL 2018.
- Bast, Brosi, Storandt. *Metro Maps on Octilinear Grid Graphs.* EuroVis 2020.
- Bast, Brosi, Storandt. *Metro Maps on Flexible Base Grids.* SSTD 2021.

---

## Licence

GPL-3.0 — matching the upstream LOOM project.
