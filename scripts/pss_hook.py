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
import platform
import subprocess
import sys
from pathlib import Path

# Configuration - tune these to control context usage
MAX_SUGGESTIONS = 4  # Maximum number of skill suggestions (was 10, reduced to save context)
MIN_SCORE = 0.5  # Minimum score threshold (skip low-confidence matches)
MAX_TRANSCRIPT_LINES = 50  # How many recent transcript lines to scan for context

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
    "*.vcxproj": ("cpp", ["c++", "cpp", "visual studio"]),
    "*.csproj": ("csharp", ["c#", "csharp", "dotnet", ".net"]),
    "*.sln": ("dotnet", ["c#", "csharp", "dotnet", ".net", "visual studio"]),
    "meson.build": ("cpp", ["c++", "cpp", "c", "meson"]),
    "configure.ac": ("c", ["c", "autoconf", "autotools"]),
    "conanfile.txt": ("cpp", ["c++", "cpp", "conan"]),
    "conanfile.py": ("cpp", ["c++", "cpp", "conan"]),
    "vcpkg.json": ("cpp", ["c++", "cpp", "vcpkg"]),
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

# Prompts to skip (slash commands and simple responses don't need skill suggestions)
SKIP_PREFIXES = (
    "/",  # Slash commands like /plugin, /help, /exit
    "<command-name>/",  # Command tags from Claude Code
)

SKIP_SIMPLE_PROMPTS = {
    # Single words - confirmations and acknowledgments only
    "continue", "yes", "no", "ok", "okay", "thanks", "sure", "done", "stop",
    "y", "n", "yep", "nope", "thx", "ty", "next", "go", "proceed", "k",
    "yea", "yeah", "nah", "good", "great", "perfect", "fine", "cool", "nice",
    # Two-word phrases
    "got it", "thank you", "thanks!", "ok thanks", "okay thanks", "sounds good",
    "go ahead", "do it", "looks good", "that works", "yes please", "no thanks",
    "i see", "i understand", "makes sense", "all good", "thank you!",
}


def detect_project_type(cwd: str) -> list[str]:
    """Detect project type from cwd by looking for marker files."""
    if not cwd:
        return []

    cwd_path = Path(cwd)
    if not cwd_path.exists():
        return []

    context_keywords = []

    # Check for project marker files
    for marker, (_, keywords) in PROJECT_MARKERS.items():
        if (cwd_path / marker).exists():
            context_keywords.extend(keywords)
            break  # Use first match

    # If no marker found, check for common source files
    if not context_keywords:
        for ext, keywords in EXTENSION_CONTEXT.items():
            # Check if any files with this extension exist in cwd (shallow)
            if list(cwd_path.glob(f"*{ext}"))[:1]:  # Just check if any exist
                context_keywords.extend(keywords)
                break

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

    # Only augment short/generic prompts (less than 20 chars or single word)
    prompt_stripped = prompt.strip()
    if len(prompt_stripped) > 30 or " " in prompt_stripped:
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


def detect_platform():
    """Detect platform and architecture, return binary name."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Normalize architecture names
    if machine in ("aarch64",):
        machine = "arm64"
    elif machine in ("amd64",):
        machine = "x86_64"

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
        # Windows is typically x86_64
        return "pss-windows-x86_64.exe"

    # Unsupported platform
    raise RuntimeError(f"Unsupported platform: {system} {machine}")


def find_binary():
    """Locate the PSS binary relative to this script."""
    # This script is in: OUTPUT_SKILLS/perfect-skill-suggester/scripts/pss_hook.py
    # Binary is in: OUTPUT_SKILLS/perfect-skill-suggester/rust/skill-suggester/bin/
    script_dir = Path(__file__).parent.resolve()
    binary_name = detect_platform()
    binary_path = script_dir.parent / "rust" / "skill-suggester" / "bin" / binary_name

    if not binary_path.exists():
        raise FileNotFoundError(f"Binary not found: {binary_path}")

    return binary_path


def main():
    """Main entry point - read stdin, call binary, output result."""
    try:
        # Read JSON input from stdin
        stdin_data = sys.stdin.read()

        # Parse input to check if we should skip
        input_json: dict = {}
        try:
            input_json = json.loads(stdin_data)
            prompt = input_json.get("prompt", "")
            cwd = input_json.get("cwd", "")
            transcript_path = input_json.get("transcriptPath", "")
        except json.JSONDecodeError:
            # Invalid JSON - return empty
            print(json.dumps({}))
            sys.exit(0)

        # Skip prompts that don't need skill suggestions
        if should_skip_prompt(prompt):
            # Return empty hook output (no suggestions)
            print(json.dumps({}))
            sys.exit(0)

        # Augment generic prompts with project/conversation context
        augmented_prompt = augment_prompt_with_context(prompt, cwd, transcript_path)

        # Update the input JSON with augmented prompt
        input_json["prompt"] = augmented_prompt
        augmented_stdin = json.dumps(input_json)

        # Find the binary
        binary_path = find_binary()

        # Call the binary with --format hook, --top to limit count, --min-score to filter low quality
        result = subprocess.run(
            [
                str(binary_path),
                "--format", "hook",
                "--top", str(MAX_SUGGESTIONS),
                "--min-score", str(MIN_SCORE),
            ],
            input=augmented_stdin,
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )

        # Output the result
        if result.returncode == 0:
            print(result.stdout, end="")
        else:
            # On error, log to stderr and return empty JSON to stdout
            msg = f"PSS binary error (exit {result.returncode}): {result.stderr}"
            print(msg, file=sys.stderr)
            print(json.dumps({}))

        sys.exit(0)  # Always exit 0 to not block Claude

    except Exception as e:
        # On any error, log to stderr and return empty JSON to stdout
        print(f"PSS hook error: {e}", file=sys.stderr)
        print(json.dumps({}))
        sys.exit(0)


if __name__ == "__main__":
    main()
