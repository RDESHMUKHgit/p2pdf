"""P2PDF - Core Conversion Engine.

Handles image validation, color mode/orientation normalization,
lossless PDF generation via img2pdf, and lossless structural PDF optimization.
"""

from __future__ import annotations

import os
import re
import time
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from PIL import Image, ImageOps, UnidentifiedImageError
import img2pdf
import pikepdf

from config import (
    A4_SIZE_PT,
    AUTO_ORIENT,
    DEFAULT_FIT_MODE,
    DEFAULT_LOSSLESS_OPTIMIZE,
    DEFAULT_MARGIN,
    DEFAULT_ORIENTATION,
    DEFAULT_OUTPUT_FILENAME,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT_ORDER,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_PAGE_SIZES,
)


class P2PDFError(Exception):
    """Base exception class for P2PDF."""


class ValidationError(P2PDFError):
    """Raised when an input file is invalid, missing, or unsupported."""


class ConversionError(P2PDFError):
    """Raised when PDF conversion fails."""


@dataclass
class ConversionResult:
    """Contains information about a successful conversion."""
    output_path: Path
    page_count: int
    duration_seconds: float
    file_size_bytes: int
    optimized: bool = False
    original_size_bytes: int = 0


def resolve_page_size(page_size: str | Tuple[float, float] | None = None) -> Tuple[float, float]:
    """Resolves page size specification into dimensions in points (width_pt, height_pt).

    Supports: 'A4', 'A3', 'A5', 'Letter', 'Legal', or custom (width, height) tuples.
    """
    if page_size is None:
        return SUPPORTED_PAGE_SIZES[DEFAULT_PAGE_SIZE]

    if isinstance(page_size, (tuple, list)) and len(page_size) == 2:
        return (float(page_size[0]), float(page_size[1]))

    if isinstance(page_size, str):
        key = page_size.strip().upper()
        if key in SUPPORTED_PAGE_SIZES:
            return SUPPORTED_PAGE_SIZES[key]
        try:
            parsed = img2pdf.parse_pagesize_rectarg(page_size)
            if parsed and len(parsed) == 2:
                return (float(parsed[0]), float(parsed[1]))
        except Exception:
            pass

    supported = ", ".join(sorted(SUPPORTED_PAGE_SIZES.keys()))
    raise ValidationError(
        f"Unsupported page size '{page_size}'. Supported sizes: {supported}"
    )


def resolve_fit_mode(fit_mode_str: str) -> Any:
    """Maps fit mode string to img2pdf.FitMode enum."""
    mode_str = (fit_mode_str or DEFAULT_FIT_MODE).lower()
    fit_map = {
        "into": img2pdf.FitMode.into,
        "fill": img2pdf.FitMode.fill,
        "exact": img2pdf.FitMode.exact,
        "shrink": img2pdf.FitMode.shrink,
        "enlarge": img2pdf.FitMode.enlarge,
    }
    if mode_str in fit_map:
        return fit_map[mode_str]
    raise ValidationError(
        f"Unsupported fit mode '{fit_mode_str}'. Supported modes: {', '.join(fit_map.keys())}"
    )


def natural_sort_key(path: Path | str) -> list:
    """Key for natural alphanumeric sorting (e.g. photo1, photo2, photo10)."""
    name = Path(path).name
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', name)]


def sort_image_paths(paths: Sequence[Path | str], sort_order: str = "none") -> List[Path]:
    """Sorts image paths according to the requested order.
    
    Supported sort orders:
    - 'natural': Human-intuitive alphanumeric sort (photo1, photo2, photo10).
    - 'name': Standard alphabetical sort.
    - 'date': File modification timestamp sort (oldest to newest).
    - 'none': Preserves original sequence without sorting.
    """
    resolved = [Path(p).resolve() for p in paths]
    mode = (sort_order or "none").strip().lower()
    if mode == "natural":
        return sorted(resolved, key=natural_sort_key)
    elif mode == "name":
        return sorted(resolved, key=lambda p: p.name.lower())
    elif mode == "date":
        return sorted(resolved, key=lambda p: (p.stat().st_mtime if p.exists() else 0, p.name.lower()))
    elif mode in ("none", ""):
        return list(resolved)
    else:
        raise ValidationError(
            f"Unsupported sort order '{sort_order}'. Supported: natural, name, date, none."
        )


