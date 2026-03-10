#!/usr/bin/env python3
"""
PSS Hook Script - Multiplatform binary caller for Perfect Skill Suggester
Replaces hook.sh and hook.ps1 with unified Python implementation

Now with context-awareness:
- Detects project type from cwd (Cargo.toml → Rust, package.json → JS/TS, etc.)
- Reads recent conversation for context keywords
- Augments generic prompts with context for better skill matching
"""

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Configuration - tune these to control context usage
MAX_SUGGESTIONS = 4  # Maximum number of skill suggestions per message (strict limit)
MIN_SCORE = 0.5  # Minimum score threshold (skip low-confidence matches)
MAX_TRANSCRIPT_LINES = 200  # How many recent transcript lines to scan for context
SUBPROCESS_TIMEOUT = (
    4  # Binary timeout in seconds (hooks.json timeout is 5000ms = 5s; keep this < 5)
)

# Project type detection markers
PROJECT_MARKERS = {
    # filename/dirname → (project_type, context_keywords)
    "Cargo.toml": ("rust", ["rust", "cargo", "crate"]),
    "Cargo.lock": ("rust", ["rust", "cargo"]),
    "package.json": ("javascript", ["javascript", "typescript", "node", "npm"]),
    "tsconfig.json": ("typescript", ["typescript", "ts"]),
    "pyproject.toml": ("python", ["python", "pip", "uv"]),
    "setup.py": ("python", ["python", "pip"]),
    "requirements.txt": ("python", ["python", "pip"]),
    "go.mod": ("go", ["go", "golang"]),
    "go.sum": ("go", ["go", "golang"]),
    "Package.swift": ("swift", ["swift", "ios", "macos", "xcode"]),
    "Podfile": ("ios", ["ios", "swift", "xcode", "cocoapods"]),
    "build.gradle": ("android", ["android", "kotlin", "gradle"]),
    "build.gradle.kts": ("android", ["android", "kotlin", "gradle"]),
    "CMakeLists.txt": ("cpp", ["c++", "cpp", "cmake"]),
    "Makefile": ("make", ["make", "build"]),
    "Gemfile": ("ruby", ["ruby", "rails", "gem"]),
    "mix.exs": ("elixir", ["elixir", "phoenix"]),
    "pubspec.yaml": ("flutter", ["flutter", "dart"]),
    # C/C++/C#/Objective-C
    "meson.build": ("cpp", ["c++", "cpp", "c", "meson"]),
    "configure.ac": ("c", ["c", "autoconf", "autotools"]),
    "conanfile.txt": ("cpp", ["c++", "cpp", "conan"]),
    "conanfile.py": ("cpp", ["c++", "cpp", "conan"]),
    "vcpkg.json": ("cpp", ["c++", "cpp", "vcpkg"]),
}

# Detailed context metadata for Rust binary filtering
# project_type → {platforms, frameworks, languages}
PROJECT_CONTEXT_METADATA: dict[str, dict[str, list[str]]] = {
    "rust": {"platforms": [], "frameworks": [], "languages": ["rust"]},
    "javascript": {"platforms": [], "frameworks": [], "languages": ["javascript"]},
    "typescript": {"platforms": [], "frameworks": [], "languages": ["typescript"]},
    "python": {"platforms": [], "frameworks": [], "languages": ["python"]},
    "go": {"platforms": [], "frameworks": [], "languages": ["go"]},
    "swift": {
        "platforms": ["ios", "macos", "watchos", "tvos"],
        "frameworks": [],
        "languages": ["swift"],
    },
    "ios": {
        "platforms": ["ios"],
        "frameworks": [],
        "languages": ["swift", "objective-c"],
    },
    "android": {
        "platforms": ["android"],
        "frameworks": [],
        "languages": ["kotlin", "java"],
    },
    "cpp": {"platforms": [], "frameworks": [], "languages": ["c++", "c"]},
    "c": {"platforms": [], "frameworks": [], "languages": ["c"]},
    "csharp": {"platforms": ["windows"], "frameworks": ["dotnet"], "languages": ["c#"]},
    "dotnet": {"platforms": ["windows"], "frameworks": ["dotnet"], "languages": ["c#"]},
    "ruby": {"platforms": [], "frameworks": [], "languages": ["ruby"]},
    "elixir": {"platforms": [], "frameworks": [], "languages": ["elixir"]},
    "flutter": {
        "platforms": ["ios", "android"],
        "frameworks": ["flutter"],
        "languages": ["dart"],
    },
    "make": {"platforms": [], "frameworks": [], "languages": []},
}

