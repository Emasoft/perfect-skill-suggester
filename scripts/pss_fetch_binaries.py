#!/usr/bin/env python3
"""Fetch this platform's PSS native binaries from the GitHub release (TRDD-YC51I1C0 phase 2).

Downloads ONLY the two binaries this machine can execute (`pss-<os>-<arch>` and
`pss-nlp-<os>-<arch>`) and verifies each against the sha256 recorded in the
git-tracked `bin/manifest.json`.

Why the checksum comes from git and not from the download: publishing a binary
next to its own `.sha256` on the same server proves the bytes survived transit
and nothing more — whoever can replace the asset can replace the checksum. The
manifest instead arrives through the plugin clone the user already trusted by
installing it, so a tampered release asset fails against the repo.

The store is content-addressed, so two plugin versions whose engine did not
change share one copy on disk:

    <data-dir>/bin/<sha256[:16]>/<name>      the artifact
    <data-dir>/bin/current/<name>            what the resolvers look at
    <data-dir>/bin/.fetch.lock               writers only, never readers
    <data-dir>/bin/.state.json               why the last attempt ended how it did

FAIL-FAST and FAIL-CLOSED. A blocked or corrupted download exits non-zero,
prints the offline remedies, and leaves NOTHING behind — no partial file, no
half-published `current/`. A silent degradation here would surface much later
as "PSS stopped suggesting things", with nothing to read.

This script is never on the hot path. `bin/pss-hook-dispatch.sh` may only stat
the store; see the TRDD's §3.4 table for which surface may fetch and which
may not.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover — Windows has no fcntl
    # A BARE `import fcntl` here would crash at import time on the one platform
    # whose binary this script exists to fetch. Windows loses only the
    # writer-serialization lock, which costs a redundant download in the rare
    # case of two concurrent fetches — never a corrupt install, because the
    # verify-then-`os.replace` below is what makes a store entry trustworthy,
    # not the lock. Same guard every other fcntl user in scripts/ already uses.
    fcntl = None  # type: ignore[assignment]

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pss_paths import detect_platform, get_data_dir  # noqa: E402

REPO = "Emasoft/perfect-skill-suggester"
DOWNLOAD_BASE = f"https://github.com/{REPO}/releases/download"
# Three attempts, then stop. A corporate proxy that refuses the connection
# refuses it just as firmly on the twentieth try, and an unbounded retry loop
# turns a clear failure into a hang the user cannot diagnose.
ATTEMPTS = 3
BACKOFF_SECONDS = 2
CHUNK = 1024 * 1024


class ChecksumMismatch(Exception):
    """Downloaded bytes did not match the manifest. Never a BaseException."""


def _plugin_root() -> Path:
    """Where the tracked `bin/` lives — the plugin install, else this repo."""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if env and Path(env).is_absolute():
        return Path(env)
    return Path(__file__).resolve().parent.parent


def store_dir() -> Path:
    return get_data_dir() / "bin"


def load_manifest() -> dict:
    """Read the git-tracked manifest, or fail loudly saying which path was tried.

    A missing manifest is not recoverable by guessing: without it there is no
    trusted sha to verify against, and installing an unverified binary is the
    exact thing this design exists to prevent.
    """
    path = _plugin_root() / "bin" / "manifest.json"
    if not path.exists():
        raise SystemExit(
            f"PSS: no binary manifest at {path}.\n"
            "  The manifest ships with the plugin and carries the checksums "
            "every download is verified against.\n"
            "  A plugin install without it is incomplete — reinstall the plugin."
        )
    data = json.loads(path.read_text())
    if not isinstance(data.get("binaries"), dict) or not data.get("release_tag"):
        raise SystemExit(f"PSS: malformed binary manifest at {path}.")
    return data


def needed_names() -> list[str]:
    """The two binaries THIS machine can execute — never all ten.

    Downloading the full set would move ~160 MiB to run ~30 MiB of it; §1.2 of
    the TRDD measures that at 78-82% dead weight on every platform.
    """
    pss = detect_platform()
    return [pss, pss.replace("pss-", "pss-nlp-", 1)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_state(status: str, **fields: object) -> None:
    """Record why the last attempt ended how it did.

    The hot-path shim stays graceful — missing binary means empty hook JSON and
    exit 0, because breaking a user's session is never the right answer. But
    graceful with no signal is how a broken install stays broken silently, so
    the reason lands here and `/pss-status` renders it.
    """
    state = {"status": status, "attempted_at": int(time.time()), **fields}
    d = store_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / ".state.json.tmp"
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    tmp.replace(d / ".state.json")


def _download_verified(url: str, expected_sha: str, dest: Path) -> None:
    """Download to a `.part`, verify, and only then put it in place.

    Verify-then-rename is the whole contract: a file that exists in the store
    has already matched its manifest sha, so a reader never has to re-check and
    a crash mid-download cannot leave something that looks installed.
    """
    part = dest.with_suffix(dest.suffix + ".part")
    last_error = ""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
                with part.open("wb") as fh:
                    shutil.copyfileobj(response, fh, CHUNK)
            actual = _sha256(part)
            if actual != expected_sha:
                part.unlink(missing_ok=True)
                # A plain exception, NEVER SystemExit: SystemExit derives from
                # BaseException, so it would sail past this function's own
                # `except` clauses AND fetch()'s, leaving `.state.json` holding
                # whatever the LAST run wrote — `{"status": "ok"}` after a
                # previously good fetch. /pss-status would then report a healthy
                # engine immediately after a TAMPERED download: silent
                # degradation in the one path the git-shipped checksum exists to
                # defend. The caller turns this into a recorded failure.
                raise ChecksumMismatch(
                    f"checksum mismatch for {dest.name}\n"
                    f"  expected {expected_sha}\n  got      {actual}\n"
                    f"  from     {url}"
                )
            part.replace(dest)
            return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
            part.unlink(missing_ok=True)
            if attempt < ATTEMPTS:
                time.sleep(BACKOFF_SECONDS * attempt)
    raise ConnectionError(last_error)


def _publish_current(store: Path, sha: str, name: str) -> None:
    """Point `current/<name>` at the content-addressed copy.

    Symlink where possible, copy where not: unprivileged Windows refuses
    symlink creation, and a plugin that only works for administrators is not
    shipped. Both shapes satisfy the resolvers, which stat a path.
    """
    current = store / "current"
    current.mkdir(parents=True, exist_ok=True)
    target = store / sha[:16] / name
    link = current / name
    if link.exists() or link.is_symlink():
        link.unlink()
    try:
        link.symlink_to(target)
    except OSError:
        shutil.copy2(target, link)
    link.chmod(0o755)


def fetch(offline_tarball: Path | None = None) -> int:
    manifest = load_manifest()
    tag = manifest["release_tag"]
    store = store_dir()
    store.mkdir(parents=True, exist_ok=True)

    # Writers serialize on their own lock file. Readers (the hot path) never
    # touch it — a fetch in progress must never be able to block a suggestion.
    lock_path = store / ".fetch.lock"
    # Opened "a", not "w": "w" truncates on open, and truncating a file another
    # process is holding the lock on is a pointless write against a live lock.
    # Append never modifies a byte and still creates the file.
    with lock_path.open("a") as lock_fh:
        if fcntl is not None:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
        try:
            names = needed_names()
        except RuntimeError as exc:
            write_state("unsupported-platform", reason=str(exc))
            print(f"PSS: {exc}", file=sys.stderr)
            return 1

        missing = [n for n in names if n not in manifest["binaries"]]
        if missing:
            reason = f"manifest has no entry for {', '.join(missing)}"
            write_state("manifest-incomplete", reason=reason)
            print(f"PSS: {reason} — refusing to install unverifiable bytes.", file=sys.stderr)
            return 1

        staged: Path | None = None
        if offline_tarball is not None:
            if not offline_tarball.exists():
                write_state("offline-missing", reason=str(offline_tarball))
                print(f"PSS: no such tarball: {offline_tarball}", file=sys.stderr)
                return 1
            staged = Path(tempfile.mkdtemp(prefix="pss-offline-"))
            with tarfile.open(offline_tarball) as tf:
                # Flat archive by construction (publish.py writes arcname=name);
                # extract only the two members this platform needs.
                for name in names:
                    try:
                        member = tf.extractfile(name)
                    except KeyError:
                        # An absent member RAISES; it does not return None. A
                        # `is None` guard alone therefore turns a truncated
                        # bundle into an uncaught traceback instead of the
                        # actionable refusal below — the loud-but-useless
                        # failure this whole path exists to avoid.
                        continue
                    if member is None:
                        continue  # a directory or other non-regular entry
                    (staged / name).write_bytes(member.read())

        # ALL binaries are obtained and verified BEFORE any of them is published
        # to `current/`. Publishing inside the loop meant a bundle carrying the
        # engine but not its nlp sibling installed the engine, then failed —
        # exit 1 with a half-installed store, contradicting the "installs
        # nothing" contract this whole path advertises. Resolve first, publish
        # last: `current/` then flips only on a run that obtained everything.
        resolved: list[tuple[str, str]] = []
        try:
            for name in names:
                expected = manifest["binaries"][name]["sha256"]
                dest_dir = store / expected[:16]
                dest = dest_dir / name
                if dest.exists() and _sha256(dest) == expected:
                    # Already in the store from an earlier version whose engine
                    # was identical — this is the "unchanged engine costs
                    # nothing" property, and it needs no network at all.
                    resolved.append((expected, name))
                    continue
                dest_dir.mkdir(parents=True, exist_ok=True)
                if staged is not None:
                    src = staged / name
                    if not src.exists():
                        write_state("offline-incomplete", reason=f"{name} not in tarball")
                        print(f"PSS: {name} missing from the offline tarball.", file=sys.stderr)
                        return 1
                    actual = _sha256(src)
                    if actual != expected:
                        write_state("checksum-mismatch", reason=name)
                        print(
                            f"PSS: checksum mismatch for {name} in the offline "
                            f"tarball.\n  expected {expected}\n  got      {actual}",
                            file=sys.stderr,
                        )
                        return 1
                    src.replace(dest)
                else:
                    url = f"{DOWNLOAD_BASE}/{tag}/{name}"
                    try:
                        _download_verified(url, expected, dest)
                    except ConnectionError as exc:
                        write_state("network-blocked", reason=str(exc), url=url)
                        print(_blocked_message(name, url, str(exc), tag), file=sys.stderr)
                        return 1
                    except ChecksumMismatch as exc:
                        write_state("checksum-mismatch", reason=str(exc), url=url)
                        print(f"PSS: {exc}\n  Refusing to install.", file=sys.stderr)
                        return 1
                dest.chmod(0o755)
                resolved.append((expected, name))
        finally:
            if staged is not None:
                shutil.rmtree(staged, ignore_errors=True)

        for expected, name in resolved:
            _publish_current(store, expected, name)

    write_state("ok", release_tag=tag, binaries=names)
    print(f"PSS: engine ready ({', '.join(names)}) from {tag}.")
    return 0


def _blocked_message(name: str, url: str, error: str, tag: str) -> str:
    """The remedy belongs in the failure, not in documentation nobody reaches."""
    version = tag.lstrip("v")
    return (
        f"\nPSS: cannot obtain the native engine ({name}).\n\n"
        f"  tried:  {url}\n"
        f"  result: {error} after {ATTEMPTS} attempts (proxy/firewall?)\n\n"
        "  offline install:\n"
        "    1) on a networked machine:\n"
        f"         gh release download {tag} -R {REPO} \\\n"
        f"            -p 'pss-binaries-{version}.tar.gz'\n"
        "    2) copy it over, then:\n"
        "         uv run python scripts/pss_fetch_binaries.py --offline "
        f"pss-binaries-{version}.tar.gz\n"
        "  or point PSS at a directory you populate yourself:\n"
        "         export PSS_BINARY_DIR=/opt/pss/bin\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        metavar="TARBALL",
        type=Path,
        help="install from a pss-binaries-<version>.tar.gz instead of downloading",
    )
    args = parser.parse_args()
    return fetch(args.offline)


if __name__ == "__main__":
    sys.exit(main())