def resolve_orientation(orientation_str: str) -> str:
    """Validates and normalizes page orientation ('auto', 'portrait', 'landscape')."""
    val = (orientation_str or DEFAULT_ORIENTATION).strip().lower()
    if val in ("auto", "portrait", "landscape"):
        return val
    raise ValidationError(
        f"Unsupported orientation '{orientation_str}'. Supported: auto, portrait, landscape."
    )


def resolve_border(border_spec: str | float | int | Tuple[float, float] | None) -> Tuple[float, float] | None:
    """Parses margin specification into a (horizontal_pt, vertical_pt) tuple in points or None."""
    if border_spec is None:
        return None

    if isinstance(border_spec, (tuple, list)) and len(border_spec) == 2:
        return (float(border_spec[0]), float(border_spec[1]))

    if isinstance(border_spec, (int, float)):
        val = float(border_spec)
        return None if val == 0 else (val, val)

    if isinstance(border_spec, str):
        cleaned = border_spec.strip()
        if not cleaned or cleaned in ("0", "0pt", "0mm", "0in"):
            return None
        try:
            parsed = img2pdf.parse_borderarg(cleaned)
            if parsed and len(parsed) == 2:
                if parsed[0] == 0.0 and parsed[1] == 0.0:
                    return None
                return (float(parsed[0]), float(parsed[1]))
        except Exception as e:
            raise ValidationError(f"Invalid margin format '{border_spec}': {e}") from e

    raise ValidationError(f"Invalid margin specification '{border_spec}'.")



def get_unique_output_path(
    target_path_or_dir: Path | str,
    default_filename: str = DEFAULT_OUTPUT_FILENAME,
    forbidden_paths: Optional[Sequence[Path | str]] = None,
) -> Path:
    """Returns a unique output file path that does not exist and does not collide with forbidden paths.

    Never overwrites an existing file or any input image in forbidden_paths.

    Progression:
    - Target.pdf (if it does not exist and is not forbidden)
    - Target (1).pdf (if Target.pdf exists or is forbidden)
    - Target (2).pdf ...
    """
    target = Path(target_path_or_dir).resolve()
    forbidden_set: Set[Path] = {Path(p).resolve() for p in (forbidden_paths or [])}

    if target.is_dir() or str(target_path_or_dir).strip() in ("", "."):
        directory = target if target.is_dir() else Path.cwd()
        base_path = Path(default_filename)
        stem = base_path.stem
        suffix = base_path.suffix if base_path.suffix.lower() == ".pdf" else ".pdf"
    else:
        directory = target.parent
        stem = target.stem
        suffix = target.suffix if target.suffix.lower() == ".pdf" else ".pdf"

    candidate = directory / f"{stem}{suffix}"
    if not candidate.exists() and candidate not in forbidden_set:
        return candidate

    counter = 1
    while True:
        candidate = directory / f"{stem} ({counter}){suffix}"
        if not candidate.exists() and candidate not in forbidden_set:
            return candidate
        counter += 1


