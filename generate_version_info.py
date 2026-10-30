"""P2PDF - Windows Version Info Generator.

Generates version_info.txt for PyInstaller based on config.APP_VERSION and metadata.
"""

from __future__ import annotations

import re
from pathlib import Path

from config import APP_DESCRIPTION, APP_NAME, APP_VERSION


def generate_version_info(output_path: Path | str = "version_info.txt") -> Path:
    """Generates a PyInstaller-compatible Windows version resource file."""
    target = Path(output_path)

    # Extract integer digits from version string (e.g. '1.5.0' -> (1, 5, 0, 0))
    parts = [int(p) for p in re.findall(r"\d+", APP_VERSION)]
    while len(parts) < 4:
        parts.append(0)
    ver_tuple = tuple(parts[:4])
    ver_str = ".".join(str(p) for p in ver_tuple)

    content = f"""# UTF-8
# Windows Version Resource for {APP_NAME}
# Generated automatically from config.py

VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={ver_tuple},
    prodvers={ver_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'Rudraksh Deshmukh'),
          StringStruct('FileDescription', 'Photo to PDF Converter'),
          StringStruct('FileVersion', '{ver_str}'),
          StringStruct('InternalName', '{APP_NAME}'),
          StringStruct('LegalCopyright', '\u00a9 Rudraksh Deshmukh 2026 All rights reserved'),
          StringStruct('OriginalFilename', '{APP_NAME}.exe'),
          StringStruct('ProductName', '{APP_NAME}'),
          StringStruct('ProductVersion', '{ver_str}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    target.write_text(content, encoding="utf-8")
    return target


if __name__ == "__main__":
    out = generate_version_info()
    print(f"Generated {out.resolve()} for {APP_NAME} v{APP_VERSION}")

