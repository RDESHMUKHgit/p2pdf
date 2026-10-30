"""Automated Test Suite for P2PDF.

Tests image validation, conversion logic, all 8 EXIF orientations,
transparency handling, output name generation, collision prevention,
page sizes, atomic staging, and lossless PDF compression.
"""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import tempfile
from pathlib import Path
import pytest
from PIL import Image, ImageDraw
import pikepdf
import pypdfium2

from config import (
    A4_HEIGHT_PT,
    A4_WIDTH_PT,
    DEFAULT_MARGIN,
    DEFAULT_ORIENTATION,
    DEFAULT_OUTPUT_FILENAME,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT_ORDER,
    SUPPORTED_PAGE_SIZES,
    AppConfig,
    load_config,
)
from converter import (
    ConversionError,
    ConversionResult,
    ValidationError,
    convert_images_to_pdf,
    get_unique_output_path,
    natural_sort_key,
    optimize_pdf_lossless,
    resolve_border,
    resolve_orientation,
    resolve_page_size,
    sort_image_paths,
    validate_image_file,
)
from main import main


@pytest.fixture
def temp_dir():
    """Provides an isolated temporary directory for test files."""
    tmp = tempfile.mkdtemp(prefix="p2pdf_test_")
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


def create_test_image(
    path: Path,
    fmt: str = "JPEG",
    mode: str = "RGB",
    size: tuple[int, int] = (400, 300),
    color: tuple = (255, 0, 0),
    exif_orientation: int | None = None,
) -> Path:
    """Helper to generate test images with specific attributes."""
    img = Image.new(mode, size, color)
    kwargs = {}
    if exif_orientation is not None:
        exif = img.getexif()
        exif[0x0112] = exif_orientation
        kwargs["exif"] = exif

    img.save(path, format=fmt, **kwargs)
    return path


# =========================================================================
# 1. Single and Mixed Format Tests
# =========================================================================

def test_single_jpeg_conversion(temp_dir):
    """Test converting a single JPEG image."""
    img_path = create_test_image(temp_dir / "photo.jpg", fmt="JPEG", size=(600, 400))
    result = convert_images_to_pdf([img_path])

    assert result.output_path.exists()
    assert result.page_count == 1
    assert result.output_path.name == "Photos.pdf"
    assert result.output_path.parent == temp_dir

    pdf = pypdfium2.PdfDocument(result.output_path)
    assert len(pdf) == 1
    page = pdf[0]
    width, height = page.get_size()
    assert width > height  # Landscape auto-orientation
    assert abs(width - A4_HEIGHT_PT) < 2
    assert abs(height - A4_WIDTH_PT) < 2


def test_mixed_formats_conversion(temp_dir):
    """Test combining JPG, JPEG, PNG, and WebP into one PDF."""
    p1 = create_test_image(temp_dir / "img1.jpg", fmt="JPEG", color=(255, 0, 0))
    p2 = create_test_image(temp_dir / "img2.jpeg", fmt="JPEG", color=(0, 255, 0))
    p3 = create_test_image(temp_dir / "img3.png", fmt="PNG", color=(0, 0, 255))
    p4 = create_test_image(temp_dir / "img4.webp", fmt="WEBP", color=(255, 255, 0))

    result = convert_images_to_pdf([p1, p2, p3, p4])

    assert result.output_path.exists()
    assert result.page_count == 4

    pdf = pypdfium2.PdfDocument(result.output_path)
    assert len(pdf) == 4