# File extensions for additional context (if no project marker found)
EXTENSION_CONTEXT = {
    ".rs": ["rust"],
    ".py": ["python"],
    ".js": ["javascript"],
    ".ts": ["typescript"],
    ".tsx": ["typescript", "react"],
    ".jsx": ["javascript", "react"],
    ".swift": ["swift", "ios", "macos"],
    ".kt": ["kotlin", "android"],
    ".go": ["go", "golang"],
    ".rb": ["ruby"],
    ".ex": ["elixir"],
    ".exs": ["elixir"],
    # C/C++/C#/Objective-C
    ".c": ["c"],
    ".h": ["c", "c++"],
    ".cpp": ["c++", "cpp"],
    ".cxx": ["c++", "cpp"],
    ".cc": ["c++", "cpp"],
    ".hpp": ["c++", "cpp"],
    ".hxx": ["c++", "cpp"],
    ".cs": ["c#", "csharp", "dotnet"],
    ".m": ["objective-c", "ios", "macos"],
    ".mm": ["objective-c++", "ios", "macos"],
}

# Conversation context keywords to detect
CONVERSATION_KEYWORDS = {
    # keyword in conversation → context to add
    "rust": ["rust"],
    "cargo": ["rust", "cargo"],
    "python": ["python"],
    "javascript": ["javascript"],
    "typescript": ["typescript"],
    "swift": ["swift", "ios"],
    "swiftui": ["swift", "ios", "swiftui"],
    "ios": ["ios", "swift"],
    "android": ["android", "kotlin"],
    "react": ["react", "javascript"],
    "vue": ["vue", "javascript"],
    "node": ["node", "javascript"],
    "django": ["python", "django"],
    "flask": ["python", "flask"],
    "fastapi": ["python", "fastapi"],
    "docker": ["docker", "container"],
    "kubernetes": ["kubernetes", "k8s"],
    "github actions": ["github", "ci/cd"],
    "xcode": ["xcode", "ios", "macos"],
}

# ============================================================================
# DYNAMIC CATALOGS - Loaded from schema files and skill index
# ============================================================================

# Dewey-like domain classification (loaded from pss-domains.json)
# Maps keywords to domain codes (e.g., "docker" -> "330" for Containers)
DOMAIN_KEYWORD_MAP: dict[str, str] = {}

# Dynamic tool catalog (extracted from skill-index.json during load)
# Contains ALL tool names mentioned across all indexed skills
TOOL_CATALOG: set[str] = set()

# Schema file paths (relative to plugin root)
DOMAIN_SCHEMA_FILE = "schemas/pss-domains.json"
SKILL_INDEX_FILE = "skill-index.json"


def _get_plugin_root() -> Path:
    """Get the plugin root directory."""
    # Script is in scripts/, plugin root is parent
    return Path(__file__).parent.parent


def _get_cache_dir() -> Path:
    """Get the PSS cache directory."""
    from pss_paths import get_cache_dir

    return get_cache_dir()


def _load_domain_schema() -> dict[str, str]:
    """Load Dewey-like domain classification from schema file."""
    schema_path = _get_plugin_root() / DOMAIN_SCHEMA_FILE
    if not schema_path.exists():
        # Fallback: return empty, will use no domain detection
        return {}

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema: dict[str, object] = json.load(f)

        # Extract keyword_to_domain_mapping
        mapping = schema.get("keyword_to_domain_mapping", {})
        if isinstance(mapping, dict):
            # Validate and return only str->str entries
            result: dict[str, str] = {}
            for k, v in mapping.items():
                if isinstance(k, str) and isinstance(v, str):
                    result[k] = v
            return result
        return {}
    except (json.JSONDecodeError, IOError, OSError):
        return {}


