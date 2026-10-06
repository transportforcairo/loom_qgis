# -*- coding: utf-8 -*-
"""
downloader.py — Download pre-built LOOM binaries from the loom_binaries repo.

Binaries are stored as ZIP files in the root of:
  https://github.com/transportforcairo/loom_binaries

They are downloaded from a *pinned tag* (BINARIES_REF) via
raw.githubusercontent.com — no API, no tokens. Pinning means a rebuild on the
binaries repo's main branch never silently changes what an installed plugin
version downloads. Each download is checked against the SHA256SUMS file
published at the same tag.

ZIP naming convention:
    loom-binaries-windows-x64.zip
    loom-binaries-macos-arm64.zip
    loom-binaries-linux-x64.zip

Each ZIP contains the binaries (sub-folders are flattened on extraction):
    loom.exe, topo.exe, ... + DLLs   (Windows)
    loom, topo, octi, ...             (macOS / Linux, no external libraries)

Releasing new binaries: build them in loom_binaries, push a new tag there,
then bump BINARIES_REF below in the same plugin release.
"""

import hashlib
import os
import platform
import stat
import tempfile
import urllib.request
import zipfile
from typing import Callable, Dict, Optional

from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BINARIES_REPO = "transportforcairo/loom_binaries"

# Tag in the loom_binaries repo that this plugin version downloads from.
BINARIES_REF = "v1.1.0"

# Base URL for raw file downloads
_RAW_BASE = f"https://raw.githubusercontent.com/{BINARIES_REPO}/{BINARIES_REF}"

CHECKSUMS_FILE = "SHA256SUMS"

# Written next to the binaries after a successful install, so that binaries
# from an older build can be detected and an update offered.
_REF_MARKER = ".loom_binaries_ref"

# Map (system, machine) → ZIP filename suffix.
# Only real builds are listed: an arm64 binary cannot run on an Intel Mac
# (Rosetta only translates Intel code for Apple Silicon, not the reverse), and
# an x64 Linux binary cannot run on ARM Linux.
_ASSET_MAP = {
    ("Windows", "AMD64"):   "windows-x64",
    ("Windows", "x86_64"):  "windows-x64",
    ("Darwin",  "arm64"):   "macos-arm64",
    ("Linux",   "x86_64"):  "linux-x64",
}

_PLATFORM_SUBDIR = {
    "Windows": "windows",
    "Darwin":  "macos",
    "Linux":   "linux",
}

ALLOWED_SCHEMES = {"http", "https"}

USER_AGENT = "loom_qgis/1.2.0"

# ---------------------------------------------------------------------------
# Progress callback: (bytes_downloaded, total_bytes_or_None, message)
# ---------------------------------------------------------------------------
ProgressCB = Callable[[int, Optional[int], str], None]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(
            f"Refusing to open URL with scheme {parsed.scheme!r}; "
            f"only {sorted(ALLOWED_SCHEMES)} allowed."
        )
    if not parsed.netloc:
        raise ValueError(f"URL missing host: {url!r}")


def _plugin_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def bin_dir() -> str:
    """Folder the binaries for the current OS are installed into."""
    system = platform.system()
    sub    = _PLATFORM_SUBDIR.get(system, "linux")
    return os.path.join(_plugin_dir(), "bin", sub)


# Backwards-compatible private alias
_bin_dir = bin_dir


def _is_apple_silicon() -> bool:
    """True on Apple Silicon hardware, even when QGIS itself is an Intel
    build running under Rosetta 2 (platform.machine() then says x86_64).
    The kernel version string is not translated by Rosetta and names the
    real architecture, e.g. '...RELEASE_ARM64_T6000'."""
    return "ARM64" in platform.version().upper()


def host_platform() -> tuple:
    """(system, machine) of the hardware, used to pick the binary build."""
    system  = platform.system()
    machine = platform.machine()
    if system == "Darwin" and machine == "x86_64" and _is_apple_silicon():
        # Intel QGIS under Rosetta can still launch native arm64 binaries.
        machine = "arm64"
    return system, machine


def asset_name() -> str:
    system, machine = host_platform()
    suffix = _ASSET_MAP.get((system, machine))
    if not suffix:
        raise RuntimeError(
            f"No pre-built LOOM binaries are available for {system} {machine}.\n\n"
            "Pre-built binaries exist for Windows x64, macOS on Apple Silicon "
            "(M1 or newer) and Linux x64.\n\n"
            "On other platforms, build LOOM from source "
            "(https://github.com/ad-freiburg/loom) and make sure loom, topo, "
            "octi, gtfs2graph and transitmap are on your PATH — the plugin "
            "will use them automatically."
        )
    return f"loom-binaries-{suffix}.zip"


def _open(url: str, timeout: int):
    if not url.lower().startswith("https://"):
        raise ValueError(f"Refusing to download from non-https URL: {url}")
    _validate_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    # Scheme validated above: only https:// URLs reach urlopen.
    return urllib.request.urlopen(req, timeout=timeout)  # nosec B310


