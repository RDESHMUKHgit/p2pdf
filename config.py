"""P2PDF - Configuration Module.

Defines default settings, supported formats, and page dimensions.
"""

from typing import Dict, Set, Tuple

APP_NAME = "P2PDF"
APP_VERSION = "1.5.0"
APP_DESCRIPTION = "Photo to PDF Converter for Windows"

# Supported image file extensions (lowercase)
SUPPORTED_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".webp"}

# Default output filename
DEFAULT_OUTPUT_FILENAME: str = "Photos.pdf"

# Standard supported page sizes in points (72 points per inch)
# 1 pt = 1/72 inch; 1 mm = 72 / 25.4 pt ≈ 2.83464567 pt
SUPPORTED_PAGE_SIZES: Dict[str, Tuple[float, float]] = {
    "A4": (595.2755905511812, 841.8897637795276),      # 210mm x 297mm
    "A3": (841.8897637795276, 1190.551181102362),     # 297mm x 420mm
    "A5": (419.5275590551181, 595.2755905511812),      # 148mm x 210mm
    "LETTER": (612.0, 792.0),                          # 8.5in x 11in
    "LEGAL": (612.0, 1008.0),                          # 8.5in x 14in
}

# Standard A4 dimensions in points
A4_WIDTH_PT: float = SUPPORTED_PAGE_SIZES["A4"][0]
A4_HEIGHT_PT: float = SUPPORTED_PAGE_SIZES["A4"][1]
A4_SIZE_PT: Tuple[float, float] = (A4_WIDTH_PT, A4_HEIGHT_PT)

# Page configuration defaults
DEFAULT_PAGE_SIZE: str = "A4"
DEFAULT_FIT_MODE: str = "into"
AUTO_ORIENT: bool = True
DEFAULT_ORIENTATION: str = "auto"
DEFAULT_MARGIN: str = "0"
DEFAULT_SORT_ORDER: str = "natural"
DEFAULT_QUIET: bool = False

# Lossless PDF structural optimization default
DEFAULT_LOSSLESS_OPTIMIZE: bool = True


import configparser
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class AppConfig:
    """Holds runtime configuration for P2PDF."""
    page_size: str = DEFAULT_PAGE_SIZE
    output_filename: str = DEFAULT_OUTPUT_FILENAME
    orientation: str = DEFAULT_ORIENTATION
    fit_mode: str = DEFAULT_FIT_MODE
    margin: str = DEFAULT_MARGIN
    sort_order: str = DEFAULT_SORT_ORDER
    optimize: bool = DEFAULT_LOSSLESS_OPTIMIZE
    quiet: bool = DEFAULT_QUIET


def get_default_config_file() -> Path:
    """Returns the default expected location of p2pdf.ini."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "Programs" / "P2PDF" / "p2pdf.ini"
    return Path.home() / ".p2pdf.ini"


def find_config_file() -> Optional[Path]:
    """Finds existing p2pdf.ini in standard search locations.
    
    Order of preference:
    1. Directory containing the running executable or script.
    2. %LOCALAPPDATA%\\Programs\\P2PDF\\p2pdf.ini
    3. Current working directory.
    """
    # 1. Next to executable / main script
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
    else:
        exe_dir = Path(__file__).resolve().parent
    local_ini = exe_dir / "p2pdf.ini"
    if local_ini.is_file():
        return local_ini

    # 2. Installed user directory
    installed_ini = get_default_config_file()
    if installed_ini.is_file():
        return installed_ini

    # 3. Current working directory
    cwd_ini = Path.cwd() / "p2pdf.ini"
    if cwd_ini.is_file():
        return cwd_ini

    return None


def generate_default_ini() -> str:
    """Generates the contents of a documented default p2pdf.ini file."""
    return f"""; P2PDF Configuration File
; Place this file in %LOCALAPPDATA%\\Programs\\P2PDF\\p2pdf.ini
; or in the same folder as P2PDF.exe

[General]
; Default target page size: A4, A3, A5, Letter, Legal
page_size = {DEFAULT_PAGE_SIZE}

; Default output PDF filename (never overwrites existing files)
output_filename = {DEFAULT_OUTPUT_FILENAME}

; Page orientation: auto (matches image aspect ratio), portrait, landscape
orientation = {DEFAULT_ORIENTATION}

; Image fit mode: into (fit within page preserving aspect ratio), fill, exact, shrink, enlarge
fit_mode = {DEFAULT_FIT_MODE}

; Page margins: 0 (edge-to-edge), 5mm, 10mm, 0.5in, 10pt
margin = {DEFAULT_MARGIN}

; Image ordering for multi-selection in File Explorer:
; natural (IMG_1, IMG_2, IMG_10), name (alphabetical), date (file modification), none (as received)
sort_order = {DEFAULT_SORT_ORDER}

; Lossless structural PDF stream optimization via pikepdf: true or false
optimize = {'true' if DEFAULT_LOSSLESS_OPTIMIZE else 'false'}

; Quiet mode: suppress success popups: true or false
quiet = {'true' if DEFAULT_QUIET else 'false'}
"""


def load_config(config_path: Path | str | None = None) -> AppConfig:
    """Loads configuration from INI file or returns default AppConfig if file is missing."""
    cfg = AppConfig()

    path: Optional[Path] = None
    if config_path is not None:
        p = Path(config_path).resolve()
        if p.is_file():
            path = p
    else:
        path = find_config_file()

    if not path or not path.is_file():
        return cfg

    parser = configparser.ConfigParser()
    try:
        parser.read(str(path), encoding="utf-8")
    except Exception:
        return cfg

    section = "General"
    if not parser.has_section(section):
        return cfg

    if parser.has_option(section, "page_size"):
        val = parser.get(section, "page_size").strip()
        if val.upper() in SUPPORTED_PAGE_SIZES:
            cfg.page_size = val.upper()

    if parser.has_option(section, "output_filename"):
        val = parser.get(section, "output_filename").strip()
        if val:
            cfg.output_filename = val

    if parser.has_option(section, "orientation"):
        val = parser.get(section, "orientation").strip().lower()
        if val in ("auto", "portrait", "landscape"):
            cfg.orientation = val

    if parser.has_option(section, "fit_mode"):
        val = parser.get(section, "fit_mode").strip().lower()
        if val in ("into", "fill", "exact", "shrink", "enlarge"):
            cfg.fit_mode = val

    if parser.has_option(section, "margin"):
        val = parser.get(section, "margin").strip()
        if val:
            cfg.margin = val

    if parser.has_option(section, "sort_order"):
        val = parser.get(section, "sort_order").strip().lower()
        if val in ("natural", "name", "date", "none"):
            cfg.sort_order = val

    if parser.has_option(section, "optimize"):
        try:
            cfg.optimize = parser.getboolean(section, "optimize")
        except ValueError:
            pass

    if parser.has_option(section, "quiet"):
        try:
            cfg.quiet = parser.getboolean(section, "quiet")
        except ValueError:
            pass

    return cfg