def _load_tool_catalog() -> set[str]:
    """Return empty set — tool detection is handled entirely by the Rust binary.

    The Rust binary already detects tools two ways:
    1. scan_project_context() — detects tools from project files (Cargo.toml → cargo, etc.)
    2. Scoring loop — matches each skill's 'tools' field against the prompt text

    Previously this function parsed the entire 13MB skill-index.json in Python
    just to extract tool names for substring matching. That was redundant with
    what Rust already does, and added ~67ms+ of unnecessary I/O per invocation.
    """
    return set()


def _initialize_catalogs() -> None:
    """Initialize domain and tool catalogs on first use."""
    global DOMAIN_KEYWORD_MAP, TOOL_CATALOG

    if not DOMAIN_KEYWORD_MAP:
        DOMAIN_KEYWORD_MAP = _load_domain_schema()

    if not TOOL_CATALOG:
        TOOL_CATALOG = _load_tool_catalog()


# NOTE: Catalogs are initialized lazily in main() AFTER skip checks,
# to avoid loading files when the prompt will be skipped anyway.


# File type detection keywords (from conversation/prompt)
FILE_TYPE_KEYWORDS = {
    "pdf": ["pdf"],
    "xlsx": ["xlsx"],
    "xls": ["xls", "xlsx"],
    "excel": ["xlsx"],
    "docx": ["docx"],
    "doc": ["doc", "docx"],
    "word": ["docx"],
    "pptx": ["pptx"],
    "powerpoint": ["pptx"],
    "epub": ["epub"],
    "mobi": ["mobi"],
    "csv": ["csv"],
    "json": ["json"],
    "yaml": ["yaml"],
    "yml": ["yaml"],
    "xml": ["xml"],
    "html": ["html"],
    "markdown": ["md"],
    "mp4": ["mp4"],
    "mp3": ["mp3"],
    "wav": ["wav"],
    "flac": ["flac"],
    "mov": ["mov"],
    "avi": ["avi"],
    "mkv": ["mkv"],
    "webm": ["webm"],
    "png": ["png"],
    "jpg": ["jpg"],
    "jpeg": ["jpg"],
    "gif": ["gif"],
    "svg": ["svg"],
    "webp": ["webp"],
    "ico": ["ico"],
    "tiff": ["tiff"],
    "bmp": ["bmp"],
}

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


def detect_project_type(cwd: str) -> list[str]:
    """Detect project type from cwd by looking for marker files."""
    if not cwd:
        return []

    cwd_path = Path(cwd)
    if not cwd_path.exists():
        return []

    context_keywords = []

    # Check for project marker files (no break — support polyglot projects)
    for marker, (_, keywords) in PROJECT_MARKERS.items():
        if (cwd_path / marker).exists():
            context_keywords.extend(keywords)

    # If no marker found, check for common source files
    if not context_keywords:
        for ext, keywords in EXTENSION_CONTEXT.items():
            if list(cwd_path.glob(f"*{ext}"))[:1]:
                context_keywords.extend(keywords)

    # Also check parent directories (up to 3 levels) for project markers
    if not context_keywords:
        for parent in list(cwd_path.parents)[:3]:
            for marker, (_, keywords) in PROJECT_MARKERS.items():
                if (parent / marker).exists():
                    context_keywords.extend(keywords)
                    return list(set(context_keywords))  # Dedupe and return

    return list(set(context_keywords))  # Dedupe


def extract_previous_user_message(transcript_path: str) -> str:
    """Extract the PREVIOUS user message from the transcript (not the current one).

    The hook fires on UserPromptSubmit, so the current message is already in the
    transcript. We skip the first (most recent) user message and return the second
    one — that's the actual previous message the user typed before this prompt.
    """
    if not transcript_path:
        return ""

    transcript_file = Path(transcript_path)
    if not transcript_file.exists():
        return ""

    try:
        with open(transcript_file, "r", encoding="utf-8") as f:
            lines = f.readlines()[-MAX_TRANSCRIPT_LINES:]

        # Walk backwards, skip the first user message (current prompt), return the second
        user_messages_found = 0
        for line in reversed(lines):
            try:
                entry = json.loads(line.strip())
                if "message" not in entry:
                    continue
                msg = entry["message"]
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role", "")
                if role not in ("human", "user"):
                    continue
                content = msg.get("content", "")
                text = ""
                if isinstance(content, str):
                    text = content.strip()
                elif isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, str):
                            parts.append(block)
                        elif isinstance(block, dict) and block.get("type") == "text":
                            parts.append(block.get("text", ""))
                    text = " ".join(parts).strip()
                if not text:
                    continue
                user_messages_found += 1
                # Skip the 1st (current prompt already in transcript), return the 2nd
                if user_messages_found >= 2:
                    return text
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    except (IOError, OSError):
        pass

    return ""