def validate_image_file(image_path: Path | str) -> Dict[str, Any]:
    """Validates that a file exists, is supported, and is not corrupted.

    Returns a dictionary of image metadata.
    Raises ValidationError if validation fails.
    """
    path = Path(image_path).resolve()

    if not path.exists():
        raise ValidationError(f"File not found: '{image_path}'")

    if not path.is_file():
        raise ValidationError(f"Path is not a regular file: '{image_path}'")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported_str = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValidationError(
            f"Unsupported file extension '{suffix}' for '{path.name}'. "
            f"Supported formats: {supported_str}"
        )

    # Validate container header structure using Pillow
    try:
        with Image.open(path) as img:
            img_format = (img.format or "").upper()
            if img_format not in ("JPEG", "PNG", "WEBP"):
                raise ValidationError(
                    f"File '{path.name}' is recognized as format '{img_format}', "
                    f"which is not supported. Supported: JPEG, PNG, WEBP."
                )
            img.verify()

    except ValidationError:
        raise
    except UnidentifiedImageError as e:
        raise ValidationError(
            f"Cannot identify image file '{path.name}'. File may be corrupted or not an image."
        ) from e
    except Exception as e:
        raise ValidationError(f"Invalid or corrupted image '{path.name}': {e}") from e

    # Re-open after verify() to inspect metadata, handle multi-frame/animated, and decode scanlines
    try:
        with Image.open(path) as img:
            is_animated = getattr(img, "is_animated", False)
            n_frames = getattr(img, "n_frames", 1)

            # For animated images (e.g. animated WebP), seek to frame 0 deterministically
            if is_animated or n_frames > 1:
                img.seek(0)

            # Verify integrity of pixel scanlines (detects truncated file data)
            img.load()

            width, height = img.size
            mode = img.mode

            # Extract EXIF orientation if present
            exif = img.getexif()
            orientation = exif.get(0x0112) if exif else None

            # Determine whether preprocessing with Pillow is necessary:
            # 1. Mirrored EXIF orientations (2, 4, 5, 7) must be transposed.
            # 2. Animated WebP images must have frame 0 extracted.
            # 3. WEBP images with alpha (RGBA, LA) must be converted to PNG for img2pdf.
            # 4. Non-JPEG CMYK or non-standard palette modes need normalization.
            needs_prep = False
            if orientation in (2, 4, 5, 7):
                needs_prep = True
            elif is_animated and img_format == "WEBP":
                needs_prep = True
            elif img_format == "WEBP" and (mode in ("RGBA", "LA") or "transparency" in img.info):
                needs_prep = True
            elif mode == "CMYK" and img_format != "JPEG":
                needs_prep = True
            elif mode == "P" and img_format != "PNG":
                needs_prep = True
            elif mode not in ("RGB", "L", "RGBA", "1", "P", "CMYK"):
                needs_prep = True

            return {
                "path": path,
                "format": img_format,
                "mode": mode,
                "width": width,
                "height": height,
                "orientation": orientation,
                "is_animated": is_animated,
                "needs_preprocessing": needs_prep,
            }

    except Exception as e:
        raise ValidationError(
            f"Corrupted or unreadable image data in '{path.name}': {e}"
        ) from e


def prepare_image_for_pdf(
    meta: Dict[str, Any],
    temp_dir: Path,
    index: int
) -> str:
    """Prepares an image for img2pdf.

    If the image is already compatible with direct embedding, returns the original path.
    Otherwise, normalizes the image via Pillow and writes a temporary file.
    """
    if not meta["needs_preprocessing"]:
        return str(meta["path"])

    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"prep_{index}_{meta['path'].stem}.png"

    with Image.open(meta["path"]) as img:
        # For animated WebP or multi-frame files, deterministically take first frame
        if getattr(img, "is_animated", False):
            img.seek(0)
            img = img.copy()

        # Handle EXIF orientation transposition
        img = ImageOps.exif_transpose(img)

        # Ensure mode is standard RGB, RGBA, or L
        if img.mode not in ("RGB", "RGBA", "L"):
            if "transparency" in img.info or img.mode in ("P", "PA", "LA"):
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")

        # Save with maximum lossless zlib compression (level 9)
        img.save(temp_path, format="PNG", compress_level=9)

    return str(temp_path)


def optimize_pdf_lossless(input_pdf_path: Path, output_pdf_path: Path) -> bool:
    """Optimizes a PDF file losslessly using pikepdf.

    Packs PDF objects into compressed Object Streams and compresses eligible streams
    without re-encoding image pixel data.

    Returns True if the optimized file is smaller and was written to output_pdf_path;
    returns False if optimization provided no reduction or failed.
    """
    input_size = input_pdf_path.stat().st_size
    temp_opt = output_pdf_path.parent / f".p2pdf_opt_{uuid.uuid4().hex}.tmp"

    try:
        with pikepdf.open(input_pdf_path) as pdf:
            pdf.save(
                temp_opt,
                compress_streams=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
                linearize=False,
            )

        opt_size = temp_opt.stat().st_size
        if opt_size < input_size:
            temp_opt.replace(output_pdf_path)
            return True
        else:
            temp_opt.unlink(missing_ok=True)
            return False
    except Exception:
        if temp_opt.exists():
            temp_opt.unlink(missing_ok=True)
        return False


