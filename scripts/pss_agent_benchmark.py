#!/usr/bin/env python3
"""
PSS Agent Profiling Benchmark — Measures how well the scoring engine
suggests elements for agent .md definitions.

Scores 5 element types separately: skills, agents, commands, rules, MCP.
Each agent has gold-standard elements per type.

Fast mode: Uses Rust binary --agent-profile directly (seconds per agent).
Full mode: Runs complete /pss-setup-agent pipeline → .agent.toml (minutes per agent).

Usage:
    uv run scripts/pss_agent_benchmark.py [OPTIONS]
    uv run scripts/pss_agent_benchmark.py --prompts docs_dev/agent-benchmark-prompts-100.jsonl \
        --gold docs_dev/agent-benchmark-gold-100.json
    uv run scripts/pss_agent_benchmark.py --range 1-100 --verbose
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


# Per-type top-K limits (how many suggestions to consider per type)
TYPE_LIMITS = {
    "skills": 5,
    "agents": 10,
    "commands": 5,
    "rules": 3,
    "mcp": 3,
}

# Per-type gold quantities (expected gold count per agent)
GOLD_EXPECTED = {
    "skills": 5,
    "agents": 10,
    "commands": 5,
    "rules": 3,
    "mcp": 3,
}


def detect_binary() -> str:
    """Detect the platform-specific PSS binary path."""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    bin_dir = project_root / "bin"

    system = platform.system()
    machine = platform.machine()

    platform_map = {
        ("Darwin", "arm64"): "pss-darwin-arm64",
        ("Darwin", "x86_64"): "pss-darwin-x86_64",
        ("Linux", "x86_64"): "pss-linux-x86_64",
        ("Linux", "aarch64"): "pss-linux-arm64",
        ("Windows", "AMD64"): "pss-windows-x86_64.exe",
        ("Windows", "x86_64"): "pss-windows-x86_64.exe",
    }

    binary_name = platform_map.get((system, machine))
    if binary_name is None:
        # Fallback to release build
        release_bin = project_root / "rust" / "target" / "release" / "pss"
        if release_bin.exists():
            return str(release_bin)
        print(f"ERROR: Unsupported platform: {system}/{machine}", file=sys.stderr)
        sys.exit(1)

    binary_path = bin_dir / binary_name
    if not binary_path.exists():
        # Try release build as fallback
        release_bin = project_root / "rust" / "target" / "release" / "pss"
        if release_bin.exists():
            return str(release_bin)
        print(f"ERROR: Binary not found: {binary_path}", file=sys.stderr)
        sys.exit(1)

    return str(binary_path)


def run_agent_profile(
    binary: str, agent_name: str, prompt: str, cwd: str, timeout: int = 30
) -> dict[str, Any]:
    """Run the binary in --agent-profile mode for a single agent.

    Returns the parsed JSON output from the binary.
    """
    # Build the agent descriptor JSON
    descriptor = {
        "name": agent_name,
        "description": prompt[:4000],  # Truncate very long .md files
        "role": "",
        "duties": [],
        "tools": [],
        "domains": [],
        "requirements_summary": "",
        "cwd": cwd,
    }

    # Write descriptor to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, prefix="pss-bench-"
    ) as f:
        json.dump(descriptor, f)
        descriptor_path = f.name

    # Use file-based output to avoid SIGPIPE/exit-137 with large JSON output
    output_file = descriptor_path.replace(".json", "-out.json")
    try:
        with open(output_file, "w") as stdout_f, open(os.devnull, "w") as devnull:
            proc = subprocess.run(
                [
                    binary,
                    "--agent-profile",
                    descriptor_path,
                    "--format",
                    "json",
                    "--top",
                    "30",
                ],
                stdout=stdout_f,
                stderr=devnull,
                timeout=timeout,
            )
        if proc.returncode != 0:
            return {}
        with open(output_file) as f:
            return json.load(f)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return {}
    finally:
        os.unlink(descriptor_path)
        if os.path.exists(output_file):
            os.unlink(output_file)


def extract_names_from_profile(profile: dict[str, Any]) -> dict[str, list[str]]:
    """Extract element names from --agent-profile JSON output, grouped by type.

    Returns dict with keys: skills, agents, commands, rules, mcp
    """
    result: dict[str, list[str]] = {
        "skills": [],
        "agents": [],
        "commands": [],
        "rules": [],
        "mcp": [],
    }

    # Skills: combine primary + secondary + specialized, take top TYPE_LIMITS["skills"]
    skills_section = profile.get("skills", {})
    all_skills: list[str] = []
    for tier in ("primary", "secondary", "specialized"):
        tier_items = skills_section.get(tier, [])
        for item in tier_items:
            name = item.get("name", "") if isinstance(item, dict) else str(item)
            if name and name not in all_skills:
                all_skills.append(name)
    result["skills"] = all_skills[: TYPE_LIMITS["skills"]]

    # Complementary agents
    comp_agents = profile.get("complementary_agents", [])
    agent_names: list[str] = []
    for item in comp_agents:
        name = item.get("name", "") if isinstance(item, dict) else str(item)
        if name and name not in agent_names:
            agent_names.append(name)
    result["agents"] = agent_names[: TYPE_LIMITS["agents"]]

    # Commands, rules, mcp
    for key in ("commands", "rules", "mcp"):
        items = profile.get(key, [])
        names: list[str] = []
        for item in items:
            name = item.get("name", "") if isinstance(item, dict) else str(item)
            if name and name not in names:
                names.append(name)
        result[key] = names[: TYPE_LIMITS[key]]

    return result


def score_agent(
    suggested: dict[str, list[str]], gold: dict[str, list[str]]
) -> dict[str, int]:
    """Score a single agent's suggestions against gold, per type.

    Returns dict with hit counts per type.
    """
    hits: dict[str, int] = {}
    for etype in TYPE_LIMITS:
        gold_set = set(gold.get(etype, []))
        suggested_list = suggested.get(etype, [])
        hits[etype] = sum(1 for s in suggested_list if s in gold_set)
    return hits


def run_benchmark(
    prompts_path: str,
    gold_path: str,
    binary: str,
    verbose: bool = False,
    agent_range: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Run the full agent benchmark.

    Returns aggregate results.
    """
    # Load data
    with open(gold_path) as f:
        gold_data = json.load(f)

    with open(prompts_path) as f:
        prompt_lines = [line.strip() for line in f if line.strip()]

    # Aggregate counters
    total_hits: dict[str, int] = {k: 0 for k in TYPE_LIMITS}
    total_max: dict[str, int] = {k: 0 for k in TYPE_LIMITS}
    per_agent_results: list[dict[str, Any]] = []

    for line in prompt_lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        agent_id = entry.get("id", 0)

        # Apply range filter
        if agent_range is not None:
            if agent_id < agent_range[0] or agent_id > agent_range[1]:
                continue

        agent_name = entry.get("agent_name", f"agent-{agent_id}")
        prompt = entry.get("prompt", "")
        cwd = entry.get("cwd", "/tmp")
        gold_key = str(agent_id)

        if gold_key not in gold_data:
            if verbose:
                print(f"  WARNING: No gold data for agent {agent_id}", file=sys.stderr)
            continue

        gold = gold_data[gold_key]

        # Run binary
        profile = run_agent_profile(binary, agent_name, prompt, cwd)
        suggested = extract_names_from_profile(profile)

        # Score
        hits = score_agent(suggested, gold)

        # Accumulate
        agent_result = {
            "id": agent_id,
            "name": agent_name,
            "hits": {},
            "suggested": {},
            "gold": {},
        }
        for etype in TYPE_LIMITS:
            gold_count = len(gold.get(etype, []))
            total_hits[etype] += hits[etype]
            total_max[etype] += gold_count
            agent_result["hits"][etype] = hits[etype]
            agent_result["suggested"][etype] = suggested.get(etype, [])
            agent_result["gold"][etype] = gold.get(etype, [])

        per_agent_results.append(agent_result)

        if verbose:
            type_scores = " | ".join(
                f"{k}:{hits[k]}/{len(gold.get(k, []))}" for k in TYPE_LIMITS
            )
            print(f"  A{agent_id}: {type_scores}")

    # Summary
    combined_hits = sum(total_hits.values())
    combined_max = sum(total_max.values())

    return {
        "total_hits": total_hits,
        "total_max": total_max,
        "combined_hits": combined_hits,
        "combined_max": combined_max,
        "agent_count": len(per_agent_results),
        "per_agent": per_agent_results,
    }


