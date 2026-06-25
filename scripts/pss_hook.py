#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pycozo[embedded]>=0.7.6",
# ]
# ///
"""
PSS Hook Script - Multiplatform binary caller for Perfect Skill Suggester.

Invocation contract (v3.1.1+): hooks/hooks.json invokes this via `uv run`.
The PEP 723 inline script metadata block above declares pycozo as a
required dependency. uv provisions and caches a venv with pycozo installed
on first invocation (~2-5s cold) and reuses it from the cache on every
subsequent call (~50-100ms). Cross-platform: uv handles the Windows/Unix
venv path split internally, so hooks/hooks.json is identical on every OS.
The user-facing requirement is just `uv` on PATH — see README.md.

Thin Python wrapper that:
1. Reads hook JSON from stdin
2. Skips trivial prompts (slash commands, confirmations)
3. Prepends the previous user message for conversational context
4. Invokes the Rust binary which handles ALL heavy lifting:
   - Project detection (scan_project_context)
   - Domain classification (detect_domains_from_prompt_with_context)
   - Tool/framework/language matching (scoring loop)
   - File type detection (scan_root_file_types)
5. Outputs the binary's hook-formatted result
"""

import contextlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

try:
    import fcntl as _fcntl  # POSIX only
except ImportError:  # pragma: no cover — Windows has no fcntl
    _fcntl = None  # type: ignore[assignment]

# Configuration
MAX_SUGGESTIONS = 5  # Maximum skill suggestions per message (one line each)
MIN_SCORE = 0.5  # Minimum score threshold
SUBPROCESS_TIMEOUT = (
    8  # Binary timeout in seconds (hooks.json timeout is 10s; keep this < 10)
)
SKILL_INDEX_FILE = "skill-index.json"
# Hook-side coordination with pss_cozodb writers. Writers take fcntl.LOCK_EX
# on get_db_lock_path() before opening CozoDB for write. Without a matching
# reader-side LOCK_SH the Rust binary can hit a half-committed SQLite file
# and cozo-ce panics with `database is locked` (SIGABRT, exit code -6).
# v3.4.2+: acquire LOCK_SH around the binary subprocess call; retry once on
# -6 with a short backoff if the lock didn't fully prevent a race (e.g.
# another process opening the DB without going through our writer path).
DB_LOCK_ACQUIRE_TIMEOUT = 4.0  # Max seconds to wait for the reader lock
DB_LOCK_POLL_INTERVAL = 0.05    # Sleep between non-blocking acquire attempts
DB_RETRY_DELAY = 0.2            # Backoff before the single retry on SIGABRT
# Prompt length cap for the Rust binary — the scorer only needs the first few
# thousand chars to determine intent.  Piping 100KB+ prompts causes timeouts
# (JSON parse + tokenization + scoring can't finish in 4s on huge inputs).
MAX_PROMPT_CHARS = 4000


_debug_mode_cache: bool | None = None