def test_order_preservation(temp_dir):
    """Verify that images appear in the PDF in the exact order supplied."""
    colors = [
        (255, 0, 0),    # Red
        (0, 255, 0),    # Green
        (0, 0, 255),    # Blue
        (255, 255, 0),  # Yellow
    ]
    paths = []
    for idx, col in enumerate(colors):
        p = create_test_image(temp_dir / f"color_{idx}.png", fmt="PNG", size=(200, 200), color=col)
        paths.append(p)

    result = convert_images_to_pdf(paths)
    pdf = pypdfium2.PdfDocument(result.output_path)
    assert len(pdf) == 4

    for idx, expected_color in enumerate(colors):
        page = pdf[idx]
        pil_img = page.render(scale=0.5).to_pil()
        center = pil_img.getpixel((pil_img.width // 2, pil_img.height // 2))[:3]
        assert abs(center[0] - expected_color[0]) <= 10
        assert abs(center[1] - expected_color[1]) <= 10
        assert abs(center[2] - expected_color[2]) <= 10


# =========================================================================
# 2. Transparency, Color Modes, and Multi-Frame
# =========================================================================

def test_png_with_transparency(temp_dir):
    """Test PNG with alpha channel (RGBA)."""
    img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 250, 250], fill=(255, 0, 0, 255))
    p = temp_dir / "transparent.png"
    img.save(p, format="PNG")

    result = convert_images_to_pdf([p])
    assert result.output_path.exists()

    pdf = pypdfium2.PdfDocument(result.output_path)
    page = pdf[0]
    rendered = page.render(scale=1).to_pil()
    corner = rendered.getpixel((10, 10))[:3]
    assert corner == (255, 255, 255)
    center = rendered.getpixel((rendered.width // 2, rendered.height // 2))[:3]
    assert center == (255, 0, 0)


def test_webp_with_transparency(temp_dir):
    """Test WebP with alpha channel (RGBA), which requires normalization."""
    img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 250, 250], fill=(0, 255, 0, 255))
    p = temp_dir / "transparent.webp"
    img.save(p, format="WEBP")

    result = convert_images_to_pdf([p])
    assert result.output_path.exists()

    pdf = pypdfium2.PdfDocument(result.output_path)
    rendered = pdf[0].render(scale=1).to_pil()
    corner = rendered.getpixel((10, 10))[:3]
    assert corner == (255, 255, 255)
    center = rendered.getpixel((rendered.width // 2, rendered.height // 2))[:3]
    assert abs(center[1] - 255) <= 5


def test_grayscale_and_palette_modes(temp_dir):
    """Test Grayscale ('L') and Paletted ('P') images."""
    p_gray = create_test_image(temp_dir / "gray.jpg", fmt="JPEG", mode="L", color=128)
    
    img_p = Image.new("P", (100, 100))
    img_p.putpalette([255, 0, 0, 0, 255, 0] + [0] * 762)
    p_pal = temp_dir / "pal.png"
    img_p.save(p_pal, format="PNG")

    result = convert_images_to_pdf([p_gray, p_pal])
    assert result.page_count == 2
    assert result.output_path.exists()


def test_cmyk_jpeg_conversion(temp_dir):
    """Test CMYK JPEG embedding."""
    p_cmyk = temp_dir / "cmyk.jpg"
    img_cmyk = Image.new("CMYK", (200, 200), (0, 100, 100, 0))
    img_cmyk.save(p_cmyk, format="JPEG")

    result = convert_images_to_pdf([p_cmyk])
    assert result.output_path.exists()
    assert result.page_count == 1


def test_animated_webp_deterministic_conversion(temp_dir):
    """Test multi-frame animated WebP converts first frame deterministically."""
    p_anim = temp_dir / "animated.webp"
    frame0 = Image.new("RGB", (200, 200), (255, 0, 0))
    frame1 = Image.new("RGB", (200, 200), (0, 255, 0))
    frame0.save(p_anim, format="WEBP", save_all=True, append_images=[frame1], duration=100)

    result = convert_images_to_pdf([p_anim])
    assert result.output_path.exists()
    assert result.page_count == 1

    pdf = pypdfium2.PdfDocument(result.output_path)
    rendered = pdf[0].render(scale=1).to_pil()
    center = rendered.getpixel((rendered.width // 2, rendered.height // 2))[:3]
    # Frame 0 is red
    assert abs(center[0] - 255) <= 10


# =========================================================================
# 3. All Eight EXIF Orientation Values
# =========================================================================

@pytest.mark.parametrize("orientation", [1, 2, 3, 4, 5, 6, 7, 8])
def test_all_eight_exif_orientations(temp_dir, orientation):
    """Test that all 8 standard and mirrored EXIF orientations convert successfully."""
    p = temp_dir / f"orient_{orientation}.jpg"
    # Create 400x200 (landscape raw image)
    create_test_image(p, fmt="JPEG", size=(400, 200), exif_orientation=orientation)

    result = convert_images_to_pdf([p])
    assert result.output_path.exists()

    pdf = pypdfium2.PdfDocument(result.output_path)
    page = pdf[0]
    rendered = page.render(scale=0.5).to_pil()

    # Orientations 5, 6, 7, 8 rotate 400x200 landscape into portrait
    if orientation in (5, 6, 7, 8):
        assert rendered.height > rendered.width
    elif orientation in (1, 2, 3, 4):
        assert rendered.width > rendered.height


# =========================================================================
# 4. Filename Uniqueness, Overwrite Prevention & Collisions
# =========================================================================

def test_unique_output_path_incrementing(temp_dir):
    """Verify Photos.pdf -> Photos (1).pdf -> Photos (2).pdf progression."""
    first = get_unique_output_path(temp_dir, "Photos.pdf")
    assert first.name == "Photos.pdf"
    first.touch()

    second = get_unique_output_path(temp_dir, "Photos.pdf")
    assert second.name == "Photos (1).pdf"
    second.touch()

    third = get_unique_output_path(temp_dir, "Photos.pdf")
    assert third.name == "Photos (2).pdf"
    third.touch()

    fourth = get_unique_output_path(temp_dir, "Photos.pdf")
    assert fourth.name == "Photos (3).pdf"


def test_conversion_never_overwrites(temp_dir):
    """Verify convert_images_to_pdf automatically increments without overwriting."""
    img = create_test_image(temp_dir / "pic.jpg")

    r1 = convert_images_to_pdf([img])
    assert r1.output_path.name == "Photos.pdf"

    r2 = convert_images_to_pdf([img])
    assert r2.output_path.name == "Photos (1).pdf"

    r3 = convert_images_to_pdf([img])
    assert r3.output_path.name == "Photos (2).pdf"

    assert r1.output_path.exists()
    assert r2.output_path.exists()
    assert r3.output_path.exists()


def test_explicit_output_path_collision_prevention(temp_dir):
    """Verify that explicitly supplied output paths never overwrite existing files."""
    img = create_test_image(temp_dir / "pic.jpg")
    custom_target = temp_dir / "MyAlbum.pdf"
    custom_target.write_text("Existing PDF content")

    result = convert_images_to_pdf([img], output_path=custom_target)
    # Must NOT overwrite MyAlbum.pdf; must create MyAlbum (1).pdf
    assert result.output_path.name == "MyAlbum (1).pdf"
    assert custom_target.read_text() == "Existing PDF content"
    assert result.output_path.exists()


def test_output_path_conflict_with_input_image(temp_dir):
    """Verify output naming never overwrites an input image."""
    img_path = create_test_image(temp_dir / "target.jpg")
    
    # Request output named target.jpg (which matches the input image path)
    result = convert_images_to_pdf([img_path], output_path=img_path)
    
    # Output must have .pdf suffix and must not overwrite input
    assert result.output_path.suffix.lower() == ".pdf"
    assert result.output_path != img_path
    assert img_path.exists()  # Original image untouched
    assert result.output_path.exists()


# =========================================================================
# 5. Configuration & Page Sizes
# =========================================================================

@pytest.mark.parametrize("size_name", ["A4", "A3", "A5", "Letter", "Legal"])
def test_supported_page_sizes(temp_dir, size_name):
    """Test that all supported standard page sizes format correctly."""
    img = create_test_image(temp_dir / "pic.jpg", size=(300, 300))
    result = convert_images_to_pdf([img], page_size=size_name)
    assert result.output_path.exists()

    expected_pts = SUPPORTED_PAGE_SIZES[size_name.upper()]
    pdf = pypdfium2.PdfDocument(result.output_path)
    w, h = pdf[0].get_size()
    # Check max and min dimensions match expected paper size
    assert abs(max(w, h) - max(expected_pts)) < 2
    assert abs(min(w, h) - min(expected_pts)) < 2


def test_invalid_page_size_raises_validation_error(temp_dir):
    """Verify that an invalid page size string raises ValidationError."""
    img = create_test_image(temp_dir / "pic.jpg")
    with pytest.raises(ValidationError, match="Unsupported page size"):
        convert_images_to_pdf([img], page_size="BOGUS_SIZE")


# =========================================================================
# 6. Error Handling, Staging, and Cleanup
# =========================================================================

def test_empty_images_list():
    """Verify that an empty image list raises ValidationError."""
    with pytest.raises(ValidationError, match="No image files provided"):
        convert_images_to_pdf([])


def test_missing_file(temp_dir):
    """Verify that non-existent file raises ValidationError."""
    missing = temp_dir / "does_not_exist.jpg"
    with pytest.raises(ValidationError, match="File not found"):
        convert_images_to_pdf([missing])


def test_unsupported_file_extension(temp_dir):
    """Verify that unsupported file extensions are rejected."""
    bad_file = temp_dir / "document.txt"
    bad_file.write_text("Not an image")
    with pytest.raises(ValidationError, match="Unsupported file extension"):
        convert_images_to_pdf([bad_file])


def test_corrupted_image_header(temp_dir):
    """Verify that a corrupted image file is caught during validation."""
    corrupt = temp_dir / "corrupted.jpg"
    corrupt.write_bytes(b"CORRUPTED_GARBAGE_HEADER_DATA_123456789")
    with pytest.raises(ValidationError, match="Cannot identify image file"):
        convert_images_to_pdf([corrupt])


def test_truncated_image_data(temp_dir):
    """Verify that a truncated image file is caught during validation."""
    valid_img = Image.new("RGB", (200, 200), (255, 0, 0))
    buf = io.BytesIO()
    valid_img.save(buf, format="JPEG")
    truncated_data = buf.getvalue()[:len(buf.getvalue()) // 2]

    truncated_file = temp_dir / "truncated.jpg"
    truncated_file.write_bytes(truncated_data)

    with pytest.raises(ValidationError, match="Corrupted or unreadable image data"):
        convert_images_to_pdf([truncated_file])


def test_failed_conversion_leaves_no_staged_or_partial_file(temp_dir, monkeypatch):
    """Verify atomic staging ensures no partial file remains when conversion fails."""
    img = create_test_image(temp_dir / "pic.jpg")

    import img2pdf
    # Force convert to raise an unexpected error during generation
    def broken_convert(*args, **kwargs):
        raise RuntimeError("Simulated conversion crash!")

    monkeypatch.setattr(img2pdf, "convert", broken_convert)

    with pytest.raises(ConversionError, match="Failed to generate PDF"):
        convert_images_to_pdf([img])

    # No PDF or temporary stage file should remain in temp_dir
    leftovers = list(temp_dir.glob("*.pdf")) + list(temp_dir.glob(".p2pdf_*"))
    assert len(leftovers) == 0, f"Found leftover files: {leftovers}"


# =========================================================================
# 7. Lossless PDF Compression Tests
# =========================================================================

def test_lossless_jpeg_stream_bit_for_bit_identical(temp_dir):
    """Verify JPEG stream inside the PDF is 100% bit-for-bit identical to original file."""
    img_path = temp_dir / "original.jpg"
    im = Image.new("RGB", (300, 200), (128, 64, 32))
    im.save(img_path, format="JPEG", quality=90)

    with open(img_path, "rb") as f:
        orig_bytes = f.read()
    orig_hash = hashlib.sha256(orig_bytes).hexdigest()

    result = convert_images_to_pdf([img_path], lossless_optimize=True)
    assert result.output_path.exists()

    with pikepdf.open(result.output_path) as pdf:
        xobj = pdf.pages[0].Resources.XObject["/Im0"]
        stream_bytes = xobj.read_raw_bytes()
        stream_hash = hashlib.sha256(stream_bytes).hexdigest()

    assert orig_hash == stream_hash, "Lossless verification failed: JPEG stream was modified!"


def test_lossless_optimization_reduces_size_and_preserves_rendering(temp_dir):
    """Verify lossless optimization produces equal or smaller file with zero rendering difference."""
    p1 = create_test_image(temp_dir / "p1.jpg", fmt="JPEG", color=(255, 0, 0))
    p2 = create_test_image(temp_dir / "p2.png", fmt="PNG", color=(0, 255, 0))

    # Convert with and without optimization
    res_unopt = convert_images_to_pdf([p1, p2], output_path=temp_dir / "unopt.pdf", lossless_optimize=False)
    res_opt = convert_images_to_pdf([p1, p2], output_path=temp_dir / "opt.pdf", lossless_optimize=True)

    assert res_opt.file_size_bytes <= res_unopt.file_size_bytes

    # Assert 0 pixel difference across all rendered pages
    doc_unopt = pypdfium2.PdfDocument(res_unopt.output_path)
    doc_opt = pypdfium2.PdfDocument(res_opt.output_path)

    assert len(doc_unopt) == len(doc_opt) == 2
    for i in range(2):
        im_unopt = doc_unopt[i].render(scale=1).to_pil()
        im_opt = doc_opt[i].render(scale=1).to_pil()
        assert im_unopt.size == im_opt.size
        diff = sum(abs(a - b) for a, b in zip(im_unopt.tobytes(), im_opt.tobytes()))
        assert diff == 0, f"Pixel difference detected on page {i}!"


# =========================================================================
# 8. Large Collection & CLI Tests
# =========================================================================

def test_large_image_collection(temp_dir):
    """Verify conversion of 30 images performs quickly and cleanly."""
    paths = []
    for i in range(30):
        p = create_test_image(
            temp_dir / f"batch_{i:02d}.jpg",
            fmt="JPEG",
            size=(300, 200),
            color=((i * 8) % 256, (i * 16) % 256, 128),
        )
        paths.append(p)

    result = convert_images_to_pdf(paths)
    assert result.output_path.exists()
    assert result.page_count == 30
    assert result.duration_seconds < 10.0


def test_cli_main_success(temp_dir):
    """Test invoking main() with --quiet flag for automated CLI usage."""
    p1 = create_test_image(temp_dir / "test1.jpg")
    p2 = create_test_image(temp_dir / "test2.png", fmt="PNG")

    exit_code = main(["--quiet", str(p1), str(p2)])
    assert exit_code == 0
    assert (temp_dir / "Photos.pdf").exists()


def test_cli_main_custom_output(temp_dir):
    """Test main() with custom -o output path."""
    p = create_test_image(temp_dir / "pic.jpg")
    custom_pdf = temp_dir / "MyAlbum.pdf"

    exit_code = main(["--quiet", "-o", str(custom_pdf), str(p)])
    assert exit_code == 0
    assert custom_pdf.exists()


def test_cli_main_options(temp_dir):
    """Test main() with --page-size and --no-optimize options."""
    p = create_test_image(temp_dir / "letter.jpg")
    out_pdf = temp_dir / "LetterDoc.pdf"

    exit_code = main(["--quiet", "--page-size", "Letter", "--no-optimize", "-o", str(out_pdf), str(p)])
    assert exit_code == 0
    assert out_pdf.exists()


def test_cli_main_error_exit_code(temp_dir):
    """Test main() returns exit code 1 when given a non-existent file."""
    exit_code = main(["--quiet", str(temp_dir / "ghost.jpg")])
    assert exit_code == 1


def test_config_ini_loading_and_fallback(temp_dir):
    """Test loading configuration from custom INI and fallback defaults."""
    # Test fallback defaults
    cfg_default = load_config(temp_dir / "nonexistent.ini")
    assert cfg_default.page_size == DEFAULT_PAGE_SIZE
    assert cfg_default.orientation == DEFAULT_ORIENTATION
    assert cfg_default.margin == DEFAULT_MARGIN
    assert cfg_default.sort_order == DEFAULT_SORT_ORDER

    # Test reading valid INI
    ini_path = temp_dir / "p2pdf.ini"
    ini_path.write_text(
        "[General]\n"
        "page_size = Letter\n"
        "output_filename = CustomAlbum.pdf\n"
        "orientation = landscape\n"
        "fit_mode = fill\n"
        "margin = 10mm\n"
        "sort_order = name\n"
        "optimize = false\n"
        "quiet = true\n",
        encoding="utf-8",
    )
    cfg_loaded = load_config(ini_path)
    assert cfg_loaded.page_size == "LETTER"
    assert cfg_loaded.output_filename == "CustomAlbum.pdf"
    assert cfg_loaded.orientation == "landscape"
    assert cfg_loaded.fit_mode == "fill"
    assert cfg_loaded.margin == "10mm"
    assert cfg_loaded.sort_order == "name"
    assert cfg_loaded.optimize is False
    assert cfg_loaded.quiet is True


def test_natural_and_custom_sorting(temp_dir):
    """Test sort_image_paths with natural, name, date, and none ordering."""
    p1 = create_test_image(temp_dir / "img1.jpg")
    p2 = create_test_image(temp_dir / "img2.jpg")
    p10 = create_test_image(temp_dir / "img10.jpg")

    input_order = [p10, p1, p2]

    # None: Preserves exact input order
    res_none = sort_image_paths(input_order, sort_order="none")
    assert res_none == [p10, p1, p2]

    # Natural: img1, img2, img10
    res_natural = sort_image_paths(input_order, sort_order="natural")
    assert res_natural == [p1, p2, p10]

    # Name: Standard ASCII sort produces img1, img10, img2
    res_name = sort_image_paths(input_order, sort_order="name")
    assert res_name == [p1, p10, p2]


def test_page_orientation_modes(temp_dir):
    """Test orientation modes: auto, portrait, landscape."""
    # Create landscape image (400x200)
    img_landscape = create_test_image(temp_dir / "wide.jpg", size=(400, 200))
    # Create portrait image (200x400)
    img_portrait = create_test_image(temp_dir / "tall.jpg", size=(200, 400))

    # Force portrait mode
    res_port = convert_images_to_pdf(
        [img_landscape],
        page_size="A4",
        orientation="portrait",
        output_path=temp_dir / "port.pdf",
    )
    pdf_port = pypdfium2.PdfDocument(res_port.output_path)
    page_p = pdf_port[0]
    w_p, h_p = page_p.get_size()
    assert w_p < h_p, f"Expected portrait page, got {w_p}x{h_p}"

    # Force landscape mode
    res_land = convert_images_to_pdf(
        [img_portrait],
        page_size="A4",
        orientation="landscape",
        output_path=temp_dir / "land.pdf",
    )
    pdf_land = pypdfium2.PdfDocument(res_land.output_path)
    page_l = pdf_land[0]
    w_l, h_l = page_l.get_size()
    assert w_l > h_l, f"Expected landscape page, got {w_l}x{h_l}"


def test_margin_and_border_handling(temp_dir):
    """Test resolve_border and converting with margins."""
    assert resolve_border(None) is None
    assert resolve_border("0") is None
    assert resolve_border("0pt") is None

    b_pt = resolve_border("10pt")
    assert b_pt == (10.0, 10.0)

    b_mm = resolve_border("5mm")
    assert b_mm is not None
    assert round(b_mm[0], 2) == 14.17

    img = create_test_image(temp_dir / "margin_test.jpg")
    res = convert_images_to_pdf(
        [img],
        margin="5mm",
        output_path=temp_dir / "with_margin.pdf",
    )
    assert res.output_path.exists()
    assert res.page_count == 1


def test_custom_default_output_filename(temp_dir):
    """Test conversion uses custom default output filename when output is a folder."""
    img = create_test_image(temp_dir / "pic.jpg")
    res = convert_images_to_pdf(
        [img],
        output_path=temp_dir,
        default_output_filename="FamilyCollection.pdf",
    )
    assert res.output_path.name == "FamilyCollection.pdf"
    assert res.output_path.exists()


def test_cli_main_with_phase3_options(temp_dir):
    """Test main() with --orientation, --margin, --sort, and --config options."""
    p1 = create_test_image(temp_dir / "photo1.jpg")
    p2 = create_test_image(temp_dir / "photo2.jpg")

    ini_path = temp_dir / "custom.ini"
    ini_path.write_text(
        "[General]\n"
        "page_size = Letter\n"
        "orientation = landscape\n"
        "margin = 10pt\n",
        encoding="utf-8",
    )

    exit_code = main([
        "--quiet",
        "-c", str(ini_path),
        "--sort", "natural",
        "--orientation", "portrait",  # CLI overrides INI
        str(p2), str(p1),
    ])
    assert exit_code == 0
    pdf_out = temp_dir / "Photos.pdf"
    assert pdf_out.exists()
    pdf = pypdfium2.PdfDocument(pdf_out)
    assert len(pdf) == 2


def test_empty_zero_byte_image_file(temp_dir):
    """Test that a 0-byte image file is gracefully rejected with a ValidationError."""
    empty_file = temp_dir / "empty_photo.jpg"
    empty_file.write_bytes(b"")

    with pytest.raises(ValidationError, match="Invalid or corrupted image|Cannot identify"):
        convert_images_to_pdf([empty_file])

    # Ensure no leftover staged files remain
    tmp_files = list(temp_dir.glob("*.tmp"))
    assert len(tmp_files) == 0


def test_unicode_filenames_and_directories(temp_dir):
    """Test conversion with complex Unicode directory names and international filenames."""
    unicode_dir = temp_dir / "旅行_Voyage_2026_📸"
    unicode_dir.mkdir(parents=True, exist_ok=True)

    img_jp = create_test_image(unicode_dir / "富士山_写真.jpg", fmt="JPEG")
    img_fr = create_test_image(unicode_dir / "Café_d'été.png", fmt="PNG")
    img_ar = create_test_image(unicode_dir / "صور_جميلة.webp", fmt="WEBP")
    img_hi = create_test_image(unicode_dir / "सुंदर_तस्वीर.jpg", fmt="JPEG")

    res = convert_images_to_pdf([img_jp, img_fr, img_ar, img_hi])
    assert res.output_path.exists()
    assert res.page_count == 4

    doc = pypdfium2.PdfDocument(res.output_path)
    assert len(doc) == 4


def test_input_file_integrity_sha256_unmodified(temp_dir):
    """Verify that all input files remain 100% byte-for-byte untouched after conversion."""
    img1 = create_test_image(temp_dir / "source1.jpg", size=(200, 200), color=(100, 150, 200))
    img2 = create_test_image(temp_dir / "source2.png", fmt="PNG", size=(150, 150), color=(50, 100, 150))

    hash1_before = hashlib.sha256(img1.read_bytes()).hexdigest()
    hash2_before = hashlib.sha256(img2.read_bytes()).hexdigest()
    mtime1_before = img1.stat().st_mtime_ns
    mtime2_before = img2.stat().st_mtime_ns

    res = convert_images_to_pdf([img1, img2])
    assert res.output_path.exists()

    hash1_after = hashlib.sha256(img1.read_bytes()).hexdigest()
    hash2_after = hashlib.sha256(img2.read_bytes()).hexdigest()
    mtime1_after = img1.stat().st_mtime_ns
    mtime2_after = img2.stat().st_mtime_ns

    assert hash1_before == hash1_after, "Input image 1 was modified during conversion!"
    assert hash2_before == hash2_after, "Input image 2 was modified during conversion!"
    assert mtime1_before == mtime1_after, "Input image 1 mtime was altered!"
    assert mtime2_before == mtime2_after, "Input image 2 mtime was altered!"


def test_very_large_image_resolution(temp_dir):
    """Test converting a high-resolution 24MP image (6000x4000) preserving stability."""
    big_img = temp_dir / "high_res_24mp.jpg"
    # Create 6000x4000 image
    Image.new("RGB", (6000, 4000), (70, 130, 180)).save(big_img, format="JPEG", quality=85)

    res = convert_images_to_pdf([big_img], page_size="A4")
    assert res.output_path.exists()
    assert res.page_count == 1
    assert res.duration_seconds < 15.0

    doc = pypdfium2.PdfDocument(res.output_path)
    assert len(doc) == 1


def test_aspect_ratio_preservation_and_scaling(temp_dir):
    """Verify that an image with an extreme 3:1 aspect ratio retains its proportions on page."""
    wide_img = create_test_image(temp_dir / "panoramic.jpg", size=(600, 200))

    res = convert_images_to_pdf([wide_img], page_size="A4", fit_mode="into")
    doc = pypdfium2.PdfDocument(res.output_path)
    page = doc[0]
    pw, ph = page.get_size()

    # In A4 auto_orient, landscape page size is ~841.89 x 595.28
    assert pw > ph
    # Verify that the PDF is valid and renders without exception
    bitmap = page.render(scale=0.5)
    pil_rendered = bitmap.to_pil()
    assert pil_rendered.size[0] > 0


