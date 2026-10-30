"""P2PDF - Single-Instance Multi-File Argument Aggregator.

When Windows File Explorer invokes a context menu verb on multiple selected files,
it spawns a separate process for each file. This module aggregates those separate
invocations into a single batch so only one PDF is created and only one dialog is shown.
"""

from __future__ import annotations

import ctypes
import getpass
import hashlib
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import List, Tuple


def get_folder_token(image_path: Path) -> str:
    """Computes a deterministic hash token representing the parent folder of an image."""
    try:
        norm_dir = str(image_path.resolve().parent).lower()
    except Exception:
        norm_dir = str(image_path.parent).lower()
    return hashlib.sha256(norm_dir.encode("utf-8")).hexdigest()[:16]


def get_queue_dir(folder_token: str | None = None) -> Path:
    """Returns the user-isolated and folder-scoped queue directory for aggregation."""
    user = getpass.getuser()
    suffix = f"_{folder_token}" if folder_token else ""
    queue = Path(tempfile.gettempdir()) / f"P2PDF_Queue_{user}{suffix}"
    queue.mkdir(parents=True, exist_ok=True)
    return queue


def aggregate_context_menu_files(
    image_path: Path,
    sort_order: str = "natural",
) -> Tuple[bool, List[Path]]:
    """Aggregates multiple individual file launches from Windows File Explorer.

    Parameters:
    - image_path: Path to the image file passed to this process instance.
    - sort_order: Sorting strategy to apply to gathered files ('natural', 'name', 'date', 'none').

    Returns:
    - (is_primary: bool, collected_paths: List[Path])
    - If is_primary is False: This is a secondary instance. The file was queued and
      the caller should exit immediately with code 0 without displaying any UI.
    - If is_primary is True: This is the lead instance. It has gathered all files
      from the current selection burst, sorted them, and should proceed with conversion.
    """
    folder_token = get_folder_token(image_path)
    queue_dir = get_queue_dir(folder_token)

    # Clean up any stale queue files older than 15 seconds
    now = time.time()
    for stale_file in queue_dir.glob("*.txt"):
        try:
            if now - stale_file.stat().st_mtime > 15:
                stale_file.unlink(missing_ok=True)
        except OSError:
            pass

    # 1. Deposit our file into the queue
    item_id = f"{time.time_ns()}_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    item_file = queue_dir / f"{item_id}.txt"
    item_file.write_text(str(image_path.resolve()), encoding="utf-8")

    # 2. Try to acquire the Lead Instance Mutex scoped to this user and folder
    kernel32 = ctypes.windll.kernel32
    user = getpass.getuser()
    mutex_name = f"P2PDF_Lead_Mutex_{user}_{folder_token}"

    handle = kernel32.CreateMutexW(None, False, mutex_name)
    already_exists = (kernel32.GetLastError() == 183)  # ERROR_ALREADY_EXISTS

    if already_exists:
        # Another instance is already the lead instance for this folder selection.
        # It will read our deposited file from the queue.
        # Close our handle and exit quietly.
        kernel32.CloseHandle(handle)
        return False, []

    # We are the Lead / Primary instance!
    try:
        # Collect all files deposited during this burst.
        # Windows launches instances within 10-150ms of each other.
        last_count = 0
        start_wait = time.perf_counter()
        total_start = time.perf_counter()

        while True:
            time.sleep(0.04)
            current_files = sorted(
                queue_dir.glob("*.txt"),
                key=lambda p: (p.stat().st_mtime_ns if p.exists() else 0, p.name)
            )
            if len(current_files) > last_count:
                last_count = len(current_files)
                start_wait = time.perf_counter()
            elif time.perf_counter() - start_wait >= 0.30:
                # No new files have arrived for 300ms, burst is complete
                break
            elif time.perf_counter() - total_start >= 5.0:
                # Maximum debounce cutoff reached
                break

        collected_paths: List[Path] = []
        for qf in sorted(
            queue_dir.glob("*.txt"),
            key=lambda p: (p.stat().st_mtime_ns if p.exists() else 0, p.name)
        ):
            try:
                content = qf.read_text(encoding="utf-8").strip()
                if content:
                    path = Path(content).resolve()
                    if path not in collected_paths:
                        collected_paths.append(path)
                qf.unlink(missing_ok=True)
            except OSError:
                pass

        if not collected_paths:
            collected_paths = [image_path.resolve()]

        # Apply requested sorting strategy
        from converter import sort_image_paths
        sorted_collected = sort_image_paths(collected_paths, sort_order)

        return True, sorted_collected

    finally:
        kernel32.CloseHandle(handle)
        # Attempt to remove empty queue directory
        try:
            queue_dir.rmdir()
        except OSError:
            pass



