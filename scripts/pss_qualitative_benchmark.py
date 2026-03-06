#!/usr/bin/env python3
"""
PSS Qualitative Agent Profile Benchmark — Phase 1: Generate evaluation tasks.

Runs PSS on random agent samples and writes evaluation task files that can be
fed to Claude Code subagents for qualitative review.

Phase 1 (this script): Run PSS, generate eval task files in docs_dev/qual-eval/
Phase 2 (orchestrator): Spawn subagents to evaluate each task file
Phase 3 (orchestrator): Spawn aggregation subagent to synthesize findings

Usage:
    uv run scripts/pss_qualitative_benchmark.py --sample 20
    uv run scripts/pss_qualitative_benchmark.py --agents 1,5,12,50
    uv run scripts/pss_qualitative_benchmark.py --sample 20 --seed 42
"""

import argparse
import json
import os
import platform
import random
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Binary detection ─────────────────────────────────────────────────────────


def detect_binary(project_root: Path) -> str:
    """Detect the platform-specific PSS binary path."""
    bin_dir = project_root / "rust" / "skill-suggester" / "bin"
    system = platform.system()
    machine = platform.machine()
    platform_map = {
        ("Darwin", "arm64"): "pss-darwin-arm64",
        ("Darwin", "x86_64"): "pss-darwin-x86_64",
        ("Linux", "x86_64"): "pss-linux-x86_64",
        ("Linux", "aarch64"): "pss-linux-arm64",
    }
    binary_name = platform_map.get((system, machine))
    if binary_name:
        p = bin_dir / binary_name
        if p.exists():
            return str(p)
    release = project_root / "rust" / "skill-suggester" / "target" / "release" / "pss"
    if release.exists():
        return str(release)
    print(f"ERROR: No binary found for {system}/{machine}", file=sys.stderr)
    sys.exit(1)


# ── PSS execution ───────────────────────────────────────────────────────────


def run_agent_profile(
    binary: str, agent_name: str, prompt: str, cwd: str, timeout: int = 30
) -> dict[str, Any]:
    """Run PSS binary in --agent-profile mode. Returns parsed JSON output."""
    descriptor = {
        "name": agent_name,
        "description": prompt[:4000],
        "role": "",
        "duties": [],
        "tools": [],
        "domains": [],
        "requirements_summary": "",
        "cwd": cwd,
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, prefix="pss-qual-"
    ) as f:
        json.dump(descriptor, f)
        descriptor_path = f.name

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


def format_suggestions(profile: dict[str, Any]) -> str:
    """Format PSS output into a readable markdown string for evaluation."""
    lines: list[str] = []

    # Skills by tier
    skills_section = profile.get("skills", {})
    for tier in ("primary", "secondary", "specialized"):
        items = skills_section.get(tier, [])
        if items:
            lines.append(f"\n### Skills ({tier}) — {len(items)} items")
            for item in items[:10]:
                if isinstance(item, dict):
                    name = item.get("name", "?")
                    score = item.get("score", 0)
                    desc = item.get("description", "")[:150]
                    conf = item.get("confidence", "?")
                    lines.append(f"  - **{name}** (score: {score:.3f}, {conf})")
                    if desc:
                        lines.append(f"    _{desc}_")

    # Complementary agents
    agents = profile.get("complementary_agents", [])
    if agents:
        lines.append(
            f"\n### Complementary Agents — {len(agents)} total (showing top 10)"
        )
        for item in agents[:10]:
            if isinstance(item, dict):
                name = item.get("name", "?")
                score = item.get("score", 0)
                desc = item.get("description", "")[:150]
                conf = item.get("confidence", "?")
                lines.append(f"  - **{name}** (score: {score:.3f}, {conf})")
                if desc:
                    lines.append(f"    _{desc}_")

    # Commands
    commands = profile.get("commands", [])
    if commands:
        lines.append(f"\n### Commands — {len(commands)} total")
        for item in commands[:10]:
            if isinstance(item, dict):
                name = item.get("name", "?")
                score = item.get("score", 0)
                desc = item.get("description", "")[:150]
                lines.append(f"  - **{name}** (score: {score:.3f}) — {desc}")

    # Rules
    rules = profile.get("rules", [])
    if rules:
        lines.append(f"\n### Rules — {len(rules)} total")
        for item in rules:
            if isinstance(item, dict):
                name = item.get("name", "?")
                desc = item.get("description", "")[:150]
                lines.append(f"  - **{name}** — {desc}")

    # MCP servers
    mcps = profile.get("mcp", [])
    if mcps:
        lines.append(f"\n### MCP Servers — {len(mcps)} total")
        for item in mcps:
            if isinstance(item, dict):
                name = item.get("name", "?")
                desc = item.get("description", "")[:150]
                lines.append(f"  - **{name}** — {desc}")

    return "\n".join(lines)


# ── Evaluation task file generation ──────────────────────────────────────────

