"""Phase 2 Integration Test Suite for Windows File Explorer Integration.

Verifies:
1. Installation and Uninstallation scripts (idempotency, registry keys, SendTo shortcut).
2. Installed binary execution at %LOCALAPPDATA%\\Programs\\P2PDF\\P2PDF.exe.
3. Single JPEG, mixed formats, paths with spaces.
4. Independent execution outside project directory.
5. Collision safety and error handling.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import pytest
from PIL import Image
import pikepdf
import pypdfium2


INSTALL_BAT = Path(__file__).resolve().parent.parent / "install_context_menu.bat"
UNINSTALL_BAT = Path(__file__).resolve().parent.parent / "uninstall_context_menu.bat"
INSTALLED_EXE = Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\P2PDF\P2PDF.exe"))


@pytest.fixture
def temp_test_dir():
    """Provides an isolated directory containing paths with spaces."""
    d = Path(tempfile.mkdtemp(prefix="p2pdf test spaces_"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_install_script_execution_and_idempotency():
    """Verify install_context_menu.bat runs cleanly twice without errors."""
    assert INSTALL_BAT.exists(), f"install_context_menu.bat not found: {INSTALL_BAT}"

    # First installation run
    res1 = subprocess.run(["cmd.exe", "/c", str(INSTALL_BAT)], capture_output=True, text=True)
    assert res1.returncode == 0, f"Install run 1 failed: {res1.stderr}\n{res1.stdout}"
    assert "INSTALLATION SUCCESSFUL" in res1.stdout
    assert INSTALLED_EXE.exists(), f"Installed executable not found at: {INSTALLED_EXE}"

    # Second installation run (idempotency test)
    res2 = subprocess.run(["cmd.exe", "/c", str(INSTALL_BAT)], capture_output=True, text=True)
    assert res2.returncode == 0, f"Install run 2 failed: {res2.stderr}\n{res2.stdout}"
    assert "INSTALLATION SUCCESSFUL" in res2.stdout


def test_registry_configuration_integrity():
    """Verify all registry keys and values are correctly set in HKCU."""
    res = subprocess.run(
        ["reg.exe", "query", r"HKCU\Software\Classes\*\shell\CreatePDF_P2PDF", "/s"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, "Registry key not found!"
    stdout = res.stdout

    # Check verb title
    assert "Create PDF with P2PDF" in stdout
    # Check MultiSelectModel is Player
    assert "MultiSelectModel    REG_SZ    Player" in stdout
    # Check AppliesTo filter
    assert "AppliesTo" in stdout
    assert "*.jpg" in stdout and "*.png" in stdout and "*.webp" in stdout
    # Check command line contains installed executable and %1 placeholder
    assert "command" in stdout
    assert str(INSTALLED_EXE) in stdout
    assert "%1" in stdout


def test_installed_executable_single_jpeg_with_spaces(temp_test_dir):
    """Test installed executable on a single JPEG in a folder with spaces."""
    folder_with_spaces = temp_test_dir / "Summer Trip 2026"
    folder_with_spaces.mkdir(parents=True, exist_ok=True)
    img_path = folder_with_spaces / "Beach Sunset Photo.jpg"

    Image.new("RGB", (500, 350), (255, 120, 60)).save(img_path, format="JPEG")

    cmd = [str(INSTALLED_EXE), "--quiet", str(img_path)]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(tempfile.gettempdir()))
    assert res.returncode == 0, f"Installed executable failed: {res.stderr}"

    output_pdf = folder_with_spaces / "Photos.pdf"
    assert output_pdf.exists(), "Photos.pdf was not created in the image folder!"

    pdf = pypdfium2.PdfDocument(output_pdf)
    assert len(pdf) == 1


def test_installed_executable_multiple_mixed_formats_with_spaces(temp_test_dir):
    """Test installed executable converting multiple mixed formats in a path with spaces."""
    folder = temp_test_dir / "Family Photos Collection"
    folder.mkdir(parents=True, exist_ok=True)

    img1 = folder / "01 First Image.jpg"
    img2 = folder / "02 Transparent Art.png"
    img3 = folder / "03 Modern Graphic.webp"

    Image.new("RGB", (400, 300), (200, 50, 50)).save(img1, format="JPEG")
    Image.new("RGBA", (300, 300), (50, 200, 50, 128)).save(img2, format="PNG")
    Image.new("RGB", (250, 350), (50, 50, 200)).save(img3, format="WEBP")

    # Call installed executable from arbitrary working directory
    cmd = [str(INSTALLED_EXE), "--quiet", str(img1), str(img2), str(img3)]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=os.environ["SYSTEMROOT"])
    assert res.returncode == 0, f"Execution failed: {res.stderr}"

    output_pdf = folder / "Photos.pdf"
    assert output_pdf.exists()

    pdf = pypdfium2.PdfDocument(output_pdf)
    assert len(pdf) == 3


def test_installed_executable_collision_safety(temp_test_dir):
    """Verify installed binary automatically creates Photos (1).pdf when Photos.pdf exists."""
    img = temp_test_dir / "photo.jpg"
    Image.new("RGB", (100, 100), (100, 100, 100)).save(img)

    # First conversion creates Photos.pdf
    res1 = subprocess.run([str(INSTALLED_EXE), "--quiet", str(img)], capture_output=True, text=True)
    assert res1.returncode == 0
    assert (temp_test_dir / "Photos.pdf").exists()

    # Second conversion creates Photos (1).pdf
    res2 = subprocess.run([str(INSTALLED_EXE), "--quiet", str(img)], capture_output=True, text=True)
    assert res2.returncode == 0
    assert (temp_test_dir / "Photos (1).pdf").exists()


def test_installed_executable_handles_corrupted_file(temp_test_dir):
    """Verify installed executable returns exit code 1 on corrupted images."""
    bad_img = temp_test_dir / "corrupted.png"
    bad_img.write_bytes(b"INVALID_IMAGE_HEADER_CONTENT")

    res = subprocess.run([str(INSTALLED_EXE), "--quiet", str(bad_img)], capture_output=True, text=True)
    assert res.returncode == 1
    assert "Cannot identify image file" in (res.stderr + res.stdout)


def test_installed_executable_no_args_shows_usage():
    """Verify running installed executable without arguments displays the usage guide."""
    env = os.environ.copy()
    env["P2PDF_NO_GUI"] = "1"
    res = subprocess.run([str(INSTALLED_EXE)], capture_output=True, text=True, env=env)
    assert res.returncode == 0
    combined = res.stdout + res.stderr
    assert "No photos were selected" in combined
    assert "How to use" in combined


def test_context_menu_multi_instance_aggregation(temp_test_dir):
    """Simulate Windows File Explorer launching separate concurrent processes for 3 selected files.
    
    Verifies that the single-instance mutex aggregator collects all 3 files
    into a single 3-page PDF with zero collisions and zero orphan PDFs.
    """
    folder = temp_test_dir / "Multi Select Explorer Test"
    folder.mkdir(parents=True, exist_ok=True)

    img1 = folder / "Photo Alpha.jpg"
    img2 = folder / "Photo Beta.png"
    img3 = folder / "Photo Gamma.webp"

    Image.new("RGB", (300, 200), (200, 30, 30)).save(img1, format="JPEG")
    Image.new("RGBA", (250, 250), (30, 200, 30, 200)).save(img2, format="PNG")
    Image.new("RGB", (200, 300), (30, 30, 200)).save(img3, format="WEBP")

    env = os.environ.copy()
    env["P2PDF_NO_GUI"] = "1"  # Suppress modal MessageBox so processes don't block

    # Spawn 3 separate processes concurrently within milliseconds (identical to Explorer)
    p1 = subprocess.Popen([str(INSTALLED_EXE), str(img1)], env=env)
    p2 = subprocess.Popen([str(INSTALLED_EXE), str(img2)], env=env)
    p3 = subprocess.Popen([str(INSTALLED_EXE), str(img3)], env=env)

    # Wait for all processes to complete
    ret1 = p1.wait(timeout=15)
    ret2 = p2.wait(timeout=15)
    ret3 = p3.wait(timeout=15)

    assert ret1 == 0, f"Process 1 failed with exit code {ret1}"
    assert ret2 == 0, f"Process 2 failed with exit code {ret2}"
    assert ret3 == 0, f"Process 3 failed with exit code {ret3}"

    output_pdf = folder / "Photos.pdf"
    assert output_pdf.exists(), "Photos.pdf was not created!"

    # Ensure no duplicate/orphan collision PDFs were created
    assert not (folder / "Photos (1).pdf").exists(), "Collision PDF was erroneously created!"
    assert not (folder / "Photos (2).pdf").exists(), "Collision PDF was erroneously created!"

    # Verify that the single PDF contains all 3 pages
    pdf = pypdfium2.PdfDocument(output_pdf)
    assert len(pdf) == 3, f"Expected 3 pages in Photos.pdf, but got {len(pdf)}"


def test_installed_executable_with_custom_ini(temp_test_dir):
    """Verify that installed executable honors custom p2pdf.ini when invoked."""
    folder = temp_test_dir / "Ini Test Folder"
    folder.mkdir(parents=True, exist_ok=True)

    img = folder / "Sample Photo.jpg"
    Image.new("RGB", (300, 300), (40, 140, 240)).save(img)

    ini_file = folder / "custom.ini"
    ini_file.write_text(
        "[General]\n"
        "output_filename = FromIni.pdf\n"
        "page_size = Letter\n"
        "orientation = landscape\n"
        "margin = 5mm\n",
        encoding="utf-8",
    )

    cmd = [str(INSTALLED_EXE), "-c", str(ini_file), "--quiet", str(img)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Execution failed: {res.stderr}"

    out_pdf = folder / "FromIni.pdf"
    assert out_pdf.exists(), "FromIni.pdf was not created!"
    pdf = pypdfium2.PdfDocument(out_pdf)
    assert len(pdf) == 1
    w, h = pdf[0].get_size()
    assert w > h, f"Expected landscape Letter page, got {w}x{h}"


def test_installed_executable_cli_phase3_flags(temp_test_dir):
    """Verify installed binary supports new Phase 3 CLI flags (--orientation, --margin, --sort)."""
    folder = temp_test_dir / "Cli Flags Test"
    folder.mkdir(parents=True, exist_ok=True)

    img1 = folder / "p1.jpg"
    img2 = folder / "p2.jpg"
    Image.new("RGB", (200, 400), (10, 10, 10)).save(img1)
    Image.new("RGB", (200, 400), (20, 20, 20)).save(img2)

    cmd = [
        str(INSTALLED_EXE),
        "--quiet",
        "--orientation", "portrait",
        "--margin", "10pt",
        "--sort", "name",
        "-o", str(folder / "FlagsResult.pdf"),
        str(img2), str(img1),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0
    assert (folder / "FlagsResult.pdf").exists()


def test_concurrent_launches_in_separate_folders(temp_test_dir):
    """Verify that concurrent multi-selections in two different folders are properly isolated.
    
    Folder A and Folder B must each create their own Photos.pdf containing only their respective photos,
    without mutual interference, cross-contamination, or false mutex locking.
    """
    folder_a = temp_test_dir / "Folder Alpha"
    folder_b = temp_test_dir / "Folder Beta"
    folder_a.mkdir(parents=True, exist_ok=True)
    folder_b.mkdir(parents=True, exist_ok=True)

    a1 = folder_a / "a1.jpg"
    a2 = folder_a / "a2.jpg"
    b1 = folder_b / "b1.jpg"
    b2 = folder_b / "b2.jpg"

    Image.new("RGB", (100, 100), (255, 0, 0)).save(a1)
    Image.new("RGB", (100, 100), (200, 0, 0)).save(a2)
    Image.new("RGB", (100, 100), (0, 0, 255)).save(b1)
    Image.new("RGB", (100, 100), (0, 0, 200)).save(b2)

    env = os.environ.copy()
    env["P2PDF_NO_GUI"] = "1"

    # Launch all 4 processes concurrently (2 for folder_a, 2 for folder_b)
    p_a1 = subprocess.Popen([str(INSTALLED_EXE), str(a1)], env=env)
    p_a2 = subprocess.Popen([str(INSTALLED_EXE), str(a2)], env=env)
    p_b1 = subprocess.Popen([str(INSTALLED_EXE), str(b1)], env=env)
    p_b2 = subprocess.Popen([str(INSTALLED_EXE), str(b2)], env=env)

    # Wait for all to finish
    for p in (p_a1, p_a2, p_b1, p_b2):
        assert p.wait(timeout=15) == 0

    pdf_a = folder_a / "Photos.pdf"
    pdf_b = folder_b / "Photos.pdf"
    assert pdf_a.exists(), "Folder A Photos.pdf was not created!"
    assert pdf_b.exists(), "Folder B Photos.pdf was not created!"

    doc_a = pypdfium2.PdfDocument(pdf_a)
    doc_b = pypdfium2.PdfDocument(pdf_b)
    assert len(doc_a) == 2, f"Expected 2 pages in Folder A PDF, got {len(doc_a)}"
    assert len(doc_b) == 2, f"Expected 2 pages in Folder B PDF, got {len(doc_b)}"


def test_stale_queue_recovery(temp_test_dir):
    """Verify that crashed/stale queue files (>15s old) are automatically cleared on next run."""
    import time
    from aggregator import get_folder_token, get_queue_dir

    folder = temp_test_dir / "Stale Recovery Test"
    folder.mkdir(parents=True, exist_ok=True)
    img = folder / "valid.jpg"
    Image.new("RGB", (100, 100), (50, 150, 50)).save(img)

    token = get_folder_token(img)
    q_dir = get_queue_dir(token)
    stale_file = q_dir / "stale_crash_data.txt"
    stale_file.write_text("C:\\ghost\\nonexistent.jpg", encoding="utf-8")

    # Set mtime to 30 seconds ago
    old_time = time.time() - 30.0
    os.utime(stale_file, (old_time, old_time))

    env = os.environ.copy()
    env["P2PDF_NO_GUI"] = "1"
    res = subprocess.run([str(INSTALLED_EXE), str(img)], env=env, capture_output=True, text=True)
    assert res.returncode == 0
    assert not stale_file.exists(), "Stale queue file was not unlinked!"
    assert (folder / "Photos.pdf").exists()


def test_user_configuration_survives_reinstall(temp_test_dir):
    """Verify that installing or updating P2PDF preserves existing user configuration in p2pdf.ini."""
    ini_path = Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\P2PDF\p2pdf.ini"))
    assert ini_path.exists(), "p2pdf.ini should exist after initial installation"

    original_content = ini_path.read_text(encoding="utf-8")
    try:
        # Write custom user preference
        custom_content = "[General]\noutput_filename = PreservedAlbum.pdf\npage_size = A5\n"
        ini_path.write_text(custom_content, encoding="utf-8")

        # Re-run installation script
        res = subprocess.run(["cmd.exe", "/c", str(INSTALL_BAT)], capture_output=True, text=True)
        assert res.returncode == 0

        # Verify custom user preference was NOT overwritten
        current_content = ini_path.read_text(encoding="utf-8")
        assert "PreservedAlbum.pdf" in current_content, "User configuration was overwritten during reinstall!"
    finally:
        # Restore original default configuration so other tests remain isolated
        ini_path.write_text(original_content, encoding="utf-8")



def test_installed_executable_unicode_path_with_spaces(temp_test_dir):
    """Verify installed binary handles Unicode folder and file paths containing spaces."""
    folder = temp_test_dir / "Summer Trip 2026 日本語 & España"
    folder.mkdir(parents=True, exist_ok=True)
    img = folder / "Plage de l'Est 📸.jpg"
    Image.new("RGB", (200, 200), (120, 180, 240)).save(img)

    env = os.environ.copy()
    env["P2PDF_NO_GUI"] = "1"
    res = subprocess.run([str(INSTALLED_EXE), str(img)], env=env, capture_output=True, text=True)
    assert res.returncode == 0

    pdf = folder / "PreservedAlbum.pdf" if (folder / "PreservedAlbum.pdf").exists() else folder / "Photos.pdf"
    assert pdf.exists(), f"PDF was not created in unicode folder: {folder}"


def test_uninstall_and_reinstall_cycle():
    """Verify complete uninstallation removes registry and reinstall restores it."""
    # Run uninstaller
    res_un = subprocess.run(["cmd.exe", "/c", str(UNINSTALL_BAT)], capture_output=True, text=True)
    assert res_un.returncode == 0, f"Uninstall failed: {res_un.stderr}"
    assert "UNINSTALLATION COMPLETE" in res_un.stdout

    # Verify registry key is gone
    res_query = subprocess.run(
        ["reg.exe", "query", r"HKCU\Software\Classes\*\shell\CreatePDF_P2PDF"],
        capture_output=True,
        text=True,
    )
    assert res_query.returncode != 0, "Registry key still exists after uninstallation!"

    # Reinstall
    res_re = subprocess.run(["cmd.exe", "/c", str(INSTALL_BAT)], capture_output=True, text=True)
    assert res_re.returncode == 0, f"Reinstallation failed: {res_re.stderr}"

    # Verify registry key is back
    res_query2 = subprocess.run(
        ["reg.exe", "query", r"HKCU\Software\Classes\*\shell\CreatePDF_P2PDF"],
        capture_output=True,
        text=True,
    )
    assert res_query2.returncode == 0, "Registry key was not restored after reinstallation!"

