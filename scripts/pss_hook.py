#!/usr/bin/env python3
"""
PSS Hook Script - Multiplatform binary caller for Perfect Skill Suggester.

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

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Configuration
MAX_SUGGESTIONS = 5  # Maximum skill suggestions per message (one line each)
MIN_SCORE = 0.5  # Minimum score threshold
SUBPROCESS_TIMEOUT = (
    4  # Binary timeout in seconds (hooks.json timeout is 5s; keep this < 5)
)
SKILL_INDEX_FILE = "skill-index.json"
# Prompt length cap for the Rust binary — the scorer only needs the first few
# thousand chars to determine intent.  Piping 100KB+ prompts causes timeouts
# (JSON parse + tokenization + scoring can't finish in 4s on huge inputs).
MAX_PROMPT_CHARS = 4000


_debug_mode_cache: bool | None = None


def _is_debug_mode() -> bool:
    """Check if Claude Code is running with --debug by walking the process tree.

    Matches only the actual 'claude' binary (not paths containing '.claude').
    Adapted from token-reporter-plugin. Result is cached for the process lifetime.
    """
    global _debug_mode_cache
    if _debug_mode_cache is not None:
        return _debug_mode_cache
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
    """Detect platform and architecture, return binary name."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Normalize architecture names
    if machine in ("aarch64",):
        machine = "arm64"
    elif machine in ("amd64",):
        machine = "x86_64"

    # Detect Android (reports as linux arm64 but uses separate binary)
    if system == "linux" and machine == "arm64":
        android_markers = (
            os.environ.get("ANDROID_ROOT"),
            os.environ.get("TERMUX_VERSION"),
        )
        if any(android_markers):
            # Android/Termux uses the linux-arm64 binary
            return "pss-linux-arm64"

    # Map to binary names
    if system == "darwin":
        if machine == "arm64":
            return "pss-darwin-arm64"
        if machine == "x86_64":
            return "pss-darwin-x86_64"
    elif system == "linux":
        if machine == "arm64":
            return "pss-linux-arm64"
        if machine == "x86_64":
            return "pss-linux-x86_64"
    elif system == "windows":
        # ARM64 Windows runs x86_64 via emulation
        return "pss-windows-x86_64.exe"

    # Unsupported platform
    raise RuntimeError(
        f"Unsupported platform: {system} {machine}. Supported: darwin-arm64, darwin-x86_64, linux-arm64, linux-x86_64, windows-x86_64. Build from source for other platforms."
    )


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
    try:
        os.kill(pid, 0)  # Signal 0 = existence check, no actual signal sent
        return True
    except OSError:
        return False


def _maybe_auto_reindex(index_path: Path) -> None:
    """Auto-spawn a background reindex if no index exists, with PID lockfile guard.

    - First call: spawns reindex, writes PID lockfile, notifies user
    - Subsequent calls while reindex runs: detects live PID, just notifies
    - After crash: detects dead PID, cleans up stale files, respawns
    """
    lock_path = index_path.with_suffix(".reindex.pid")

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
        # PID is dead or lockfile corrupt — clean up stale artifacts
        lock_path.unlink(missing_ok=True)
        # Clean up any staging/tmp files left by crashed reindex
        for suffix in (".json.tmp", ".staging.json"):
            index_path.with_suffix(suffix).unlink(missing_ok=True)

    # Spawn background reindex
    script_dir = Path(__file__).parent.resolve()
    reindex_script = script_dir / "pss_reindex.py"
    if not reindex_script.exists():
        _exit_warning(
            f"skill-index.json not found and reindex script missing at {reindex_script} — run /pss-reindex-skills manually"
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
        _exit_warning(f"skill-index.json not found, auto-reindex failed: {e}")


def main() -> None:
    """Main entry point - read stdin, call binary, output result."""
    try:
        # Read JSON input from stdin
        stdin_data = sys.stdin.read(
            1_048_576
        )  # 1MB cap to prevent memory exhaustion from oversized input

        # Parse input to check if we should skip
        input_json: dict[str, Any] = {}
        try:
            input_json = json.loads(stdin_data)
            prompt = input_json.get("prompt", "")
            cwd = input_json.get("cwd", "")
            transcript_path = input_json.get("transcriptPath", "")

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

        # Check if skill index exists and is valid BEFORE doing any expensive work.
        # If missing or corrupt, auto-spawn a background reindex and notify user.
        index_path = _get_cache_dir() / SKILL_INDEX_FILE
        if not index_path.exists():
            _maybe_auto_reindex(index_path)
            return
        # Quick corruption check: file must be valid JSON with a "skills" key
        try:
            with open(index_path, "r", encoding="utf-8-sig") as f:
                # Read first 256 chars to verify JSON structure (handles BOM + whitespace)
                header = f.read(256)
            if not header.strip().startswith("{"):
                raise ValueError("not JSON")
        except (OSError, ValueError):
            # Index file is corrupt — rename to .corrupt and trigger auto-reindex
            # (preserves evidence; if reindex fails, user still has the file)
            corrupt_path = index_path.with_suffix(".json.corrupt")
            try:
                index_path.rename(corrupt_path)
            except OSError:
                pass  # Best-effort rename; reindex will overwrite anyway
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
        # transcriptPath). Avoids re-serializing 200KB+ of other hook input fields.
        binary_input = {
            "prompt": augmented_prompt,
            "cwd": cwd,
            "transcriptPath": transcript_path,
        }
        augmented_stdin = json.dumps(binary_input)

        # Call the binary with --format hook, --top to limit count,
        # --min-score to filter low quality matches.
        # Timeout MUST be less than hooks.json timeout (5s) to avoid zombie processes.
        # Unset VIRTUAL_ENV to prevent stale venv from interfering with the binary
        clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        result = subprocess.run(
            [
                str(binary_path),
                "--format",
                "hook",
                "--top",
                str(MAX_SUGGESTIONS),
                "--min-score",
                str(MIN_SCORE),
            ],
            input=augmented_stdin,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
            env=clean_env,
        )

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


if __name__ == "__main__":
    main()
