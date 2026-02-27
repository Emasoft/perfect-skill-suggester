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
import subprocess
import sys
from pathlib import Path
from typing import Any

# Configuration - tune these to control context usage
MAX_SUGGESTIONS = 4  # Maximum number of skill suggestions per message (strict limit)
MIN_SCORE = 0.5  # Minimum score threshold (skip low-confidence matches)
MAX_TRANSCRIPT_LINES = 200  # How many recent transcript lines to scan for context
SUBPROCESS_TIMEOUT = (
    2  # Binary timeout in seconds (hooks.json timeout is 5000ms = 5s; keep this < 5)
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
    """Get the cache directory (~/.claude/cache/)."""
    return Path.home() / ".claude" / "cache"


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
    """
    Load tool catalog dynamically from skill-index.json.

    This extracts ALL unique tool names from the 'tools' field of every skill
    in the index. No hardcoded tool list - the catalog is built from what
    skills actually declare they use.
    """
    index_path = _get_cache_dir() / SKILL_INDEX_FILE
    if not index_path.exists():
        # Fallback: return empty set, no tool detection until index exists
        return set()

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)

        tools: set[str] = set()
        skills = index.get("skills", {})

        for _, skill_data in skills.items():
            # Extract tools from skill entry
            skill_tools = skill_data.get("tools", [])
            if isinstance(skill_tools, list):
                for tool in skill_tools:
                    if isinstance(tool, str) and tool.strip():
                        # Store lowercase for case-insensitive matching
                        tools.add(tool.strip().lower())

        return tools
    except (json.JSONDecodeError, IOError, OSError):
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


def extract_conversation_context(transcript_path: str) -> list[str]:
    """Read recent conversation from transcript and extract context keywords."""
    if not transcript_path:
        return []

    transcript_file = Path(transcript_path)
    if not transcript_file.exists():
        return []

    context_keywords = []

    try:
        # Read last N lines of transcript
        with open(transcript_file, "r", encoding="utf-8") as f:
            lines = f.readlines()[-MAX_TRANSCRIPT_LINES:]

        # Combine all text content
        text_content = ""
        for line in lines:
            try:
                entry = json.loads(line.strip())
                # Extract message content
                if "message" in entry:
                    msg = entry["message"]
                    if isinstance(msg, dict) and "content" in msg:
                        text_content += " " + str(msg["content"])
                # Also check hook content
                if "content" in entry and isinstance(entry["content"], list):
                    for c in entry["content"]:
                        if isinstance(c, str):
                            text_content += " " + c
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        # Search for context keywords in the text
        text_lower = text_content.lower()
        for keyword, context in CONVERSATION_KEYWORDS.items():
            if keyword in text_lower:
                context_keywords.extend(context)

    except (IOError, OSError):
        pass  # File read error, return empty

    return list(set(context_keywords))  # Dedupe


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

    detected_type = None

    # Check for project marker files
    for marker, (project_type, _) in PROJECT_MARKERS.items():
        if (cwd_path / marker).exists():
            detected_type = project_type
            break

    # If no marker found, check parent directories
    if not detected_type:
        for parent in list(cwd_path.parents)[:3]:
            for marker, (project_type, _) in PROJECT_MARKERS.items():
                if (parent / marker).exists():
                    detected_type = project_type
                    break
            if detected_type:
                break

    # If no marker found, check file extensions
    if not detected_type:
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
                detected_type = proj_type
                break

    # Get metadata for detected project type
    if detected_type and detected_type in PROJECT_CONTEXT_METADATA:
        meta: dict[str, list[str]] = PROJECT_CONTEXT_METADATA[detected_type]
        result["platforms"] = meta.get("platforms", [])
        result["frameworks"] = meta.get("frameworks", [])
        result["languages"] = meta.get("languages", [])

    return result