@contextlib.contextmanager
def _db_shared_lock() -> Iterator[None]:
    """Acquire fcntl.LOCK_SH on pss-skill-index.db.lock for the duration of
    the binary subprocess call. Compatible with pss_cozodb writers (LOCK_EX).

    On non-POSIX (Windows, where fcntl is unavailable) this is a no-op; the
    binary call proceeds without coordination and falls back to the
    retry-on-SIGABRT path below if cozo races on the SQLite file.

    Uses non-blocking acquire + bounded poll (DB_LOCK_ACQUIRE_TIMEOUT). If
    we can't acquire the shared lock in time (writer is holding LOCK_EX
    for a very long merge), we yield anyway — the retry-on-SIGABRT path
    handles the residual race. Better to attempt the binary call and
    surface a real error than to silently swallow the hook.

    HP-4 (audit 20260514): the hot path is intentionally "best-effort
    under contention." If the writer holds LOCK_EX for >4 s, we let the
    binary call proceed without the shared lock and rely on the writer's
    new staging-file + atomic-rename design (v3.5.0+) to keep readers
    safe. Empirically a hot-path call that times out on the shared lock
    happens once or twice during a full /pss-reindex-skills cycle and
    the SIGABRT retry below absorbs it transparently. This is a
    documented carve-out from CLAUDE.md's fail-fast rule — fail-fast
    here would mean dropping suggestion output on every reindex, which
    is worse for the user than the rare retry.
    """
    if _fcntl is None:
        yield
        return

    try:
        from pss_paths import get_db_lock_path

        lock_path = get_db_lock_path()
    except Exception:
        # Path resolution failed (very early in cache install, etc.) — skip
        # locking and let the binary call proceed.
        yield
        return

    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        yield
        return

    lock_fd = None
    try:
        lock_fd = open(lock_path, "w")  # noqa: SIM115
    except OSError:
        yield
        return

    deadline = time.monotonic() + DB_LOCK_ACQUIRE_TIMEOUT
    acquired = False
    try:
        while True:
            try:
                _fcntl.flock(lock_fd.fileno(), _fcntl.LOCK_SH | _fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    break
                time.sleep(DB_LOCK_POLL_INTERVAL)
        yield
    finally:
        try:
            if acquired:
                _fcntl.flock(lock_fd.fileno(), _fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            lock_fd.close()
        except OSError:
            pass


def _is_debug_mode() -> bool:
    """Check if Claude Code is running with --debug by walking the process tree.

    Matches only the actual 'claude' binary (not paths containing '.claude').
    Adapted from token-reporter-plugin. Result is cached for the process lifetime.
    """
    global _debug_mode_cache
    if _debug_mode_cache is not None:
        return _debug_mode_cache
    # ps command is Unix-only — skip on Windows
    if platform.system() == "Windows":
        _debug_mode_cache = False
        return False
    pid = os.getppid()
    while pid > 1:
        try:
            result = subprocess.run(
                ["ps", "-o", "args=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=2,
            )
            cmdline = result.stdout.strip()
            args = cmdline.split()
            if args:
                # Check the binary is actually 'claude' (not just a path with .claude)
                cmd = os.path.basename(args[0])
                if cmd == "claude" and "--debug" in args:
                    _debug_mode_cache = True
                    return True
            # Walk up to this process's parent
            result = subprocess.run(
                ["ps", "-o", "ppid=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=2,
            )
            pid = int(result.stdout.strip())
        except (subprocess.TimeoutExpired, ValueError, OSError):
            break
    _debug_mode_cache = False
    return False


def _get_cache_dir() -> Path:
    """Get the PSS cache directory."""
    from pss_paths import get_cache_dir

    return get_cache_dir()


# Prompts to skip (slash commands and simple responses don't need skill suggestions)
SKIP_PREFIXES = (
    "/",  # Slash commands like /plugin, /help, /exit
    "<command-name>/",  # Command tags from Claude Code
)

SKIP_SIMPLE_PROMPTS = {
    # Single words - confirmations and acknowledgments only
    "continue",
    "yes",
    "no",
    "ok",
    "okay",
    "thanks",
    "sure",
    "done",
    "stop",
    "y",
    "n",
    "yep",
    "nope",
    "thx",
    "ty",
    "next",
    "go",
    "proceed",
    "k",
    "yea",
    "yeah",
    "nah",
    "good",
    "great",
    "perfect",
    "fine",
    "cool",
    "nice",
    # Two-word phrases
    "got it",
    "thank you",
    "thanks!",
    "ok thanks",
    "okay thanks",
    "sounds good",
    "go ahead",
    "do it",
    "looks good",
    "that works",
    "yes please",
    "no thanks",
    "i see",
    "i understand",
    "makes sense",
    "all good",
    "thank you!",
}


def _extract_user_text(entry: dict) -> str:
    """Extract user message text from a parsed JSONL transcript entry."""
    msg = entry.get("message")
    if not isinstance(msg, dict):
        return ""
    role = msg.get("role", "")
    if role not in ("human", "user"):
        return ""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts).strip()
    return ""


def extract_previous_user_message(transcript_path: str) -> str:
    """Extract the PREVIOUS user message from the transcript (not the current one).

    The hook fires on UserPromptSubmit, so the current message is already in the
    transcript. We skip the first (most recent) user message and return the second
    one — that's the actual previous message the user typed before this prompt.

    Delegates to the Rust binary's --extract-prev-msg which uses mmap + backward
    scan (zero-copy, no memory limit, ~3ms on 500MB files).  Falls back to a
    Python seek-based reader if the binary is not available.
    """
    if not transcript_path:
        return ""
    if not Path(transcript_path).exists():
        return ""

    # Try Rust binary first — mmap is ~5x faster and has no scan-distance limit
    try:
        binary_path = find_binary()
        result = subprocess.run(
            [str(binary_path), "--extract-prev-msg", transcript_path],
            capture_output=True,
            text=True,
            timeout=2,  # 2s timeout (mmap scan is <30ms, but account for startup)
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired, OSError):
        pass  # Fall through to Python fallback

    # Python fallback: seek-based backward reader with 8KB blocks + 512B peek
    return _extract_prev_msg_python(transcript_path)


def _extract_prev_msg_python(transcript_path: str) -> str:
    """Python fallback for extract_previous_user_message.

    Seek-based backwards reader — scans 8KB blocks for newline positions, then
    peeks at each line start (512 bytes) to pre-filter before reading.  Multi-MB
    assistant/image lines are NEVER loaded into memory.
    """
    import time

    transcript_file = Path(transcript_path)
    deadline = time.monotonic() + 0.8

    BLOCK = 8192
    PEEK = 512
    MAX_SCAN = 32 * 1024 * 1024

    try:
        file_size = transcript_file.stat().st_size
    except OSError:
        return ""

    if file_size == 0:
        return ""

    user_messages_found = 0
    bytes_scanned = 0

    with open(transcript_file, "rb") as f:
        line_end = file_size
        scan_pos = file_size

        while scan_pos > 0 and bytes_scanned < MAX_SCAN:
            if time.monotonic() > deadline:
                return ""

            block_start = max(0, scan_pos - BLOCK)
            block_len = scan_pos - block_start
            f.seek(block_start)
            block = f.read(block_len)
            bytes_scanned += block_len

            search_end = block_len
            while True:
                nl = block.rfind(b"\n", 0, search_end)
                if nl < 0:
                    break

                abs_nl = block_start + nl
                line_start = abs_nl + 1
                line_len = line_end - line_start

                if line_len >= 20:
                    peek_len = min(PEEK, line_len)
                    f.seek(line_start)
                    peek = f.read(peek_len)

                    if b'"human"' in peek or b'"user"' in peek:
                        # Skip tool-result messages (v2.1.85+): auto-generated
                        # by tool execution, not user-typed prompts
                        if b'"toolUseResult"' in peek or b'"sourceToolAssistantUUID"' in peek:
                            line_end = abs_nl
                            search_end = nl
                            continue

                        if time.monotonic() > deadline:
                            return ""

                        if line_len > peek_len:
                            f.seek(line_start)
                            full_line = f.read(line_len)
                        else:
                            full_line = peek

                        try:
                            entry = json.loads(full_line)
                        except (json.JSONDecodeError, ValueError):
                            line_end = abs_nl
                            search_end = nl
                            continue
                        if "message" not in entry:
                            line_end = abs_nl
                            search_end = nl
                            continue
                        # Belt-and-suspenders: skip tool-result entries even if
                        # the peek pre-filter missed (field past byte 512)
                        if "toolUseResult" in entry or "sourceToolAssistantUUID" in entry:
                            line_end = abs_nl
                            search_end = nl
                            continue
                        user_text = _extract_user_text(entry)
                        if user_text:
                            user_messages_found += 1
                            if user_messages_found >= 2:
                                return (
                                    user_text[:MAX_PROMPT_CHARS]
                                    if len(user_text) > MAX_PROMPT_CHARS
                                    else user_text
                                )

                line_end = abs_nl
                search_end = nl

            scan_pos = block_start

        if scan_pos == 0 and line_end > 20:
            f.seek(0)
            peek = f.read(min(PEEK, line_end))
            if b'"human"' in peek or b'"user"' in peek:
                # Skip tool-result messages (v2.1.85+)
                if b'"toolUseResult"' in peek or b'"sourceToolAssistantUUID"' in peek:
                    pass
                else:
                    if line_end > len(peek):
                        f.seek(0)
                        full_line = f.read(line_end)
                    else:
                        full_line = peek
                    try:
                        entry = json.loads(full_line)
                        # Skip tool-result entries (field past byte 512)
                        if "toolUseResult" not in entry and "sourceToolAssistantUUID" not in entry:
                            user_text = _extract_user_text(entry)
                            if user_text:
                                user_messages_found += 1
                                if user_messages_found >= 2:
                                    return (
                                        user_text[:MAX_PROMPT_CHARS]
                                        if len(user_text) > MAX_PROMPT_CHARS
                                        else user_text
                                    )
                    except (json.JSONDecodeError, ValueError):
                        pass

    return ""


def augment_prompt_with_context(prompt: str, transcript_path: str) -> str:
    """Concatenate previous user message + current prompt for full intent.

    The result is capped at MAX_PROMPT_CHARS because the Rust binary only needs
    the first few thousand chars for intent/keyword extraction.  Piping 100KB+
    through subprocess stdin → JSON parse → tokenize → score blows the 4s timeout.

    Previous message is ONLY prepended when the current prompt is too short to
    carry clear intent on its own (<30 non-trivial chars).  Longer prompts like
    "developing a software with bun" have enough signal; prepending unrelated
    previous messages (e.g. "bump and publish") pollutes scoring with generic
    keywords that outweigh the specific intent.
    """
    prompt_stripped = prompt.strip()

    # Cap current prompt first — if it's already huge, prev_msg won't help
    if len(prompt_stripped) > MAX_PROMPT_CHARS:
        prompt_stripped = prompt_stripped[:MAX_PROMPT_CHARS]

    # Only augment with previous message when current prompt is too short
    # to carry clear intent.  Count non-trivial chars (letters/digits only).
    non_trivial = sum(1 for c in prompt_stripped if c.isalnum())
    if non_trivial >= 30:
        # Current prompt has enough signal — don't pollute with previous message
        return prompt_stripped

    prev_msg = extract_previous_user_message(transcript_path)
    if prev_msg:
        # Cap prev_msg so total stays under MAX_PROMPT_CHARS
        budget = MAX_PROMPT_CHARS - len(prompt_stripped) - 1  # -1 for space separator
        if budget > 200:
            prev_msg = prev_msg[:budget]
            return f"{prev_msg} {prompt_stripped}"

    return prompt_stripped


def _strip_system_reminders(text: str) -> str:
    """Remove <system-reminder>...</system-reminder> blocks using str.find().

    O(n) with no regex backtracking — critical for 200KB+ prompts where
    re.sub with re.DOTALL causes >1s overhead.
    """
    open_tag = "<system-reminder>"
    close_tag = "</system-reminder>"
    open_len = len(open_tag)
    close_len = len(close_tag)

    parts: list[str] = []
    pos = 0
    while pos < len(text):
        start = text.find(open_tag, pos)
        if start == -1:
            parts.append(text[pos:])
            break
        if start > pos:
            parts.append(text[pos:start])
        end = text.find(close_tag, start + open_len)
        if end == -1:
            break  # Unclosed tag — discard rest (contains system content)
        pos = end + close_len
    return "".join(parts).strip()


def should_skip_prompt(prompt: str) -> bool:
    """Check if this prompt should skip skill suggestion."""
    if not prompt:
        return True

    prompt_stripped = prompt.strip()
    prompt_lower = prompt_stripped.lower()

    # Skip slash commands
    for prefix in SKIP_PREFIXES:
        if prompt_stripped.startswith(prefix):
            return True

    # Skip simple one-word responses
    if prompt_lower in SKIP_SIMPLE_PROMPTS:
        return True

    # Skip system-generated prompts (task notifications, session continuations,
    # hook outputs, release notes, local commands).
    # NOTE: system-reminder blocks are already stripped before this function is
    # called, so we only check for other system tags in the clean prompt.
    if "<task-notification>" in prompt_stripped:
        return True
    if "<local-command-caveat>" in prompt_stripped:
        return True
    if "<local-command-stdout>" in prompt_stripped:
        return True
    # Claude Code release notes pasted by /release-notes command
    if prompt_stripped.startswith("Version ") and "\n• " in prompt_stripped[:500]:
        return True

    return False


def detect_platform() -> str:
    """Detect platform and architecture, return binary name.

    Delegates to ``pss_paths.detect_platform()`` — the single Python source of
    truth for the platform→binary mapping (also mirrored by the hot-path shell
    dispatch ``bin/pss-hook-dispatch.sh``). Kept as a thin wrapper so this
    module's ``find_binary()`` and the existing tests keep their call site,
    while the mapping itself lives in exactly one place. The local import
    matches the existing ``from pss_paths import ...`` idiom used elsewhere in
    this PEP 723 script (pss_paths is stdlib-only and sits beside this file).
    """
    from pss_paths import detect_platform as _detect_platform

    return _detect_platform()


def find_binary() -> Path:
    """Locate the PSS binary relative to this script."""
    # This script is in: perfect-skill-suggester/scripts/pss_hook.py
    # Binary is in: perfect-skill-suggester/bin/
    script_dir = Path(__file__).parent.resolve()
    binary_name = detect_platform()
    binary_path = script_dir.parent / "bin" / binary_name

    if not binary_path.exists():
        raise FileNotFoundError(
            f"PSS binary not found at: {binary_path}. Build it with: uv run python {script_dir / 'pss_build.py'}"
        )

    return binary_path


# Empty hook response — matches Rust binary's HookOutput::empty() format
_EMPTY_HOOK_OUTPUT = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
    }
}


def _exit_empty() -> None:
    """Exit with valid empty hook output — no suggestions, no error."""
    print(json.dumps(_EMPTY_HOOK_OUTPUT))
    sys.exit(0)


def _exit_warning(msg: str) -> None:
    """Exit with warning as systemMessage (visible to user) and empty hook output."""
    output: dict[str, Any] = dict(_EMPTY_HOOK_OUTPUT)
    output["systemMessage"] = f"\033[0;33m⚡ PSS: {msg}\033[0m"
    print(json.dumps(output))
    sys.exit(0)


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        # os.kill(pid, 0) doesn't work on Windows — use tasklist
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            return str(pid) in result.stdout
        except (OSError, subprocess.TimeoutExpired):
            return False
    try:
        os.kill(pid, 0)  # Signal 0 = existence check, no actual signal sent
        return True
    except OSError:
        return False


def _maybe_auto_reindex(index_path: Path) -> None:
    """Auto-spawn a background reindex if no index exists, with PID lockfile guard.

    In Phase C (v3.0.0), the trigger condition moved from "JSON missing" to
    "CozoDB missing-or-empty". The `index_path` arg is kept because the PID
    lockfile has historically lived next to the legacy index path
    (`.reindex.pid`) — we still colocate it there to preserve cleanup
    semantics for users upgrading from <v3.0.0 (any stale lockfiles from a
    crashed pre-v3 reindex get detected by the dead-PID branch below).

    - First call: spawns reindex, writes PID lockfile, notifies user
    - Subsequent calls while reindex runs: detects live PID, just notifies
    - After crash: detects dead PID, cleans up stale files, respawns

    HP-5 (audit 20260514): if the reindex script crashes hard (SIGSEGV,
    OOM, syntax error) it will never write its PID into the lockfile,
    and the dead-PID branch will respawn it on the next prompt — for
    every prompt — forever. To break this infinite crash loop we record
    each failed attempt in a sibling `.reindex.crashes` file (each line
    is one ISO-8601 timestamp). If 3 crashes happen within a 1-hour
    sliding window we stop respawning and surface a one-line warning
    pointing the user at /pss-reindex-skills so they can run it
    manually and see the actual error.
    """
    lock_path = index_path.with_suffix(".reindex.pid")
    crash_log = index_path.with_suffix(".reindex.crashes")

    # Check if a reindex is already running
    if lock_path.exists():
        try:
            pid = int(lock_path.read_text().strip())
            if _is_pid_alive(pid):
                # Reindex in progress — just notify and exit
                _exit_warning("building skill index… suggestions available shortly")
                return
        except (ValueError, OSError):
            pass
        # PID is dead or lockfile corrupt — record the crash and clean up
        _record_reindex_crash(crash_log)
        lock_path.unlink(missing_ok=True)
        # Clean up any staging/tmp files left by crashed reindex
        for suffix in (".json.tmp", ".staging.json"):
            index_path.with_suffix(suffix).unlink(missing_ok=True)

        # HP-5: bail out if 3+ crashes in the last hour.
        recent = _recent_reindex_crashes(crash_log, window_seconds=3600)
        if len(recent) >= 3:
            _exit_warning(
                "auto-reindex has crashed 3 times in the last hour — "
                "run /pss-reindex-skills manually to see the error"
            )
            return

    # Spawn background reindex
    script_dir = Path(__file__).parent.resolve()
    reindex_script = script_dir / "pss_reindex.py"
    if not reindex_script.exists():
        _exit_warning(
            f"CozoDB index not found and reindex script missing at {reindex_script} — run /pss-reindex-skills manually"
        )
        return

    try:
        proc = subprocess.Popen(
            [sys.executable, str(reindex_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Detach from hook process group
        )
        try:
            # Exclusive create — fails if file already exists (prevents TOCTOU race)
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(proc.pid).encode())
            os.close(fd)
        except FileExistsError:
            # Another hook already started reindex — kill our process
            proc.kill()
            _exit_warning("skill index not found — auto-reindex already in progress")
            return
        _exit_warning(
            "skill index not found — auto-reindex started, suggestions available shortly"
        )
    except OSError as e:
        # OS-level spawn failure also counts as a crash for HP-5.
        _record_reindex_crash(crash_log)
        _exit_warning(f"CozoDB index not found, auto-reindex failed: {e}")


# HP-5 (audit 20260514) — crash-counter helpers for the auto-reindex.
def _record_reindex_crash(crash_log: Path) -> None:
    """Append an ISO-8601 UTC timestamp line to the crash log. Best-effort
    — if the write fails we silently ignore, because the counter is a
    rate-limiter, not a security mechanism, and any IO problem here
    would mean the upstream reindex is also going to fail.
    """
    from datetime import datetime, timezone

    try:
        crash_log.parent.mkdir(parents=True, exist_ok=True)
        with open(crash_log, "a", encoding="utf-8") as f:
            f.write(datetime.now(timezone.utc).isoformat() + "\n")
    except OSError:
        pass


def _recent_reindex_crashes(crash_log: Path, *, window_seconds: int) -> list[str]:
    """Return crash-log lines whose timestamp falls inside the rolling
    `window_seconds` window ending at now. Older entries are pruned
    from the file as a side-effect (so the log doesn't grow unbounded
    over months of usage).
    """
    from datetime import datetime, timedelta, timezone

    if not crash_log.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    keep: list[str] = []
    try:
        with open(crash_log, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ts = datetime.fromisoformat(line)
                except ValueError:
                    continue
                if ts >= cutoff:
                    keep.append(line)
    except OSError:
        return []

    # Best-effort prune of older entries; if the rewrite races we lose
    # at most a couple of recent entries which the next call replaces.
    try:
        with open(crash_log, "w", encoding="utf-8") as f:
            for line in keep:
                f.write(line + "\n")
    except OSError:
        pass
    return keep


def main() -> None:
    """Main entry point - read stdin, call binary, output result."""
    try:
        # Read JSON input from stdin
        # HP-3 (audit 20260514): the 1 MB cap previously truncated silently —
        # json.loads on a cut payload would then raise JSONDecodeError and
        # produce empty hook output with no user-visible warning. We now
        # peek for an additional byte AFTER the cap to detect truncation.
        # If anything is present past the 1 MB mark the payload was clipped;
        # we still proceed (json.loads will raise on the cut, falling
        # through the normal empty-output path) but log a warning so a user
        # debugging "why are my suggestions disappearing on huge prompts"
        # has a trail.
        _STDIN_CAP = 1_048_576
        stdin_data = sys.stdin.read(_STDIN_CAP)
        if len(stdin_data) == _STDIN_CAP:
            try:
                extra = sys.stdin.read(1)
            except Exception:
                extra = ""
            if extra:
                print(
                    f"[pss-hook] WARN: stdin truncated at {_STDIN_CAP} bytes "
                    f"(HP-3 audit-20260514). Suggestions may be missed for "
                    f"this prompt; consider trimming earlier system reminders.",
                    file=sys.stderr,
                )
                stdin_data += extra

        # Parse input to check if we should skip
        input_json: dict[str, Any] = {}
        try:
            input_json = json.loads(stdin_data)
            prompt = input_json.get("prompt", "")
            cwd = input_json.get("cwd", "")
            transcript_path = input_json.get("transcript_path", "")

            # Validate paths are under home dir to prevent path traversal
            home_path = Path.home()
            if cwd:
                try:
                    Path(cwd).resolve().relative_to(home_path)
                except ValueError:
                    cwd = ""
            if transcript_path:
                try:
                    Path(transcript_path).resolve().relative_to(home_path)
                except ValueError:
                    transcript_path = ""
        except json.JSONDecodeError:
            _exit_empty()
            return  # unreachable but satisfies type checker

        # Strip system-reminders FIRST — they can be 200KB+ and must be removed
        # before any string scanning (should_skip_prompt, augmentation, etc.).
        # Using str.find() loop, not regex — regex re.DOTALL on 200KB+ causes >1s.
        clean_prompt = _strip_system_reminders(prompt)
        if not clean_prompt:
            _exit_empty()
            return

        # Skip prompts that don't need skill suggestions (BEFORE any file I/O).
        # Now runs on the clean (small) prompt, not the raw 200KB+ one.
        if should_skip_prompt(clean_prompt):
            _exit_empty()
            return

        # Check that the CozoDB exists and has rows BEFORE doing any expensive
        # work. In Phase C (v3.0.0) CozoDB is the single source of truth — the
        # JSON file is no longer automatically maintained. If the DB is missing
        # or empty, auto-spawn a background reindex and notify the user.
        #
        # Migration safety: if a legacy `skill-index.json` exists but no CozoDB
        # is present (upgrade from <v3.0.0), we still need to bootstrap the DB.
        # The auto-reindex path handles this — pss_reindex.py writes both.
        #
        # The `index_path` is passed to _maybe_auto_reindex only so it can name
        # the PID lockfile consistently with prior releases; it is NOT read.
        index_path = _get_cache_dir() / SKILL_INDEX_FILE
        try:
            from pss_cozodb import (  # type: ignore[import-not-found]
                count_skills,
                get_db_path,
            )
        except ImportError:
            # pycozo missing is a hard error in Phase C — the entire runtime
            # assumes CozoDB as canonical. Warn and exit without suggestions.
            _exit_warning(
                "pycozo is not installed. Install with: "
                "uv pip install 'pycozo[embedded]>=0.7.6'"
            )
            return

        db_path = get_db_path()
        if not db_path.exists():
            _maybe_auto_reindex(index_path)
            return
        # Per DI-5 (audit 20260514): count_skills() returns -1 when the DB
        # file exists but is corrupt. Auto-reindex would burn CPU on every
        # prompt forever against a broken file — surface a manual-fix
        # warning instead.
        count = count_skills()
        if count == -1:
            _exit_warning(
                f"CozoDB at {db_path} appears corrupt. Delete it and "
                f"run /pss-reindex-skills to rebuild the index."
            )
            return
        if count == 0:
            _maybe_auto_reindex(index_path)
            return

        # Check if binary exists BEFORE doing any expensive work
        try:
            binary_path = find_binary()
        except (FileNotFoundError, RuntimeError) as e:
            _exit_warning(str(e))
            return

        # Augment prompt with previous user message for conversational context
        # (Rust binary handles all project/domain/tool/file-type detection itself)
        augmented_prompt = augment_prompt_with_context(clean_prompt, transcript_path)

        # Build minimal JSON for the binary — only fields it needs (prompt, cwd,
        # transcript_path). Avoids re-serializing 200KB+ of other hook input fields.
        # Field names are snake_case, matching the CC hook input spec and the
        # Rust HookInput struct (which no longer uses #[serde(rename_all)]).
        binary_input = {
            "prompt": augmented_prompt,
            "cwd": cwd,
            "transcript_path": transcript_path,
        }
        augmented_stdin = json.dumps(binary_input)

        # Call the binary with --format hook, --top to limit count,
        # --min-score to filter low quality matches.
        # Timeout MUST be less than hooks.json timeout (5s) to avoid zombie processes.
        # Unset VIRTUAL_ENV to prevent stale venv from interfering with the binary
        clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        argv = [
            str(binary_path),
            "--format",
            "hook",
            "--top",
            str(MAX_SUGGESTIONS),
            "--min-score",
            str(MIN_SCORE),
        ]

        # Wrap the subprocess call in a shared fcntl lock (LOCK_SH on the
        # same .db.lock file pss_cozodb writers take LOCK_EX on) so reads
        # cannot collide with an in-progress merge. cozo-ce calls .unwrap()
        # on `Connection::open()`, so a lost race becomes SIGABRT (-6)
        # rather than a recoverable error — see TRDD note in CLAUDE.md.
        # Retry once with backoff on -6 in case the residual race
        # (non-fcntl pathway, or another writer that bypasses our lock)
        # still occurs.
        def _run_binary() -> subprocess.CompletedProcess[str]:
            with _db_shared_lock():
                return subprocess.run(
                    argv,
                    input=augmented_stdin,
                    capture_output=True,
                    text=True,
                    timeout=SUBPROCESS_TIMEOUT,
                    env=clean_env,
                )

        result = _run_binary()
        if result.returncode == -6:
            # cozo-ce panic on a locked DB. Wait briefly for the writer
            # to release the SQLite file, then retry once. Bounded by
            # DB_RETRY_DELAY so we stay well under the 10s hook timeout.
            time.sleep(DB_RETRY_DELAY)
            result = _run_binary()

        # Output the result (binary already limits to MAX_SUGGESTIONS)
        if result.returncode == 0:
            # Parse the binary output — additionalContext always goes to the model
            hook_out = json.loads(result.stdout)
            # User-visible notification only in --debug mode (silent otherwise)
            if _is_debug_mode():
                try:
                    ctx = (hook_out.get("hookSpecificOutput") or {}).get(
                        "additionalContext", ""
                    )
                    if ctx:
                        # Extract "name [type]" pairs from compact format lines
                        names = re.findall(r"^\s+(.+?)\s+\[(\w+)\]", ctx, re.MULTILINE)
                        if names:
                            # Names in bold bright green, types in dim green, wrapped in guillemets
                            parts = [f"\033[1;92m{n}\033[0;32m ({t})" for n, t in names]
                            label = "\033[0;32m, ".join(parts)
                            notification = f"\033[1;92m⚡\u00ab Pss!... use\033[0;32m:\033[0;32m {label} \033[1;92m\u00bb\033[0m"
                            # Inject systemMessage into hook output for user-visible display
                            hook_out["systemMessage"] = notification
                except KeyError:
                    pass  # Don't block on display errors
            print(json.dumps(hook_out))
        else:
            build_script = Path(__file__).parent / "pss_build.py"
            # SIGABRT (-6) after retry → genuine concurrency loser. Surface
            # a targeted message (the "rebuild" suggestion is wrong here).
            if result.returncode == -6 and "database is locked" in (result.stderr or ""):
                _exit_warning(
                    "CozoDB busy after retry (another PSS writer is still holding the lock). "
                    "This usually clears within seconds; if it persists, check for a stuck "
                    "pss_merge_queue.py process and remove a stale ~/.claude/cache/pss-skill-index.db.lock."
                )
            else:
                _exit_warning(
                    f"binary exited with code {result.returncode}: {result.stderr[:300]}. Try rebuilding: uv run python {build_script}"
                )

        sys.exit(0)  # Always exit 0 to not block Claude

    except subprocess.TimeoutExpired:
        _exit_warning(
            f"binary timed out after {SUBPROCESS_TIMEOUT}s. The skill index may be too large or the binary may be stuck. Check: uv run python {Path(__file__).parent / 'pss_test_e2e.py'}"
        )
    except Exception as e:
        _exit_warning(str(e))


def _warm_index() -> None:
    """SessionStart hook handler: silently warm the skill index.

    In Phase C (v3.0.0), the check is against the CozoDB, not the JSON. If
    the DB is missing or empty, spawn a background reindex (detached) and
    exit 0 with no output. No stdin read, no chat notifications — this hook
    runs at session startup/resume and must never block or surface messages.
    """
    try:
        # CozoDB is the authoritative store in Phase C; JSON is only a debug
        # export. Verify the DB, not the JSON.
        try:
            from pss_cozodb import (  # type: ignore[import-not-found]
                count_skills,
                get_db_path,
            )
        except ImportError:
            return  # pycozo missing — defer to the real hook call which warns

        index_path = _get_cache_dir() / SKILL_INDEX_FILE
        db_path = get_db_path()
        if db_path.exists() and count_skills() > 0:
            return  # Nothing to do — DB is ready

        lock_path = index_path.with_suffix(".reindex.pid")
        if lock_path.exists():
            try:
                pid = int(lock_path.read_text().strip())
                if _is_pid_alive(pid):
                    return  # Reindex already in progress
            except (ValueError, OSError):
                pass
            lock_path.unlink(missing_ok=True)

        script_dir = Path(__file__).parent.resolve()
        reindex_script = script_dir / "pss_reindex.py"
        if not reindex_script.exists():
            return  # Graceful no-op if reindex script is missing

        proc = subprocess.Popen(
            [sys.executable, str(reindex_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(proc.pid).encode())
            os.close(fd)
        except FileExistsError:
            proc.kill()
    except Exception:
        return  # Never fail — SessionStart must be silent


def _post_compact() -> None:
    """PostCompact hook handler: stub for future re-suggest logic.

    Currently a no-op — reserves the event binding without re-scoring.
    Follow-up work can track prior suggestions and re-inject them here.
    """
    return


def _cli_dispatch() -> None:
    """CLI entry point. Routes `--warm-index` and `--post-compact` flags.

    Kept as a function so the module itself has no sys.exit at import time —
    the CPV plugin validator rejects module-scope SystemExit because a stray
    import of the module would kill the caller. Calling from inside
    `if __name__ == "__main__":` keeps the exit guarded.
    """
    if len(sys.argv) > 1:
        flag = sys.argv[1]
        if flag == "--warm-index":
            _warm_index()
            return
        if flag == "--post-compact":
            _post_compact()
            return
    main()


if __name__ == "__main__":
    _cli_dispatch()