EVAL_INSTRUCTIONS = """You are an expert evaluator of AI agent configurations. You are reviewing the output
of PSS (Perfect Skill Suggester), a tool that suggests relevant skills, agents, commands,
rules, and MCP servers for a Claude Code agent based on its definition.

## Your Task

Read the agent definition below, then review each category of PSS suggestions.
For each category (Skills, Agents, Commands, Rules, MCP), evaluate:

1. **Quality grade** (A/B/C/D/F) — how well do the suggestions serve this agent?
2. **Irrelevant items** — list any that don't belong (name + why wrong)
3. **Critical missing items** — important elements that should be suggested but aren't
4. **Ranking issues** — are the top items actually the best choices?
5. **Root cause hypothesis** — WHY is the algorithm making this mistake?
   (keyword mismatch? wrong domain? missing synonym? co-usage gap? over-broad query?)

Then provide an **Overall Assessment**:
- 1-sentence biggest problem
- Top 3 concrete algorithm improvements that would fix the most issues

Be concise but specific — always name exact elements."""


def write_eval_task(
    output_dir: Path,
    agent_id: int,
    agent_name: str,
    agent_definition: str,
    suggestions_text: str,
) -> Path:
    """Write an evaluation task file for a single agent."""
    filename = f"eval-A{agent_id:03d}-{agent_name}.md"
    filepath = output_dir / filename

    with open(filepath, "w") as f:
        f.write(f"# Evaluation Task: A{agent_id} — {agent_name}\n\n")
        f.write(f"{EVAL_INSTRUCTIONS}\n\n")
        f.write("---\n\n")
        f.write("## Agent Definition\n\n")
        f.write(f"**Name:** {agent_name}\n\n")
        f.write(agent_definition[:3000])
        f.write("\n\n---\n\n")
        f.write("## PSS Suggestions\n")
        f.write(suggestions_text)
        f.write("\n\n---\n\n")
        f.write("## Your Evaluation\n\n")
        f.write("(Write your evaluation below)\n")

    return filepath


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PSS Qualitative Benchmark — Phase 1: Generate evaluation tasks"
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=20,
        help="Number of random agents to evaluate (default: 20)",
    )
    parser.add_argument(
        "--agents",
        type=str,
        default=None,
        help="Specific agent IDs (comma-separated, e.g., '1,5,12')",
    )
    parser.add_argument(
        "--prompts",
        default="docs_dev/agent-benchmark-prompts-100.jsonl",
        help="Path to agent prompts JSONL file",
    )
    parser.add_argument(
        "--binary", default=None, help="Path to PSS binary (auto-detected if not set)"
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for eval tasks (default: docs_dev/qual-eval-TIMESTAMP/)",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducible sampling"
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress per-agent progress, print only final summary + manifest path",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    binary = args.binary or detect_binary(project_root)
    prompts_path = (
        str(project_root / args.prompts)
        if not os.path.isabs(args.prompts)
        else args.prompts
    )

    if not os.path.isfile(prompts_path):
        print(f"ERROR: Prompts file not found: {prompts_path}", file=sys.stderr)
        sys.exit(1)

    # Load all agents
    with open(prompts_path) as f:
        all_agents = [json.loads(line.strip()) for line in f if line.strip()]

    # Select agents
    if args.agents:
        agent_ids = {int(x.strip()) for x in args.agents.split(",")}
        selected = [a for a in all_agents if a.get("id") in agent_ids]
    else:
        if args.seed is not None:
            random.seed(args.seed)
        selected = random.sample(all_agents, min(args.sample, len(all_agents)))

    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = project_root / "docs_dev" / f"qual-eval-{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.quiet:
        print(f"Binary: {binary}")
        print(f"Agents: {len(selected)} selected")
        print(f"Output: {output_dir}")
        print()

    # Run PSS and generate eval tasks
    task_files: list[str] = []
    manifest: list[dict[str, Any]] = []

    for i, agent in enumerate(selected):
        agent_id = agent.get("id", 0)
        agent_name = agent.get("agent_name", f"agent-{agent_id}")
        prompt = agent.get("prompt", "")
        cwd = agent.get("cwd", "/tmp")

        if not args.quiet:
            print(
                f"[{i + 1}/{len(selected)}] {agent_name} (A{agent_id})...",
                end=" ",
                flush=True,
            )

        profile = run_agent_profile(binary, agent_name, prompt, cwd)
        if not profile:
            if not args.quiet:
                print("SKIP (binary failed)")
            continue

        suggestions_text = format_suggestions(profile)
        filepath = write_eval_task(
            output_dir, agent_id, agent_name, prompt, suggestions_text
        )
        task_files.append(str(filepath))
        manifest.append(
            {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "eval_file": str(filepath),
            }
        )
        if not args.quiet:
            print("OK")

    # Write manifest for orchestrator
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(
            {
                "timestamp": timestamp,
                "binary": binary,
                "agent_count": len(manifest),
                "agents": manifest,
                "output_dir": str(output_dir),
            },
            f,
            indent=2,
        )

    # Always print final summary (works for both quiet and verbose modes)
    print(
        f"[DONE] qualitative-benchmark - {len(manifest)} eval tasks generated. Manifest: {manifest_path}"
    )

    if not args.quiet:
        print(f"\nGenerated {len(task_files)} evaluation tasks in: {output_dir}")
        print(f"Manifest: {manifest_path}")
        print(
            "\nNext: Spawn subagents to evaluate each task file, then aggregate results."
        )


if __name__ == "__main__":
    main()