def extract_conversation_context(transcript_path: str) -> list[str]:
    """Extract context keywords from the previous user message only.

    Only checks the previous user message (not the entire transcript) to avoid
    injecting thousands of irrelevant terms from the conversation history.
    """
    prev_msg = extract_previous_user_message(transcript_path)
    if not prev_msg:
        return []

    context_keywords = []
    text_lower = prev_msg.lower()
    for keyword, context in CONVERSATION_KEYWORDS.items():
        if keyword in text_lower:
            context_keywords.extend(context)

    return list(set(context_keywords))


def extract_context_metadata(cwd: str) -> dict[str, list[str]]:
    """
    Extract detailed context metadata for Rust binary filtering.

    Returns platforms, frameworks, and languages detected from project type.
    """
    result: dict[str, list[str]] = {"platforms": [], "frameworks": [], "languages": []}

    if not cwd:
        return result

    cwd_path = Path(cwd)
    if not cwd_path.exists():
        return result

    detected_types: set[str] = set()

    # Check for project marker files — collect ALL matches for polyglot projects
    for marker, (project_type, _) in PROJECT_MARKERS.items():
        if (cwd_path / marker).exists():
            detected_types.add(project_type)

    # If no marker found, check parent directories
    if not detected_types:
        for parent in list(cwd_path.parents)[:3]:
            for marker, (project_type, _) in PROJECT_MARKERS.items():
                if (parent / marker).exists():
                    detected_types.add(project_type)
            if detected_types:
                break

    # If no marker found, check file extensions
    if not detected_types:
        ext_to_type = {
            ".rs": "rust",
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".swift": "swift",
            ".kt": "android",
            ".go": "go",
            ".rb": "ruby",
            ".c": "c",
            ".cpp": "cpp",
            ".cs": "csharp",
            ".m": "ios",
        }
        for ext, proj_type in ext_to_type.items():
            if list(cwd_path.glob(f"*{ext}"))[:1]:
                detected_types.add(proj_type)

    # Get metadata for all detected project types (polyglot support)
    for detected_type in detected_types:
        if detected_type in PROJECT_CONTEXT_METADATA:
            meta: dict[str, list[str]] = PROJECT_CONTEXT_METADATA[detected_type]
            for p in meta.get("platforms", []):
                if p not in result["platforms"]:
                    result["platforms"].append(p)
            for f in meta.get("frameworks", []):
                if f not in result["frameworks"]:
                    result["frameworks"].append(f)
            for lang in meta.get("languages", []):
                if lang not in result["languages"]:
                    result["languages"].append(lang)

    return result


def detect_prompt_context(
    prompt: str, transcript_path: str = ""
) -> dict[str, list[str]]:
    """Detect domains, tools, and file types from current prompt + previous user message.

    Only uses the current prompt and the immediately preceding user message — NOT the
    entire transcript. Scanning thousands of transcript lines injects irrelevant tools
    and domains from unrelated earlier discussion.
    """
    result: dict[str, list[str]] = {"domains": [], "tools": [], "file_types": []}

    # Combine current prompt with previous user message only
    text_to_analyze = prompt.lower()
    prev_msg = extract_previous_user_message(transcript_path)
    if prev_msg:
        text_to_analyze += " " + prev_msg.lower()

    # Detect domains using Dewey classification from pss-domains.json
    for keyword, domain_code in DOMAIN_KEYWORD_MAP.items():
        if keyword in text_to_analyze:
            result["domains"].append(domain_code)

    # Detect tools from dynamic catalog extracted from skill-index.json
    for tool in TOOL_CATALOG:
        if tool in text_to_analyze:
            result["tools"].append(tool)

    # Detect file types
    for keyword, file_types in FILE_TYPE_KEYWORDS.items():
        if keyword in text_to_analyze:
            result["file_types"].extend(file_types)

    # Dedupe
    result["domains"] = list(set(result["domains"]))
    result["tools"] = list(set(result["tools"]))
    result["file_types"] = list(set(result["file_types"]))

    return result


