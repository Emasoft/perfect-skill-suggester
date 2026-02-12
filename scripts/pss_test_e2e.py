#!/usr/bin/env python3
"""
PSS End-to-End Test Script

Self-contained runtime test for the entire PSS pipeline:
  Phase 1: Environment setup (temp dirs, binary check)
  Phase 2: Create test skills (3 fake SKILL.md files)
  Phase 3: Merge queue Pass 1 (keywords/metadata into index)
  Phase 4: Merge queue Pass 2 (co-usage into index)
  Phase 5: Rust binary scoring (direct prompt matching)
  Phase 6: Hook simulation (hook-format output matching)

Requirements: Python 3.10+ stdlib only (no pip dependencies).
Works for any user who installs the PSS plugin, regardless of scope.

Usage:
    python3 scripts/pss_test_e2e.py              # Run all tests
    python3 scripts/pss_test_e2e.py --verbose     # Detailed output per phase
    python3 scripts/pss_test_e2e.py --keep-temp   # Don't cleanup (for debugging)

Library usage (from pss_validate_plugin.py):
    from pss_test_e2e import run_all_tests
    results = run_all_tests(plugin_root)
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Test skills data — 3 diverse skills covering different categories
TEST_SKILLS: list[dict[str, Any]] = [
    {
        "name": "test-python-linter",
        "category": "code-quality",
        "description": "Python code linting and formatting with ruff",
        "use_cases": ["Lint Python files with ruff", "Format Python code to PEP 8"],
        "platforms": ["universal"],
        "frameworks": [],
        "languages": ["python"],
        "domains": ["160"],
        "tools": ["ruff"],
        "file_types": ["py"],
        "keywords": [
            "python lint ruff",
            "ruff format python",
            "python code style check",
            "lint python files ruff",
            "check python code quality",
            "python formatting pep8",
            "ruff linter python",
            "python static analysis ruff",
        ],
        "intents": ["lint", "format", "check"],
        "co_usage": {
            "usually_with": ["test-docker-deploy"],
            "precedes": [],
            "follows": [],
            "alternatives": [],
            "rationale": "Linting often precedes deployment in CI pipelines",
        },
        "tier": "primary",
        "skill_md": (
            "---\n"
            "name: test-python-linter\n"
            'description: "Python code linting and formatting with ruff"\n'
            "user-invocable: false\n"
            "---\n\n"
            "# Test Python Linter\n\n"
            "Lint and format Python code using ruff.\n\n"
            "## Use Cases\n"
            "- Lint Python files with ruff\n"
            "- Format Python code to PEP 8\n"
        ),
    },
    {
        "name": "test-docker-deploy",
        "category": "devops-cicd",
        "description": "Docker container deployment and orchestration",
        "use_cases": [
            "Deploy Docker containers to production",
            "Manage container orchestration",
        ],
        "platforms": ["universal"],
        "frameworks": [],
        "languages": ["any"],
        "domains": ["330"],
        "tools": ["docker", "docker-compose"],
        "file_types": ["yaml", "yml", "dockerfile"],
        "keywords": [
            "docker deploy container",
            "container orchestration docker",
            "docker compose deploy",
            "deploy docker production",
            "docker container management",
            "docker build push deploy",
            "container deployment pipeline",
            "docker compose orchestration",
        ],
        "intents": ["deploy", "build", "orchestrate"],
        "co_usage": {
            "usually_with": ["test-python-linter"],
            "precedes": [],
            "follows": [],
            "alternatives": [],
            "rationale": "Docker deployment follows code quality checks",
        },
        "tier": "primary",
        "skill_md": (
            "---\n"
            "name: test-docker-deploy\n"
            'description: "Docker container deployment and orchestration"\n'
            "user-invocable: false\n"
            "---\n\n"
            "# Test Docker Deploy\n\n"
            "Deploy and manage Docker containers.\n\n"
            "## Use Cases\n"
            "- Deploy Docker containers to production\n"
            "- Manage container orchestration\n"
        ),
    },
    {
        "name": "test-react-frontend",
        "category": "web-frontend",
        "description": "React component development with hooks and JSX",
        "use_cases": [
            "Build React components with hooks",
            "Create interactive React UIs with JSX",
        ],
        "platforms": ["web"],
        "frameworks": ["react"],
        "languages": ["typescript", "javascript"],
        "domains": ["110"],
        "tools": ["react", "vite"],
        "file_types": ["tsx", "jsx", "css"],
        "keywords": [
            "react component jsx hooks",
            "react hooks state management",
            "build react app component",
            "react frontend development",
            "react jsx component creation",
            "react hooks usestate useeffect",
            "react typescript component",
            "react ui development",
        ],
        "intents": ["build", "create", "develop"],
        "co_usage": {
            "usually_with": ["test-docker-deploy"],
            "precedes": [],
            "follows": [],
            "alternatives": [],
            "rationale": "Frontend apps are containerized for deployment",
        },
        "tier": "primary",
        "skill_md": (
            "---\n"
            "name: test-react-frontend\n"
            'description: "React component development with hooks and JSX"\n'
            "user-invocable: false\n"
            "---\n\n"
            "# Test React Frontend\n\n"
            "Build React components with modern hooks.\n\n"
            "## Use Cases\n"
            "- Build React components with hooks\n"
            "- Create interactive React UIs with JSX\n"
        ),
    },
]

# Test prompts and expected matches for Phase 6
HOOK_TEST_CASES: list[dict[str, str]] = [
    {
        "prompt": "lint python code with ruff",
        "expected_skill": "test-python-linter",
    },
    {
        "prompt": "deploy docker container to production",
        "expected_skill": "test-docker-deploy",
    },
    {
        "prompt": "build react component with hooks",
        "expected_skill": "test-react-frontend",
    },
]


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------


class TestResult:
    """Single test phase result."""

    def __init__(self, name: str, passed: bool, detail: str) -> None:
        self.name = name
        self.passed = passed
        self.detail = detail


# ---------------------------------------------------------------------------
# Platform detection (same logic as pss_hook.py)
# ---------------------------------------------------------------------------


def detect_platform_binary() -> str:
    """Detect platform and return binary name (mirrors pss_hook.py logic)."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if machine in ("aarch64",):
        machine = "arm64"
    elif machine in ("amd64",):
        machine = "x86_64"

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
        return "pss-windows-x86_64.exe"

    raise RuntimeError(f"Unsupported platform: {system} {machine}")


