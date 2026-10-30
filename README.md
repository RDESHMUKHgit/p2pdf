# P2PDF — Photo to PDF Converter for Windows

<div align="center">

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%20Windows%2011-blue?logo=windows)](https://github.com/RDESHMUKHgit/p2pdf)
[![Python](https://img.shields.io/badge/Python-3.12%2B-brightgreen?logo=python)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Tests-65%2F65%20Passed-success?logo=pytest)](https://github.com/RDESHMUKHgit/p2pdf)
[![Packaging](https://img.shields.io/badge/Installer-Inno%20Setup%206-orange)](https://github.com/RDESHMUKHgit/p2pdf/releases)
[![Build](https://img.shields.io/badge/Standalone-PyInstaller%206-blueviolet)](https://github.com/RDESHMUKHgit/p2pdf)

**A lightning-fast, lightweight Windows utility to combine multiple photos into a single, losslessly optimized PDF directly from File Explorer.**

[Download Installer](https://github.com/RDESHMUKHgit/p2pdf/releases) • [Features](#key-features) • [Tech Stack](#tech-stack) • [Installation](#installation) • [CLI Reference](#command-line-interface-cli) • [Configuration](#configuration-p2pdfini) • [Contributing](#contributing--future-roadmap)

</div>

---

## Overview

**P2PDF** is built for simplicity, speed, and reliability. Instead of opening bulky PDF editing applications or uploading sensitive personal documents to third-party online converters, P2PDF integrates directly into the native Windows File Explorer:

1. **Select** any group of photos (`.jpg`, `.jpeg`, `.png`, `.webp`).
2. **Right-click** and choose **"Create PDF with P2PDF"**.
3. **Done!** A perfectly formatted, losslessly compressed PDF is ready in seconds in the same folder.

P2PDF is designed strictly as a **lightweight desktop utility** — there are no bloated multi-window GUIs, no background telemetry, and no complex setup steps.

---

## Key Features

- **Seamless Windows File Explorer Integration**:
  - Right-click context-menu verb (`Create PDF with P2PDF`) filtered using Windows Advanced Query Syntax (`AppliesTo`) to only appear when supported images are selected.
  - Companion **Send to -> Create PDF with P2PDF** shortcut for instant alternative access.
  - Installs cleanly per-user (`HKCU`) without requiring administrator privileges or UAC prompts.
- **Single-Instance Mutex Aggregation (`aggregator.py`)**:
  - Solves the Windows Explorer multi-select limitation where Explorer launches a separate process for each selected photo.
  - Automatically elects a Primary instance via a Windows Named Mutex, debounces and collects all selected file paths from concurrent launches, and converts them as a **single batch into one combined PDF with one notification**.
- **100% Lossless Embedding & Zero Generation Loss**:
  - Directly extracts raw JPEG byte streams and encapsulates them into PDF raster structures without decoding or re-encoding.
  - Original camera quality, resolution, and color profiles are preserved bit-for-bit.
- **Lossless Structural Stream Optimization (`pikepdf`)**:
  - Packs internal PDF objects into compressed Object Streams.
  * Reduces final PDF file sizes by 10%–25% with zero pixel alterations.
  - Strict verification: only writes optimized streams if they are strictly smaller than the original.
- **Full EXIF Camera Orientation Support**:
  - Correctly auto-rotates photos according to all 8 EXIF orientation tags (rotations and mirror reflections).
- **Alpha Channel & Soft Mask Rendering**:
  - Renders PNG and WebP images with transparency cleanly against white page backgrounds using PDF soft masks (`/SMask`).
- **Collision-Safe & Atomic File Staging**:
  - Automatically avoids overwriting existing files by incrementing to `Photos (1).pdf`, `Photos (2).pdf`, etc.
  - **Input Protection**: Strictly prevents overwriting input source photos, even if the destination filename matches an input photo.
  - **Atomic Writing**: Writes to a staging file (`.tmp`) first; atomically commits to destination only after complete conversion and verification.
- **Configurable Geometry**:
  - Supports **A4** (default), **A3**, **A5**, **Letter**, and **Legal**.
  - Automatic landscape/portrait page orientation matching each image's aspect ratio.

---

## Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| **Language** | Python 3.12+ (tested up to 3.14) | Core application logic and aggregation |
| **Image Engine** | [Pillow (PIL)](https://pillow.readthedocs.io/) | Header validation, EXIF parsing, color mode normalization |
| **PDF Generation** | [img2pdf](https://gitlab.mister-muffin.de/josch/img2pdf) | Fast, lossless direct JPEG stream embedding |
| **PDF Optimization** | [pikepdf](https://pikepdf.readthedocs.io/) (QPDF engine) | Lossless structural stream compression & compaction |
| **Windows Integration** | Win32 API via standard `ctypes` | Windows Named Mutex, `MessageBoxW`, registry integration |
| **Executable Packaging** | [PyInstaller 6](https://pyinstaller.org/) | Standalone windowless executable with PE version metadata |
| **Setup Installer** | [Inno Setup 6](https://jrsoftware.org/isinfo.php) | Per-user Windows installer wizard (`PrivilegesRequired=lowest`) |
| **Testing** | `pytest`, `pypdfium2` | Automated unit, regression, and rendering validation |

---

## Installation

### Option 1: Windows Installer Wizard (Recommended)
1. Download **`P2PDF-Setup-v1.5.0.exe`** from [GitHub Releases](https://github.com/RDESHMUKHgit/p2pdf/releases).
2. Run the setup wizard (no administrator rights needed).
3. P2PDF installs to `%LOCALAPPDATA%\Programs\P2PDF\` and configures Explorer right-click integration automatically.
4. Upgrades preserve your existing `p2pdf.ini` settings. You can uninstall anytime via Windows **Settings > Apps > Installed apps**.

### Option 2: Portable ZIP (Zero Installation)
1. Download **`P2PDF-v1.5.0-portable.zip`** from [GitHub Releases](https://github.com/RDESHMUKHgit/p2pdf/releases).
2. Extract anywhere on your system or run from a USB drive.
3. Drag-and-drop photos onto `P2PDF.exe`, or double-click `install_context_menu.bat` to enable right-click integration.

### Option 3: Build from Source
Requirements: Python 3.12+ on Windows.

```bash
# 1. Clone the repository
git clone https://github.com/RDESHMUKHgit/p2pdf.git
cd p2pdf

# 2. Install dependencies
pip install -r requirements-dev.txt

# 3. Run automated test suite (65 tests)
python -m pytest -v

# 4. Compile standalone executable with version resources
.\build.bat
```
The compiled executable will be located at `dist\P2PDF.exe`.

---

## How to Use

### 1. File Explorer Context Menu
* **Windows 10**: Select photos -> Right-click -> **"Create PDF with P2PDF"**.
* **Windows 11**: Select photos -> Right-click -> **"Show more options"** (`Shift + F10`) -> **"Create PDF with P2PDF"** (or use **"Send to" -> "Create PDF with P2PDF"**).

### 2. Drag & Drop
Drag one or more photos and drop them directly onto `P2PDF.exe` (or a desktop shortcut to it).

### 3. Command Line Interface (CLI)
P2PDF can be fully automated or scripted via the command line:

```bash
# Convert multiple images into Photos.pdf in the first image's folder
P2PDF.exe image1.jpg image2.png image3.webp

# Specify custom output path (collision-safe: will not overwrite existing files)
P2PDF.exe -o "D:\Documents\Album.pdf" pic1.jpg pic2.jpg

# Target page size: A4, A3, A5, Letter, Legal
P2PDF.exe --page-size Letter photo1.jpg photo2.jpg

# Page orientation: auto, portrait, landscape
P2PDF.exe --orientation landscape photo1.jpg photo2.jpg

# Margins: 0, 5mm, 10mm, 0.5in, 10pt
P2PDF.exe --margin 5mm photo1.jpg photo2.jpg

# Sort order: natural (IMG_1, IMG_2, IMG_10), name, date, none
P2PDF.exe --sort natural pic10.jpg pic1.jpg pic2.jpg

# Silent / Script mode (suppresses GUI popups, exits with 0 on success, 1 on error)
P2PDF.exe --quiet *.jpg

# Display application version
P2PDF.exe --version
```

---

## Configuration (`p2pdf.ini`)

P2PDF functions out of the box with zero setup. You can customize default behaviors by editing `p2pdf.ini`.

### Discovery Order:
1. Alongside `P2PDF.exe` (portable mode).
2. `%LOCALAPPDATA%\Programs\P2PDF\p2pdf.ini` (installed mode).
3. Current working directory.
4. Built-in defaults.

### Default Configuration Template:
```ini
; P2PDF Configuration File
[General]
; Default target page size: A4, A3, A5, Letter, Legal
page_size = A4

; Default output PDF filename (never overwrites existing files)
output_filename = Photos.pdf

; Page orientation: auto (matches image aspect ratio), portrait, landscape
orientation = auto

; Image fit mode: into (fit within page preserving aspect ratio), fill, exact, shrink, enlarge
fit_mode = into

; Page margins: 0 (edge-to-edge), 5mm, 10mm, 0.5in, 10pt
margin = 0

; Image ordering for multi-selection in File Explorer:
; natural (IMG_1, IMG_2, IMG_10), name (alphabetical), date (file modification), none (as received)
sort_order = natural

; Lossless structural PDF stream optimization via pikepdf: true or false
optimize = true

; Quiet mode: suppress success popups: true or false
quiet = false
```

---

## Repository Structure

```
p2pdf/
├── aggregator.py             # Single-instance Windows Named Mutex aggregator
├── build.bat                 # Automated compilation script (PyInstaller + metadata)
├── config.py                 # Configuration loader, discovery order, default settings
├── converter.py              # Image validation, lossless stream conversion, pikepdf optimizer
├── generate_version_info.py  # Synchronizes Windows PE resource metadata from config.py
├── install_context_menu.bat  # 1-click batch installer for portable release
├── main.py                   # Application entry point, CLI parser, Windows message dialogs
├── p2pdf.ini                 # Default configuration file template
├── requirements.txt          # Core runtime dependencies (Pillow, img2pdf, pikepdf)
├── requirements-dev.txt      # Development, test, and build dependencies
├── uninstall_context_menu.bat# 1-click batch uninstaller for portable release
├── installer/
│   └── P2PDF.iss             # Inno Setup 6 compilation script for setup wizard
└── tests/
    ├── test_converter.py     # 50 automated tests (formats, EXIF, alpha, collision, sizing)
    └── test_integration.py   # 15 integration tests (registry, CLI, aggregation, idempotency)
```

---

## Testing

The project has comprehensive automated test coverage with **65 tests** passing across unit, engine, and integration layers:

```bash
python -m pytest -v
```

Verified test coverage includes:
- Single and mixed-format conversions (`.jpg`, `.jpeg`, `.png`, `.webp`).
- All 8 standard EXIF orientation tags (rotations and mirroring).
- Transparency, soft masks (`/SMask`), and color spaces (RGB, Grayscale, 1-bit, CMYK).
- Collision avoidance and input image preservation (byte-for-byte SHA-256 checks).
- Corrupted headers, truncated files, and zero-byte file diagnostics.
- Windows Named Mutex multi-instance aggregation and debounce recovery.
- Registry verb installation, uninstallation, and idempotency.

---

## Contributing & Future Roadmap

Contributions and feature suggestions are very welcome! Here are potential areas for further enhancements:

- [ ] **Windows 11 Modern Top-Level Context Menu**: Implement a packaged sparse package / MSIX with `IExplorerCommand` COM registration to elevate P2PDF to the first tier of the Windows 11 context menu.
- [ ] **Extended Format Support**: Add support for multi-frame `.tiff` / `.tif`, modern `.heic` / `.heif` (via `pillow-heif`), and `.avif`.
- [ ] **PDF Security**: Support password protection and encryption (AES-256) via `pikepdf`.
- [ ] **Windows Toast Notifications**: Provide an optional modern Windows Action Center notification instead of modal `MessageBoxW` dialogs.
- [ ] **Context Menu Submenu Presets**: Right-click submenu options for quick presets (e.g., "Create A4 PDF", "Create Letter PDF", "Create Compressed PDF").

### How to Contribute:
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/amazing-feature`).
3. Commit your changes (`git commit -m "Add amazing feature"`).
4. Run the test suite (`python -m pytest -v`) to ensure no regressions.
5. Push to your branch (`git push origin feature/amazing-feature`).
6. Open a Pull Request.

---

## Author & Acknowledgments

* **Author**: Rudraksh Deshmukh ([@RDESHMUKHgit](https://github.com/RDESHMUKHgit))
* **Libraries**: Built upon open-source giants including [Pillow](https://python-pillow.org/), [img2pdf](https://gitlab.mister-muffin.de/josch/img2pdf), [pikepdf](https://github.com/pikepdf/pikepdf), [PyInstaller](https://pyinstaller.org/), and [Inno Setup](https://jrsoftware.org/isinfo.php).

---

<div align="center">
<sub>© 2026 Rudraksh Deshmukh. All rights reserved.</sub>
</div>