def convert_images_to_pdf(
    image_paths: Sequence[Path | str],
    output_path: Optional[Path | str] = None,
    page_size: str | Tuple[float, float] = DEFAULT_PAGE_SIZE,
    fit_mode: str = DEFAULT_FIT_MODE,
    orientation: str = DEFAULT_ORIENTATION,
    margin: str | float | Tuple[float, float] | None = DEFAULT_MARGIN,
    auto_orient: Optional[bool] = None,
    sort_order: str = "none",
    lossless_optimize: bool = DEFAULT_LOSSLESS_OPTIMIZE,
    default_output_filename: str = DEFAULT_OUTPUT_FILENAME,
) -> ConversionResult:
    """Converts a sequence of images into a single PDF file with safe staging and optional lossless optimization.

    Parameters:
    - image_paths: Sequence of image file paths (JPG, JPEG, PNG, WebP).
    - output_path: Destination path or directory. Never silently overwrites existing files.
    - page_size: Target page format name ('A4', 'Letter', etc.) or (width_pt, height_pt) tuple.
    - fit_mode: Fitting rule ('into', 'fill', 'exact', 'shrink', 'enlarge').
    - orientation: Page orientation ('auto', 'portrait', 'landscape').
    - margin: Outer margins around image (e.g. '0', '5mm', '10pt', or (h_pt, v_pt)).
    - auto_orient: Whether to automatically match page orientation to image aspect ratio.
      If None, defaults to True when orientation is 'auto', False otherwise.
    - sort_order: Ordering rule ('none', 'natural', 'name', 'date').
    - lossless_optimize: Whether to losslessly optimize PDF structure via pikepdf.
    - default_output_filename: Default filename to use when output_path is a directory or None.

    Returns:
    - ConversionResult with destination path, page count, duration, file size, and optimization stats.

    Raises:
    - ValidationError on invalid arguments or unreadable images.
    - ConversionError on conversion or write failures.
    """
    if not image_paths:
        raise ValidationError("No image files provided for conversion.")

    start_time = time.perf_counter()

    # Step 1: Resolve and validate page configuration, orientation, and margins
    pagesize_pt = resolve_page_size(page_size)
    fit_enum = resolve_fit_mode(fit_mode)
    resolved_orient = resolve_orientation(orientation)
    border_pt = resolve_border(margin)

    if auto_orient is not None:
        effective_auto_orient = bool(auto_orient)
    else:
        effective_auto_orient = (resolved_orient == "auto")

    if resolved_orient == "portrait":
        pagesize_pt = (min(pagesize_pt[0], pagesize_pt[1]), max(pagesize_pt[0], pagesize_pt[1]))
    elif resolved_orient == "landscape":
        pagesize_pt = (max(pagesize_pt[0], pagesize_pt[1]), min(pagesize_pt[0], pagesize_pt[1]))

    # Step 2: Sort and validate all input images
    ordered_paths = sort_image_paths(image_paths, sort_order)
    meta_list: List[Dict[str, Any]] = []
    for img_path in ordered_paths:
        meta = validate_image_file(img_path)
        meta_list.append(meta)

    input_resolved_paths = [m["path"] for m in meta_list]

    # Step 3: Determine target output specification and ensure parent directory is writable
    if output_path is None:
        target_dir = meta_list[0]["path"].parent
        target_spec = target_dir / default_output_filename
    else:
        target_spec = Path(output_path).resolve()

    dest_dir = target_spec if target_spec.is_dir() else target_spec.parent
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        # Test directory write permission
        test_file = dest_dir / f".p2pdf_perm_test_{uuid.uuid4().hex}"
        test_file.touch()
        test_file.unlink()
    except PermissionError as e:
        raise ConversionError(
            f"Permission denied: Cannot write to directory '{dest_dir}': {e}"
        ) from e
    except OSError as e:
        if getattr(e, "errno", None) == 28:
            raise ConversionError(
                f"Disk is full: Unable to write to '{dest_dir}'."
            ) from e
        raise ConversionError(
            f"Cannot access output directory '{dest_dir}': {e}"
        ) from e

    # Step 4: Staged conversion — write to temporary file first to guarantee atomic delivery
    stage_id = uuid.uuid4().hex
    staged_path = dest_dir / f".p2pdf_stage_{stage_id}.tmp"

    try:
        with tempfile.TemporaryDirectory(prefix="p2pdf_") as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            prepared_inputs: List[str] = [
                prepare_image_for_pdf(meta, temp_dir, i)
                for i, meta in enumerate(meta_list)
            ]

            layout = img2pdf.get_layout_fun(
                pagesize=pagesize_pt,
                fit=fit_enum,
                auto_orient=effective_auto_orient,
                border=border_pt,
            )

            try:
                with open(staged_path, "wb") as out_f:
                    img2pdf.convert(
                        prepared_inputs,
                        layout_fun=layout,
                        outputstream=out_f,
                    )
            except Exception as primary_err:
                # Fallback path: Normalize ALL images via Pillow if direct embedding encounters issues
                try:
                    fallback_inputs: List[str] = []
                    for i, meta in enumerate(meta_list):
                        fallback_file = temp_dir / f"fallback_{i}.png"
                        with Image.open(meta["path"]) as im:
                            if getattr(im, "is_animated", False):
                                im.seek(0)
                                im = im.copy()
                            im = ImageOps.exif_transpose(im)
                            if im.mode not in ("RGB", "L", "RGBA"):
                                im = im.convert("RGBA" if "transparency" in im.info or im.mode in ("P", "PA", "LA") else "RGB")
                            im.save(fallback_file, format="PNG", compress_level=9)
                        fallback_inputs.append(str(fallback_file))

                    with open(staged_path, "wb") as out_f:
                        img2pdf.convert(
                            fallback_inputs,
                            layout_fun=layout,
                            outputstream=out_f,
                        )
                except Exception as fallback_err:
                    raise ConversionError(
                        f"Failed to generate PDF. "
                        f"Primary conversion failed: {primary_err}. "
                        f"Fallback conversion also failed: {fallback_err}."
                    ) from fallback_err

        # Verify staged PDF exists, is non-empty, and can be parsed
        if not staged_path.exists() or staged_path.stat().st_size == 0:
            raise ConversionError("PDF creation failed: Output stream generated an empty file.")

        try:
            with pikepdf.open(staged_path) as verify_pdf:
                if len(verify_pdf.pages) != len(meta_list):
                    raise ConversionError(
                        f"PDF page count mismatch: expected {len(meta_list)}, got {len(verify_pdf.pages)}."
                    )
        except Exception as verify_err:
            if isinstance(verify_err, ConversionError):
                raise
            raise ConversionError(f"Generated PDF verification failed: {verify_err}") from verify_err

        # Step 5: Lossless structural optimization (if enabled)
        raw_size = staged_path.stat().st_size
        optimized_applied = False
        if lossless_optimize:
            optimized_applied = optimize_pdf_lossless(staged_path, staged_path)

        # Step 6: Atomic, collision-safe move into final destination
        final_dest: Optional[Path] = None
        while True:
            candidate = get_unique_output_path(
                target_path_or_dir=target_spec,
                default_filename=default_output_filename,
                forbidden_paths=input_resolved_paths,
            )
            try:
                # os.rename on Windows atomically moves file and fails if destination exists
                os.rename(staged_path, candidate)
                final_dest = candidate
                break
            except FileExistsError:
                # Race condition handling: another process created candidate in the interim
                continue
            except PermissionError as e:
                raise ConversionError(
                    f"Permission denied while delivering final PDF to '{candidate}': {e}"
                ) from e
            except OSError as e:
                raise ConversionError(
                    f"Failed to save final PDF to '{candidate}': {e}"
                ) from e

        duration = time.perf_counter() - start_time
        final_size = final_dest.stat().st_size

        return ConversionResult(
            output_path=final_dest,
            page_count=len(meta_list),
            duration_seconds=duration,
            file_size_bytes=final_size,
            optimized=optimized_applied,
            original_size_bytes=raw_size,
        )

    finally:
        # Guarantee that any staged temporary file is cleaned up on error
        if staged_path.exists():
            try:
                staged_path.unlink()
            except OSError:
                pass