def _fetch_checksums() -> Dict[str, str]:
    """Return {filename: sha256} from the SHA256SUMS file at BINARIES_REF."""
    url = f"{_RAW_BASE}/{CHECKSUMS_FILE}"
    try:
        with _open(url, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise RuntimeError(
            f"Could not download the checksum file for LOOM binaries "
            f"({BINARIES_REF}).\n{url}\n\n{exc}"
        ) from exc

    sums: Dict[str, str] = {}
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and len(parts[0]) == 64:
            sums[parts[1].lstrip("*")] = parts[0].lower()
    return sums


def _download_file(url: str, dest_path: str, progress_cb: Optional[ProgressCB]) -> str:
    """Stream url to dest_path; return the SHA-256 hex digest of the content."""
    digest = hashlib.sha256()
    with _open(url, timeout=120) as resp:
        total      = resp.headers.get("Content-Length")
        total      = int(total) if total else None
        downloaded = 0
        chunk_size = 64 * 1024  # 64 KB

        with open(dest_path, "wb") as fh:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                fh.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    mb = downloaded / 1_048_576
                    if total:
                        msg = f"Downloading… {mb:.1f} / {total / 1_048_576:.1f} MB"
                    else:
                        msg = f"Downloading… {mb:.1f} MB"
                    progress_cb(downloaded, total, msg)
    return digest.hexdigest()


def _clear_dir(path: str) -> None:
    """Remove the files of a previous install so no stale libraries remain."""
    if not os.path.isdir(path):
        return
    for fname in os.listdir(path):
        fpath = os.path.join(path, fname)
        if os.path.isfile(fpath) or os.path.islink(fpath):
            os.unlink(fpath)


def _extract_zip(zip_path: str, dest_dir: str) -> None:
    """Extract ZIP flat into dest_dir; make binaries executable on Unix."""
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            if member.is_dir() or "__MACOSX" in member.filename:
                continue
            filename = os.path.basename(member.filename)
            if not filename or filename.startswith("."):
                continue
            dest_file = os.path.join(dest_dir, filename)
            with zf.open(member) as src, open(dest_file, "wb") as dst:
                dst.write(src.read())

    if platform.system() != "Windows":
        for fname in os.listdir(dest_dir):
            fpath = os.path.join(dest_dir, fname)
            if fname.startswith("."):
                continue
            st = os.stat(fpath)
            os.chmod(fpath, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def binaries_present() -> bool:
    """True if the main loom binary already exists in the bin dir."""
    system = platform.system()
    ext    = ".exe" if system == "Windows" else ""
    return os.path.isfile(os.path.join(bin_dir(), f"loom{ext}"))


def installed_ref() -> Optional[str]:
    """Tag of the installed binaries, or None if unknown (pre-1.1 install)."""
    try:
        with open(os.path.join(bin_dir(), _REF_MARKER), "r", encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def binaries_outdated() -> bool:
    """True if bundled binaries exist but come from a different build."""
    return binaries_present() and installed_ref() != BINARIES_REF


def download_binaries(progress_cb: Optional[ProgressCB] = None) -> str:
    """
    Download, verify and install LOOM binaries for the current platform.
    Returns the bin_dir path on success.
    Raises RuntimeError with a human-readable message on failure.
    """
    name = asset_name()
    url  = f"{_RAW_BASE}/{name}"

    if progress_cb:
        progress_cb(0, None, "Connecting to GitHub…")

    expected = _fetch_checksums().get(name)
    if not expected:
        raise RuntimeError(
            f"{name} is not listed in {CHECKSUMS_FILE} for {BINARIES_REF}.\n"
            f"Please report this at https://github.com/transportforcairo/loom_qgis/issues"
        )

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip", prefix="loom_binaries_")
    os.close(tmp_fd)

    try:
        actual = _download_file(url, tmp_path, progress_cb)
        if actual != expected:
            raise RuntimeError(
                "The downloaded LOOM binaries failed the integrity check "
                "(SHA-256 mismatch), so they were not installed.\n\n"
                f"File:     {name} ({BINARIES_REF})\n"
                f"Expected: {expected}\n"
                f"Got:      {actual}\n\n"
                "Please retry; if it keeps failing, report it at "
                "https://github.com/transportforcairo/loom_qgis/issues"
            )

        if progress_cb:
            progress_cb(0, None, "Extracting…")

        target = bin_dir()
        _clear_dir(target)
        _extract_zip(tmp_path, target)
        with open(os.path.join(target, _REF_MARKER), "w", encoding="utf-8") as fh:
            fh.write(BINARIES_REF + "\n")

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if progress_cb:
        progress_cb(1, 1, f"Done — binaries installed to {bin_dir()}")

    return bin_dir()