def find_binary(plugin_root: Path) -> Path:
    """Locate PSS binary relative to plugin root."""
    binary_name = detect_platform_binary()
    binary_path = plugin_root / "rust" / "skill-suggester" / "bin" / binary_name
    if not binary_path.exists():
        raise FileNotFoundError(f"Binary not found: {binary_path}")
    return binary_path


# ---------------------------------------------------------------------------
# Phase implementations
# ---------------------------------------------------------------------------


def phase1_setup(plugin_root: Path, verbose: bool) -> tuple[TestResult, dict[str, Any]]:
    """Phase 1: Environment setup — temp dirs, binary check."""
    try:
        # Create temp dir
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        temp_dir = Path(tempfile.mkdtemp(prefix=f"pss-test-{timestamp}-"))

        # Create subdirectories
        skills_dir = temp_dir / "skills"
        queue_dir = temp_dir / "queue"
        # Fake home structure for the Rust binary (reads ~/.claude/cache/)
        fake_home = temp_dir / "home"
        cache_dir = fake_home / ".claude" / "cache"
        cache_dir.mkdir(parents=True)
        skills_dir.mkdir()
        queue_dir.mkdir()

        # Create skeleton index
        skeleton_index = {
            "version": "3.0",
            "generated": datetime.now(tz=timezone.utc).isoformat(),
            "method": "ai-analyzed",
            "pass": 0,
            "skills_count": 0,
            "skills": {},
        }
        index_path = cache_dir / "skill-index.json"
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(skeleton_index, f, indent=2)

        # Find binary
        binary_path = find_binary(plugin_root)

        env = {
            "temp_dir": temp_dir,
            "skills_dir": skills_dir,
            "queue_dir": queue_dir,
            "cache_dir": cache_dir,
            "fake_home": fake_home,
            "index_path": index_path,
            "binary_path": binary_path,
            "plugin_root": plugin_root,
        }

        detail = f"binary found at {binary_path.name}, temp at {temp_dir}"
        if verbose:
            detail += f"\n  Index: {index_path}\n  Binary: {binary_path}"

        return TestResult("Phase 1: Environment setup", True, detail), env

    except Exception as e:
        return TestResult("Phase 1: Environment setup", False, str(e)), {}