def print_results(
    results: dict[str, Any], label: str = "Agent Profiling Benchmark"
) -> None:
    """Print formatted benchmark results."""
    print(f"\n{label}")
    print("=" * len(label))

    total_hits = results["total_hits"]
    total_max = results["total_max"]

    for etype in TYPE_LIMITS:
        hits = total_hits[etype]
        mx = total_max[etype]
        pct = (hits / mx * 100) if mx > 0 else 0
        print(f"  {etype:10}: {hits:4}/{mx:4} ({pct:5.1f}%)")

    combined = results["combined_hits"]
    combined_max = results["combined_max"]
    pct = (combined / combined_max * 100) if combined_max > 0 else 0
    print(f"  {'combined':10}: {combined:4}/{combined_max:4} ({pct:5.1f}%)")
    print(f"  Agents scored: {results['agent_count']}")


def save_per_agent_results(results: dict[str, Any], output_path: str) -> None:
    """Save per-agent results to a text file."""
    with open(output_path, "w") as f:
        f.write("# Agent Profiling Benchmark - Per-Agent Results\n\n")

        total_hits = results["total_hits"]
        total_max = results["total_max"]

        f.write("## Aggregate Scores\n")
        for etype in TYPE_LIMITS:
            hits = total_hits[etype]
            mx = total_max[etype]
            f.write(f"  {etype:10}: {hits}/{mx}\n")
        f.write(
            f"  combined  : {results['combined_hits']}/{results['combined_max']}\n\n"
        )

        f.write("## Per-Agent Details\n\n")
        for agent in results["per_agent"]:
            f.write(f"### A{agent['id']} ({agent['name']})\n")
            for etype in TYPE_LIMITS:
                hits = agent["hits"][etype]
                gold = agent["gold"][etype]
                suggested = agent["suggested"][etype]
                gold_count = len(gold)
                f.write(f"  {etype}: {hits}/{gold_count}\n")
                f.write(f"    suggested: {suggested}\n")
                f.write(f"    gold:      {gold}\n")
                # Show misses
                misses = [g for g in gold if g not in suggested]
                if misses:
                    f.write(f"    MISSED:    {misses}\n")
            f.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="PSS Agent Profiling Benchmark")
    parser.add_argument(
        "--prompts",
        default="docs_dev/agent-benchmark-prompts-100.jsonl",
        help="Path to agent prompts JSONL file",
    )
    parser.add_argument(
        "--gold",
        default="docs_dev/agent-benchmark-gold-100.json",
        help="Path to gold answers JSON file",
    )
    parser.add_argument(
        "--binary", default=None, help="Path to PSS binary (auto-detected if not set)"
    )
    parser.add_argument(
        "--range",
        default=None,
        help="Agent ID range to benchmark (e.g., '1-100', '101-200')",
    )
    parser.add_argument("--output", default=None, help="Save per-agent results to file")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print per-agent results"
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    # Resolve binary
    binary = args.binary or detect_binary()
    if not os.path.isfile(binary):
        print(f"ERROR: Binary not found: {binary}", file=sys.stderr)
        sys.exit(1)

    # Resolve paths relative to project root
    project_root = Path(__file__).resolve().parent.parent
    prompts_path = (
        str(project_root / args.prompts)
        if not os.path.isabs(args.prompts)
        else args.prompts
    )
    gold_path = (
        str(project_root / args.gold) if not os.path.isabs(args.gold) else args.gold
    )

    if not os.path.isfile(prompts_path):
        print(f"ERROR: Prompts file not found: {prompts_path}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(gold_path):
        print(f"ERROR: Gold file not found: {gold_path}", file=sys.stderr)
        sys.exit(1)

    # Parse range
    agent_range = None
    if args.range:
        parts = args.range.split("-")
        if len(parts) == 2:
            agent_range = (int(parts[0]), int(parts[1]))
        else:
            agent_range = (int(parts[0]), int(parts[0]))

    print(f"Binary: {binary}")
    print(f"Prompts: {prompts_path}")
    print(f"Gold: {gold_path}")
    if agent_range:
        print(f"Range: {agent_range[0]}-{agent_range[1]}")

    results = run_benchmark(
        prompts_path, gold_path, binary, verbose=args.verbose, agent_range=agent_range
    )

    if args.json:
        # Strip per_agent for compact output
        compact = {k: v for k, v in results.items() if k != "per_agent"}
        print(json.dumps(compact, indent=2))
    else:
        print_results(results)

    if args.output:
        save_per_agent_results(results, args.output)
        print(f"\nPer-agent results saved to: {args.output}")


if __name__ == "__main__":
    main()
