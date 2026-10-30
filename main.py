"""P2PDF - Application Entry Point and CLI Handler.

Parses command-line arguments, invokes conversion, and displays
native Windows notifications and error dialogs.
"""

from __future__ import annotations

import argparse
import ctypes
import glob
import os
import sys
from pathlib import Path
from typing import List, Sequence

from config import (
    APP_DESCRIPTION,
    APP_NAME,
    APP_VERSION,
    DEFAULT_FIT_MODE,
    DEFAULT_MARGIN,
    DEFAULT_ORIENTATION,
    DEFAULT_OUTPUT_FILENAME,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT_ORDER,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_PAGE_SIZES,
    AppConfig,
    load_config,
)
from aggregator import aggregate_context_menu_files
from converter import (
    ConversionError,
    ConversionResult,
    ValidationError,
    convert_images_to_pdf,
)


def format_file_size(size_bytes: int) -> str:
    """Formats bytes into human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def show_notification(
    title: str,
    message: str,
    is_error: bool = False,
    quiet: bool = False
) -> None:
    """Prints message to stdout/stderr and displays a native Windows MessageBox."""
    stream = sys.stderr if is_error else sys.stdout
    try:
        print(f"[{title}] {message}", file=stream)
    except Exception:
        pass

    if quiet or os.environ.get("P2PDF_NO_GUI") == "1":
        return

    # Windows MessageBox flags
    # 0x00000010 = MB_ICONERROR
    # 0x00000040 = MB_ICONINFORMATION
    # 0x00010000 = MB_SETFOREGROUND (ensures dialog appears in foreground)
    # 0x00040000 = MB_TOPMOST (stays on top of other windows)
    icon_type = 0x00000010 if is_error else 0x00000040
    flags = icon_type | 0x00010000 | 0x00040000

    try:
        ctypes.windll.user32.MessageBoxW(0, message, title, flags)
    except Exception:
        pass


def expand_input_paths(raw_args: Sequence[str]) -> List[Path]:
    """Expands wildcards (e.g. *.jpg) and resolves absolute paths."""
    resolved_paths: List[Path] = []
    for arg in raw_args:
        # Expand wildcards if present (e.g. CMD arguments)
        if any(char in arg for char in ("*", "?")):
            matches = glob.glob(arg)
            if matches:
                for match in matches:
                    resolved_paths.append(Path(match).resolve())
            else:
                # If wildcard matched nothing, preserve original for validator error
                resolved_paths.append(Path(arg).resolve())
        else:
            resolved_paths.append(Path(arg).resolve())
    return resolved_paths


def build_parser(config: AppConfig | None = None) -> argparse.ArgumentParser:
    """Constructs the command-line argument parser."""
    cfg = config or AppConfig()
    supported_sizes = ", ".join(sorted(SUPPORTED_PAGE_SIZES.keys()))
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description=f"{APP_NAME} v{APP_VERSION} - {APP_DESCRIPTION}",
        add_help=True,
    )
    parser.add_argument(
        "images",
        nargs="*",
        metavar="IMAGE",
        help="One or more image files (.jpg, .jpeg, .png, .webp) to convert.",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="OUTPUT_PDF",
        help="Destination path for the output PDF. Never silently overwrites existing files.",
    )
    parser.add_argument(
        "--page-size",
        metavar="SIZE",
        default=cfg.page_size,
        help=f"Target page size (default: {cfg.page_size}). Supported: {supported_sizes}",
    )
    parser.add_argument(
        "--orientation",
        choices=["auto", "portrait", "landscape"],
        default=cfg.orientation,
        help=f"Page orientation (default: {cfg.orientation}). Choices: auto, portrait, landscape.",
    )
    parser.add_argument(
        "--fit-mode",
        choices=["into", "fill", "exact", "shrink", "enlarge"],
        default=cfg.fit_mode,
        help=f"Image fit mode within page (default: {cfg.fit_mode}).",
    )
    parser.add_argument(
        "--margin",
        metavar="MARGIN",
        default=cfg.margin,
        help=f"Page margins (default: {cfg.margin}). Examples: 0, 5mm, 10mm, 0.5in, 10pt.",
    )
    parser.add_argument(
        "--sort",
        choices=["natural", "name", "date", "none"],
        default=None,
        help="Sort order for input images. If omitted for CLI, order is preserved; for Explorer multi-selection, defaults to config setting.",
    )
    parser.add_argument(
        "--no-optimize",
        action="store_true",
        default=not cfg.optimize,
        help="Disable lossless structural PDF stream optimization.",
    )
    parser.add_argument(
        "--no-aggregate",
        action="store_true",
        help="Disable multi-instance argument aggregation for Windows context menu.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=cfg.quiet,
        help="Run silently without showing Windows popup dialogs (ideal for scripts and tests).",
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="INI_FILE",
        help="Path to an alternative p2pdf.ini configuration file.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"{APP_NAME} {APP_VERSION}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Main application routine."""
    if argv is None:
        argv = sys.argv[1:]

    # Early check for custom --config argument before building full parser
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("-c", "--config", dest="config_file")
    pre_args, _ = pre_parser.parse_known_args(argv)

    cfg = load_config(pre_args.config_file if pre_args.config_file else None)
    parser = build_parser(cfg)

    # If no arguments were supplied, display instructions dialog
    if not argv:
        supported_list = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        supported_sizes = ", ".join(sorted(SUPPORTED_PAGE_SIZES.keys()))
        usage_msg = (
            f"{APP_NAME} — {APP_DESCRIPTION} (v{APP_VERSION})\n\n"
            f"No photos were selected.\n\n"
            f"How to use:\n"
            f"1. Select one or more photos in Windows File Explorer.\n"
            f"2. Right-click or drag and drop onto {APP_NAME}.exe.\n\n"
            f"Supported formats: {supported_list}\n"
            f"Supported page sizes: {supported_sizes}\n\n"
            f"Configuration: Settings can be customized in p2pdf.ini"
        )
        show_notification(f"{APP_NAME}", usage_msg, is_error=False, quiet=False)
        return 0

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2

    # Check for empty images list (e.g. user only passed options like -q)
    if not args.images:
        show_notification(
            f"{APP_NAME} - Error",
            "No image paths were provided for conversion.",
            is_error=True,
            quiet=args.quiet,
        )
        return 1

    input_paths = expand_input_paths(args.images)

    # When launched from Windows Explorer context menu, Windows launches one process per file.
    # If a single file was passed in interactive mode, aggregate any concurrently launched files
    # into a single primary conversion batch so all photos become one PDF with one dialog.
    is_aggregated = False
    if len(input_paths) == 1 and not args.no_aggregate and (not args.quiet or os.environ.get("P2PDF_TEST_AGGREGATE") == "1"):
        sort_for_agg = args.sort or cfg.sort_order
        is_primary, collected = aggregate_context_menu_files(input_paths[0], sort_order=sort_for_agg)
        if not is_primary:
            # Secondary instance: file was handed off to primary instance. Exit quietly.
            return 0
        input_paths = collected
        is_aggregated = True

    try:
        # Determine sorting rule:
        # If user explicitly passed --sort, apply it.
        # If files were gathered via Explorer aggregation, they were already sorted with sort_for_agg.
        # If passed directly on CLI without --sort, preserve exact argument order ("none").
        sort_to_apply = args.sort if args.sort else ("none" if not is_aggregated else "none")

        result: ConversionResult = convert_images_to_pdf(
            image_paths=input_paths,
            output_path=args.output,
            page_size=args.page_size,
            fit_mode=args.fit_mode,
            orientation=args.orientation,
            margin=args.margin,
            sort_order=sort_to_apply,
            lossless_optimize=not args.no_optimize,
            default_output_filename=cfg.output_filename,
        )

        opt_info = ""
        if result.optimized and result.original_size_bytes > result.file_size_bytes:
            saved_bytes = result.original_size_bytes - result.file_size_bytes
            saved_pct = (saved_bytes / result.original_size_bytes) * 100
            opt_info = f"\nOptimization: Losslessly saved {format_file_size(saved_bytes)} ({saved_pct:.1f}%)"

        success_msg = (
            f"PDF generated successfully!\n\n"
            f"File: {result.output_path.name}\n"
            f"Folder: {result.output_path.parent}\n\n"
            f"Total Photos: {result.page_count}\n"
            f"File Size: {format_file_size(result.file_size_bytes)}{opt_info}\n"
            f"Time Elapsed: {result.duration_seconds:.2f} seconds"
        )
        show_notification(
            f"{APP_NAME}",
            success_msg,
            is_error=False,
            quiet=args.quiet,
        )
        return 0

    except (ValidationError, ConversionError) as e:
        show_notification(
            f"{APP_NAME} - Error",
            str(e),
            is_error=True,
            quiet=args.quiet,
        )
        return 1
    except Exception as e:
        unexpected_msg = f"An unexpected error occurred during conversion:\n\n{type(e).__name__}: {e}"
        show_notification(
            f"{APP_NAME} - Error",
            unexpected_msg,
            is_error=True,
            quiet=args.quiet,
        )
        return 1



if __name__ == "__main__":
    sys.exit(main())