def phase2_create_skills(env: dict[str, Any], verbose: bool) -> TestResult:
    """Phase 2: Create 3 test SKILL.md files."""
    try:
        skills_dir: Path = env["skills_dir"]
        created = 0

        for skill in TEST_SKILLS:
            skill_dir = skills_dir / skill["name"]
            skill_dir.mkdir()
            skill_md_path = skill_dir / "SKILL.md"
            skill_md_path.write_text(skill["skill_md"], encoding="utf-8")
            created += 1

        detail = f"{created} SKILL.md files created"
        if verbose:
            names = [s["name"] for s in TEST_SKILLS]
            detail += f"\n  Skills: {', '.join(names)}"

        return TestResult("Phase 2: Test skills created", True, detail)

    except Exception as e:
        return TestResult("Phase 2: Test skills created", False, str(e))


def phase3_pass1_merge(env: dict[str, Any], verbose: bool) -> TestResult:
    """Phase 3: Test merge queue Pass 1 — keywords/metadata."""
    try:
        queue_dir: Path = env["queue_dir"]
        index_path: Path = env["index_path"]
        skills_dir: Path = env["skills_dir"]
        plugin_root: Path = env["plugin_root"]
        merge_script = plugin_root / "scripts" / "pss_merge_queue.py"

        if not merge_script.exists():
            return TestResult(
                "Phase 3: Pass 1 merge",
                False,
                f"Merge script not found: {merge_script}",
            )

        merged = 0
        errors: list[str] = []

        for skill in TEST_SKILLS:
            pss_data = {
                "name": skill["name"],
                "type": "skill",
                "source": "test",
                "path": str(skills_dir / skill["name"] / "SKILL.md"),
                "description": skill["description"],
                "use_cases": skill["use_cases"],
                "category": skill["category"],
                "platforms": skill["platforms"],
                "frameworks": skill["frameworks"],
                "languages": skill["languages"],
                "domains": skill["domains"],
                "tools": skill["tools"],
                "file_types": skill["file_types"],
                "keywords": skill["keywords"],
                "intents": skill["intents"],
                "pass": 1,
            }

            pss_file = queue_dir / f"{skill['name']}.pss"
            with open(pss_file, "w", encoding="utf-8") as f:
                json.dump(pss_data, f, indent=2)

            result = subprocess.run(
                [
                    sys.executable,
                    str(merge_script),
                    str(pss_file),
                    "--pass",
                    "1",
                    "--index",
                    str(index_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                errors.append(
                    f"{skill['name']}: exit {result.returncode} — {result.stderr[:200]}"
                )
            else:
                merged += 1

            # Verify .pss file was deleted
            if pss_file.exists():
                errors.append(f"{skill['name']}: .pss file not deleted after merge")

        # Verify index contents
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)

        skill_count = len(index.get("skills", {}))
        if skill_count != len(TEST_SKILLS):
            errors.append(
                f"Index has {skill_count} skills, expected {len(TEST_SKILLS)}"
            )

        if errors:
            detail = f"{merged}/{len(TEST_SKILLS)} merged"
            for err in errors:
                detail += f"\n  Error: {err}"
            return TestResult("Phase 3: Pass 1 merge", False, detail)

        detail = f"{merged}/{len(TEST_SKILLS)} merged, .pss files deleted"
        if verbose:
            detail += f"\n  Index skills: {list(index.get('skills', {}).keys())}"

        return TestResult("Phase 3: Pass 1 merge", True, detail)

    except Exception as e:
        return TestResult("Phase 3: Pass 1 merge", False, str(e))


def phase4_pass2_merge(env: dict[str, Any], verbose: bool) -> TestResult:
    """Phase 4: Test merge queue Pass 2 — co-usage data."""
    try:
        queue_dir: Path = env["queue_dir"]
        index_path: Path = env["index_path"]
        plugin_root: Path = env["plugin_root"]
        merge_script = plugin_root / "scripts" / "pss_merge_queue.py"

        merged = 0
        errors: list[str] = []

        for skill in TEST_SKILLS:
            pss_data = {
                "name": skill["name"],
                "co_usage": skill["co_usage"],
                "tier": skill["tier"],
                "pass": 2,
            }

            pss_file = queue_dir / f"{skill['name']}.pss"
            with open(pss_file, "w", encoding="utf-8") as f:
                json.dump(pss_data, f, indent=2)

            result = subprocess.run(
                [
                    sys.executable,
                    str(merge_script),
                    str(pss_file),
                    "--pass",
                    "2",
                    "--index",
                    str(index_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                errors.append(
                    f"{skill['name']}: exit {result.returncode} — {result.stderr[:200]}"
                )
            else:
                merged += 1

            if pss_file.exists():
                errors.append(f"{skill['name']}: .pss file not deleted after merge")

        # Verify co_usage in index
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)

        missing_co_usage: list[str] = []
        for skill_name, skill_data in index.get("skills", {}).items():
            if "co_usage" not in skill_data:
                missing_co_usage.append(skill_name)

        if missing_co_usage:
            errors.append(f"Skills missing co_usage: {missing_co_usage}")

        pass_field = index.get("pass", 0)
        if pass_field != 2:
            errors.append(f"Index pass field is {pass_field}, expected 2")

        if errors:
            detail = f"{merged}/{len(TEST_SKILLS)} merged"
            for err in errors:
                detail += f"\n  Error: {err}"
            return TestResult("Phase 4: Pass 2 merge", False, detail)

        detail = f"{merged}/{len(TEST_SKILLS)} with co_usage, .pss files deleted"
        if verbose:
            detail += f"\n  Index pass: {pass_field}"

        return TestResult("Phase 4: Pass 2 merge", True, detail)

    except Exception as e:
        return TestResult("Phase 4: Pass 2 merge", False, str(e))


def phase5_binary_scoring(env: dict[str, Any], verbose: bool) -> TestResult:
    """Phase 5: Test Rust binary direct — prompt matching."""
    try:
        binary_path: Path = env["binary_path"]
        fake_home: Path = env["fake_home"]

        # Build test input — simple prompt
        test_input = json.dumps({"prompt": "help me lint my python code with ruff"})

        # Call binary with HOME override so it finds our test index
        test_env = os.environ.copy()
        test_env["HOME"] = str(fake_home)

        result = subprocess.run(
            [str(binary_path)],
            input=test_input,
            capture_output=True,
            text=True,
            timeout=10,
            env=test_env,
        )

        if result.returncode != 0:
            return TestResult(
                "Phase 5: Binary scoring",
                False,
                f"Binary exit {result.returncode}: {result.stderr[:300]}",
            )

        # Verify output is valid JSON
        try:
            json.loads(result.stdout)
        except json.JSONDecodeError:
            return TestResult(
                "Phase 5: Binary scoring",
                False,
                f"Invalid JSON output: {result.stdout[:300]}",
            )

        # Check that test-python-linter appears somewhere in the output
        output_str = result.stdout.lower()
        if "test-python-linter" not in output_str:
            return TestResult(
                "Phase 5: Binary scoring",
                False,
                f"Expected test-python-linter in output, got: {result.stdout[:300]}",
            )

        detail = "test-python-linter matched for 'lint python code with ruff'"
        if verbose:
            detail += f"\n  Output: {result.stdout[:200]}"

        return TestResult("Phase 5: Binary scoring", True, detail)

    except subprocess.TimeoutExpired:
        return TestResult(
            "Phase 5: Binary scoring", False, "Binary timed out after 10s"
        )
    except Exception as e:
        return TestResult("Phase 5: Binary scoring", False, str(e))


def phase6_hook_simulation(env: dict[str, Any], verbose: bool) -> TestResult:
    """Phase 6: Test hook simulation — hook-format output for multiple prompts."""
    try:
        binary_path: Path = env["binary_path"]
        fake_home: Path = env["fake_home"]

        test_env = os.environ.copy()
        test_env["HOME"] = str(fake_home)

        matched = 0
        errors: list[str] = []

        for case in HOOK_TEST_CASES:
            prompt = case["prompt"]
            expected = case["expected_skill"]

            test_input = json.dumps({"prompt": prompt})

            result = subprocess.run(
                [
                    str(binary_path),
                    "--format",
                    "hook",
                    "--top",
                    "4",
                    "--min-score",
                    "0.1",
                ],
                input=test_input,
                capture_output=True,
                text=True,
                timeout=10,
                env=test_env,
            )

            if result.returncode != 0:
                errors.append(f"'{prompt}': binary exit {result.returncode}")
                continue

            # Verify JSON output
            try:
                json.loads(result.stdout)
            except json.JSONDecodeError:
                errors.append(f"'{prompt}': invalid JSON output")
                continue

            # Check expected skill appears in output
            if expected not in result.stdout.lower():
                errors.append(
                    f"'{prompt}': expected {expected}, got: {result.stdout[:200]}"
                )
                continue

            matched += 1
            if verbose:
                print(f"    '{prompt}' → {expected} [OK]")

        if errors:
            detail = f"{matched}/{len(HOOK_TEST_CASES)} prompts matched"
            for err in errors:
                detail += f"\n  Error: {err}"
            return TestResult("Phase 6: Hook simulation", False, detail)

        detail = f"{matched}/{len(HOOK_TEST_CASES)} prompts matched correct skills"
        return TestResult("Phase 6: Hook simulation", True, detail)

    except Exception as e:
        return TestResult("Phase 6: Hook simulation", False, str(e))


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run_all_tests(
    plugin_root: Path,
    verbose: bool = False,
    _state: dict[str, Any] | None = None,
) -> list[TestResult]:
    """Run all 6 test phases. Returns list of TestResult objects.

    This is the library entry point for pss_validate_plugin.py integration.

    Args:
        plugin_root: Path to the PSS plugin root directory.
        verbose: If True, print detailed output per phase.
        _state: Optional dict populated with internal state (e.g. temp_dir).
            Used by main() to retrieve the temp directory for cleanup.
    """
    results: list[TestResult] = []

    # Phase 1: Setup
    result1, env = phase1_setup(plugin_root, verbose)
    results.append(result1)

    # Expose temp_dir to caller via _state dict
    if _state is not None and env:
        _state["temp_dir"] = env.get("temp_dir")

    if not result1.passed or not env:
        # Can't continue without environment
        for name in [
            "Phase 2: Test skills created",
            "Phase 3: Pass 1 merge",
            "Phase 4: Pass 2 merge",
            "Phase 5: Binary scoring",
            "Phase 6: Hook simulation",
        ]:
            results.append(TestResult(name, False, "Skipped — Phase 1 failed"))
        return results

    # Phase 2: Create skills
    results.append(phase2_create_skills(env, verbose))

    # Phase 3: Pass 1 merge
    results.append(phase3_pass1_merge(env, verbose))

    # Phase 4: Pass 2 merge (depends on Phase 3)
    if results[-1].passed:
        results.append(phase4_pass2_merge(env, verbose))
    else:
        results.append(
            TestResult("Phase 4: Pass 2 merge", False, "Skipped — Phase 3 failed")
        )

    # Phase 5: Binary scoring (depends on Phase 3)
    if results[2].passed:  # Phase 3 result
        results.append(phase5_binary_scoring(env, verbose))
    else:
        results.append(
            TestResult("Phase 5: Binary scoring", False, "Skipped — Phase 3 failed")
        )

    # Phase 6: Hook simulation (depends on Phase 5)
    if len(results) >= 5 and results[4].passed:  # Phase 5 result
        results.append(phase6_hook_simulation(env, verbose))
    else:
        results.append(
            TestResult("Phase 6: Hook simulation", False, "Skipped — Phase 5 failed")
        )

    return results


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="PSS End-to-End Test")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output per phase"
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Don't cleanup temp directory (for debugging)",
    )
    parser.add_argument(
        "plugin_root",
        nargs="?",
        help="Plugin root path (default: parent of scripts/)",
    )
    args = parser.parse_args()

    # Determine plugin root
    if args.plugin_root:
        plugin_root = Path(args.plugin_root)
    else:
        plugin_root = Path(__file__).parent.parent

    if not plugin_root.is_dir():
        print(f"Error: {plugin_root} is not a directory", file=sys.stderr)
        return 1

    # Header
    print("PSS End-to-End Test")
    print("===================")

    # Run tests, capturing temp_dir via state dict
    state: dict[str, Any] = {}
    results = run_all_tests(plugin_root, args.verbose, _state=state)
    temp_dir: Path | None = state.get("temp_dir")

    # Print results
    passed_count = 0
    total_count = len(results)

    for r in results:
        tag = "[PASS]" if r.passed else "[FAIL]"
        print(f"{tag} {r.name} - {r.detail}")
        if r.passed:
            passed_count += 1

    print("------")
    print(f"Result: {passed_count}/{total_count} passed")

    # Cleanup temp directory (only our own, tracked by reference)
    if not args.keep_temp and temp_dir is not None and temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    elif args.keep_temp and temp_dir is not None:
        print(f"Temp directory kept at: {temp_dir}")

    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    sys.exit(main())
