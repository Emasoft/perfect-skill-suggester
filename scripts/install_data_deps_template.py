#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Runtime installer for plugin `data_dir` dependencies.

This is the **static template** generated plugins ship as
`<plugin-root>/scripts/install-data-deps.py`. It is invoked from a
SessionStart hook in the generated plugin's `hooks/hooks.json`.

Design rule: this script has ZERO attacker-controlled interpolation.
Every external input is read from `${CLAUDE_PLUGIN_ROOT}/scripts/data-deps.json`,
validated against a strict shape, and passed to `subprocess.run` as a
list of arguments with `shell=False`. Shell injection is structurally
impossible — the prior bash-template approach (PSS v3.5.0 and earlier)
interpolated url/dest/sha256/npm/pip/rust_cargo into shell-quoted strings,
which a malicious `.agent.toml` could weaponise into RCE at every
SessionStart.

Contract for `data-deps.json`:
    {
      "npm":         "<relative-path-to-package.json>",        // optional
      "pip":         "<relative-path-to-requirements.txt>",    // optional
      "rust_cargo":  "<relative-path-to-Cargo.toml>",          // optional
      "downloads": [                                            // optional
        {
          "url":    "https://...",   // http(s) only
          "sha256": "<64 hex chars>",
          "dest":   "<relative-path-under-CLAUDE_PLUGIN_DATA>"
        },
        ...
      ]
    }

All paths must be relative and may not contain `..` segments. URLs must
use http(s) only. SHA-256 must be exactly 64 lowercase hex characters
(checked case-insensitively). Any validation failure aborts the install
with a non-zero exit — fail-fast per project rule.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

_SHA256_HEX_LEN = 64
_SHA256_ALPHABET = frozenset("0123456789abcdefABCDEF")
_DOWNLOAD_TIMEOUT_SECONDS = 120