def augment_prompt_with_context(prompt: str, _cwd: str, transcript_path: str) -> str:
    """Concatenate previous user message + current prompt in full.

    Users often write follow-up prompts referring to what they just said.
    Always concatenate both messages so the scorer sees the full intent.
    Note: _cwd is unused — project context is passed separately via extract_context_metadata.
    """
    prompt_stripped = prompt.strip()

    # Always concatenate previous message + current prompt, no truncation, no caps
    prev_msg = extract_previous_user_message(transcript_path)
    if prev_msg:
        return f"{prev_msg} {prompt_stripped}"

    return prompt_stripped


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

    # Skip task notifications
    if "<task-notification>" in prompt:
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
        f"Unsupported platform: {system} {machine}. "
        f"Supported: darwin-arm64, darwin-x86_64, linux-arm64, linux-x86_64, "
        f"windows-x86_64. Build from source for other platforms."
    )


def find_binary() -> Path:
    """Locate the PSS binary relative to this script."""
    # This script is in: perfect-skill-suggester/scripts/pss_hook.py
    # Binary is in: perfect-skill-suggester/src/skill-suggester/bin/
    script_dir = Path(__file__).parent.resolve()
    binary_name = detect_platform()
    binary_path = script_dir.parent / "src" / "skill-suggester" / "bin" / binary_name

    if not binary_path.exists():
        raise FileNotFoundError(
            f"PSS binary not found at: {binary_path}. "
            f"Build it with: uv run python {script_dir / 'pss_build.py'}"
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
            f"skill-index.json not found and reindex script missing at {reindex_script} — "
            f"run /pss-reindex-skills manually"
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
        _exit_warning("skill index not found — auto-reindex started, suggestions available shortly")
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

        # Skip prompts that don't need skill suggestions (BEFORE any file I/O)
        if should_skip_prompt(prompt):
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

        # NOW initialize catalogs (lazy — only after skip checks pass)
        _initialize_catalogs()

        # Augment generic prompts with project/conversation context
        augmented_prompt = augment_prompt_with_context(prompt, cwd, transcript_path)

        # Extract detailed context metadata for platform/framework/language filtering
        context_metadata = extract_context_metadata(cwd)

        # Extract domains, tools, file types from prompt and conversation
        prompt_context = detect_prompt_context(prompt, transcript_path)

        # Update the input JSON with augmented prompt and all context metadata
        input_json["prompt"] = augmented_prompt
        input_json["context_platforms"] = context_metadata["platforms"]
        input_json["context_frameworks"] = context_metadata["frameworks"]
        input_json["context_languages"] = context_metadata["languages"]
        input_json["context_domains"] = prompt_context["domains"]
        input_json["context_tools"] = prompt_context["tools"]
        input_json["context_file_types"] = prompt_context["file_types"]
        augmented_stdin = json.dumps(input_json)

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
            # Build user-visible summary via systemMessage (like token-reporter)
            hook_out = json.loads(result.stdout)
            try:
                ctx = (hook_out.get("hookSpecificOutput") or {}).get(
                    "additionalContext", ""
                )
                if ctx:
                    # Extract "name [type]" pairs from SUGGESTED lines
                    names = re.findall(r"SUGGESTED:\s+(.+?)\s+\[(\w+)\]", ctx)
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
                f"binary exited with code {result.returncode}: "
                f"{result.stderr[:300]}. "
                f"Try rebuilding: uv run python {build_script}"
            )

        sys.exit(0)  # Always exit 0 to not block Claude

    except subprocess.TimeoutExpired:
        _exit_warning(
            f"binary timed out after {SUBPROCESS_TIMEOUT}s. "
            f"The skill index may be too large or the binary may be stuck. "
            f"Check: uv run python {Path(__file__).parent / 'pss_test_e2e.py'}"
        )
    except Exception as e:
        _exit_warning(str(e))


if __name__ == "__main__":
    main()