def detect_prompt_context(
    prompt: str, transcript_path: str = ""
) -> dict[str, list[str]]:
    """Detect domains, tools, and file types from prompt and conversation context."""
    result: dict[str, list[str]] = {"domains": [], "tools": [], "file_types": []}

    # Combine prompt with recent conversation for context detection
    text_to_analyze = prompt.lower()

    # Also add transcript content if available
    if transcript_path:
        transcript_file = Path(transcript_path)
        if transcript_file.exists():
            try:
                with open(transcript_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-MAX_TRANSCRIPT_LINES:]
                for line in lines:
                    try:
                        entry = json.loads(line.strip())
                        if "message" in entry:
                            msg = entry["message"]
                            if isinstance(msg, dict) and "content" in msg:
                                text_to_analyze += " " + str(msg["content"]).lower()
                    except (json.JSONDecodeError, KeyError, TypeError):
                        continue
            except (IOError, OSError):
                pass

    # Detect domains using Dewey classification from pss-domains.json
    # DOMAIN_KEYWORD_MAP maps keywords to domain codes (e.g., "docker" -> "330")
    for keyword, domain_code in DOMAIN_KEYWORD_MAP.items():
        if keyword in text_to_analyze:
            result["domains"].append(domain_code)

    # Detect tools from dynamic catalog extracted from skill-index.json
    # TOOL_CATALOG contains ALL tool names mentioned in indexed skills
    # We do exact substring matching against the prompt
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


def augment_prompt_with_context(prompt: str, cwd: str, transcript_path: str) -> str:
    """Add context keywords to generic prompts for better skill matching."""
    # Collect context from project type and conversation
    context_keywords = []
    context_keywords.extend(detect_project_type(cwd))
    context_keywords.extend(extract_conversation_context(transcript_path))

    # Dedupe
    context_keywords = list(set(context_keywords))

    if not context_keywords:
        return prompt  # No context found

    # Only augment short/generic prompts (80 chars or fewer)
    prompt_stripped = prompt.strip()
    if len(prompt_stripped) > 80:
        return prompt  # Prompt is already specific enough

    # Augment prompt with context keywords
    # Add top 2 context keywords to the prompt
    context_str = " ".join(context_keywords[:2])
    augmented = f"{prompt_stripped} {context_str}"

    return augmented


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
            return "pss-android-arm64"

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
        if machine == "arm64":
            return "pss-windows-arm64.exe"
        return "pss-windows-x86_64.exe"

    # Unsupported platform
    raise RuntimeError(
        f"Unsupported platform: {system} {machine}. "
        f"Supported: darwin-arm64, darwin-x86_64, linux-arm64, linux-x86_64, "
        f"windows-x86_64, windows-arm64, android-arm64. "
        f"For other platforms, use the WASM binary: pss-wasm32.wasm"
    )


def find_binary() -> Path:
    """Locate the PSS binary relative to this script."""
    # This script is in: OUTPUT_SKILLS/perfect-skill-suggester/scripts/pss_hook.py
    # Binary is in: OUTPUT_SKILLS/perfect-skill-suggester/rust/skill-suggester/bin/
    script_dir = Path(__file__).parent.resolve()
    binary_name = detect_platform()
    binary_path = script_dir.parent / "rust" / "skill-suggester" / "bin" / binary_name

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
    """Exit with warning to stderr and valid empty hook output to stdout."""
    print(f"PSS: {msg}", file=sys.stderr)
    print(json.dumps(_EMPTY_HOOK_OUTPUT))
    sys.exit(0)


def main() -> None:
    """Main entry point - read stdin, call binary, output result."""
    try:
        # Read JSON input from stdin
        stdin_data = sys.stdin.read()

        # Parse input to check if we should skip
        input_json: dict[str, Any] = {}
        try:
            input_json = json.loads(stdin_data)
            prompt = input_json.get("prompt", "")
            cwd = input_json.get("cwd", "")
            transcript_path = input_json.get("transcriptPath", "")
        except json.JSONDecodeError:
            _exit_empty()
            return  # unreachable but satisfies type checker

        # Skip prompts that don't need skill suggestions (BEFORE any file I/O)
        if should_skip_prompt(prompt):
            _exit_empty()
            return

        # Check if skill index exists BEFORE doing any expensive work
        index_path = _get_cache_dir() / SKILL_INDEX_FILE
        if not index_path.exists():
            _exit_warning(
                f"skill-index.json not found at {index_path} — "
                f"run /pss-reindex-skills in Claude Code to generate it"
            )
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
        )

        # Output the result (binary already limits to MAX_SUGGESTIONS)
        if result.returncode == 0:
            print(result.stdout, end="")
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