def _safe_relpath(value: Any, field: str) -> Path:
    """Reject absolute paths, empty strings, non-strings, and `..` segments."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field}: must be a non-empty string, got {value!r}")
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError(f"{field}: must be a relative path, got absolute {value!r}")
    parts = candidate.parts
    if not parts:
        raise ValueError(f"{field}: empty path")
    if any(part == ".." for part in parts):
        raise ValueError(f"{field}: '..' segment forbidden in {value!r}")
    return candidate


_URL_FORBIDDEN_CHARS = set(' \t\r\n\v\f\'"`;()|&$<>{}[]^*?')


def _validate_https_url(url: Any) -> str:
    if not isinstance(url, str) or not url:
        raise ValueError(f"url: must be a non-empty string, got {url!r}")
    # Reject whitespace, quotes, shell metachars, and control chars. The
    # generator already rejects these at generate time; this is defense in
    # depth in case a tampered data-deps.json slips through.
    if any(ch in _URL_FORBIDDEN_CHARS or ord(ch) < 0x20 for ch in url):
        raise ValueError(
            f"url: contains forbidden character (whitespace/quote/shell-meta/control): {url!r}"
        )
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"url: scheme must be http or https, got {parsed.scheme!r} in {url!r}"
        )
    if not parsed.netloc:
        raise ValueError(f"url: missing host in {url!r}")
    return url


def _validate_sha256(value: Any) -> str:
    if not isinstance(value, str) or len(value) != _SHA256_HEX_LEN:
        raise ValueError(
            f"sha256: must be {_SHA256_HEX_LEN} hex characters, got {value!r}"
        )
    if not all(ch in _SHA256_ALPHABET for ch in value):
        raise ValueError(f"sha256: must be hex, got {value!r}")
    return value.lower()


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _install_npm(root: Path, data: Path, rel: Any) -> None:
    src_path = root / _safe_relpath(rel, "data_dir.npm")
    if not src_path.exists():
        return
    cache = data / src_path.name
    src_bytes = src_path.read_bytes()
    if cache.exists() and cache.read_bytes() == src_bytes:
        return
    data.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(src_bytes)
    try:
        subprocess.run(
            ["npm", "install", "--silent"],
            cwd=str(data),
            check=True,
            shell=False,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        cache.unlink(missing_ok=True)
        raise


def _install_pip(root: Path, data: Path, rel: Any) -> None:
    src_path = root / _safe_relpath(rel, "data_dir.pip")
    if not src_path.exists():
        return
    cache = data / src_path.name
    src_bytes = src_path.read_bytes()
    if cache.exists() and cache.read_bytes() == src_bytes:
        return
    data.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(src_bytes)
    venv = data / ".venv"
    if not venv.exists():
        subprocess.run(
            ["uv", "venv", "--python", "3.12", str(venv)],
            check=True,
            shell=False,
        )
    try:
        subprocess.run(
            [
                "uv", "pip", "install",
                "--python", str(venv / "bin" / "python"),
                "-r", str(cache),
                "--quiet",
            ],
            check=True,
            shell=False,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        cache.unlink(missing_ok=True)
        raise


def _install_cargo(root: Path, data: Path, rel: Any) -> None:
    src_path = root / _safe_relpath(rel, "data_dir.rust_cargo")
    if not src_path.exists():
        return
    cache = data / src_path.name
    src_bytes = src_path.read_bytes()
    if cache.exists() and cache.read_bytes() == src_bytes:
        return
    (data / "bin").mkdir(parents=True, exist_ok=True)
    cache.write_bytes(src_bytes)
    cargo_dir = src_path.parent
    target_dir = data / "target"
    try:
        subprocess.run(
            ["cargo", "build", "--release", "--target-dir", str(target_dir)],
            cwd=str(cargo_dir),
            check=True,
            shell=False,
        )
        release_dir = target_dir / "release"
        if release_dir.is_dir():
            for built in release_dir.iterdir():
                if built.is_file() and os.access(built, os.X_OK):
                    shutil.copy2(built, data / "bin" / built.name)
    except (subprocess.CalledProcessError, FileNotFoundError):
        cache.unlink(missing_ok=True)
        raise


def _process_download(data: Path, spec: dict[str, Any]) -> None:
    url = _validate_https_url(spec.get("url"))
    expected_sha = _validate_sha256(spec.get("sha256"))
    dest_path = data / _safe_relpath(spec.get("dest"), "downloads[].dest")
    if dest_path.exists() and _sha256_of_file(dest_path).lower() == expected_sha:
        return
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".tmp")
    try:
        # nosec B310 — scheme is whitelisted by _validate_https_url above.
        with (
            urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response,  # noqa: S310
            tmp_path.open("wb") as out_fp,
        ):
            shutil.copyfileobj(response, out_fp)
        actual_sha = _sha256_of_file(tmp_path).lower()
        if actual_sha != expected_sha:
            raise ValueError(
                f"sha256 mismatch for {url}: expected {expected_sha}, got {actual_sha}"
            )
        tmp_path.replace(dest_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        # Do NOT unlink dest_path on failure — it may be a pre-existing good copy
        # whose sha256 was correct but transient verification raced. _sha256_of_file
        # at top short-circuits the re-download path in that case.
        raise


def main() -> int:
    root_env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    data_env = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not root_env or not data_env:
        # CC didn't set the expected env vars — silently no-op so the hook
        # doesn't break sessions where the plugin is dormant.
        return 0
    root = Path(root_env)
    data = Path(data_env)
    spec_path = root / "scripts" / "data-deps.json"
    if not spec_path.exists():
        return 0
    raw = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"data-deps.json: top-level must be an object, got {type(raw).__name__}")

    if isinstance(raw.get("npm"), str):
        _install_npm(root, data, raw["npm"])
    if isinstance(raw.get("pip"), str):
        _install_pip(root, data, raw["pip"])
    if isinstance(raw.get("rust_cargo"), str):
        _install_cargo(root, data, raw["rust_cargo"])
    downloads = raw.get("downloads")
    if isinstance(downloads, list):
        for entry in downloads:
            if not isinstance(entry, dict):
                raise ValueError(f"downloads[] entry must be an object, got {type(entry).__name__}")
            _process_download(data, entry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
