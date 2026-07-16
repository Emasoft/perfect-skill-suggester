<p align="center">
  <img src="resources/perfect_skill_suggester_logo_header.jpeg" alt="Perfect Skill Suggester" width="800" />
</p>

# Perfect Skill Suggester (PSS)

<!--BADGES-START-->
![Version](https://img.shields.io/badge/version-3.10.1-blue)
![Platforms](https://img.shields.io/badge/platforms-5-green)
![Accuracy](https://img.shields.io/badge/accuracy-88%25+-brightgreen)
![License](https://img.shields.io/badge/license-MIT-yellow)
![Rust](https://img.shields.io/badge/rust-native_binary-orange)
![Claude Code](https://img.shields.io/badge/claude--code-v2.1.69--v2.1.112-blueviolet)
<!--BADGES-END-->

> **Installation:** This plugin is distributed via the [Emasoft Plugins Marketplace](https://github.com/Emasoft/emasoft-plugins).
> See [Installation](#installation) below for instructions.
>
> **Claude Code version support:** PSS tracks CC compatibility in
> [`docs/CC-COMPATIBILITY.md`](docs/CC-COMPATIBILITY.md) — see it for the full
> version-by-version matrix, declared hook events, and migration notes.
>
> ---
>
> Built for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) |
> Orchestrated by [AI Maestro](https://github.com/Emasoft/ai-maestro) |
> Part of the [Emasoft Plugins](https://github.com/Emasoft/emasoft-plugins) ecosystem

**High-accuracy skill activation (88%+) for Claude Code** with AI-analyzed keywords, weighted scoring, synonym expansion, and three-tier confidence routing. Indexes 6 element types: skills, agents, commands, rules, MCP servers, and LSP servers — 874+ elements including 246 MCP servers.

## What's New (last 3 releases)

### v3.6.12 — 2026-05-16
- **rust:** Bump submodule for F-12 `version-history` subcommand — focused "what versions has this element gone through?" history, filtered to signal events (installed, content_changed, description_changed, removed) with content hash and diff JSON per row.

### v3.6.11 — 2026-05-16
- **rust:** Bump submodule for F-17 / F-18 / F-19 Tier B subcommands — `changes-in-batch`, `last-changes`, and `stats-by-scope` for inspecting a single reindex's event set and counting elements per scope.

### v3.6.10 — 2026-05-16
- **rust:** Bump submodule for F-6 `scope-diff` + UX-6 similarity score — surfaces what's in scope A but not in scope B (and vice versa), plus a similarity score on `pss compare` output.

Full history: [CHANGELOG.md](CHANGELOG.md)

## Features

### Multi-Type Element Indexing
Indexes all 6 Claude Code element types — not just skills. The unified index powers both real-time hook suggestions and AI-driven agent configuration profiling.

### Cross-Client Skill Discovery
Scans skills from **27 known AI clients** beyond Claude Code — including Codex, Copilot, Gemini, Kiro, Roo, Trae, Qwen, OpenHands, and more. Follows the [AgentSkills](https://agentskills.io) open standard for cross-client interoperability. Skills with `metadata` fields (language, framework, platform, tags) get authoritative domain gates for more precise matching.

### AI-Analyzed Keywords
Sonnet subagents analyze each element's source file to extract optimal activation patterns. Instead of relying on manually defined keywords, the AI reads the content and determines what user prompts should trigger it.

### MCP Server Auto-Discovery
Automatically discovers and indexes MCP servers from installed marketplace plugins (~250+ servers). Each MCP server entry includes AI-extracted tools, domain gates, patterns, and multi-word keyword phrases for precise matching.

### Native Rust Binary (~10ms)
A pre-compiled Rust binary handles all matching logic, keeping hook latency minimal. No Python interpreter startup, no JIT compilation - just fast native code.

### Synonym Expansion (70+ patterns)
User prompts are expanded with synonyms before matching. For example:
- `"pr"` → `"github pull request"`
- `"403"` → `"oauth2 authentication"`
- `"db"` → `"database"`
- `"ci"` → `"cicd deployment automation"`

### 5-Tier Logarithmic Scoring
Each match signal occupies a tier that is **10x more powerful** than the one below it. A single tool match always outranks any number of generic keyword matches. See [How It Works](#how-it-works) for the full rationale.

| Tier | Range | Examples |
|------|-------|----------|
| T1 | 10-90 | Common words: "test", "build", "debug" |
| T2 | 100-900 | Specific keywords/phrases |
| T3 | 1,000-9,000 | Tool names: bun, webpack, docker |
| T4 | 10,000-90,000 | Frameworks: react, django, flutter |
| T5 | 100,000-900,000 | Services/APIs: aws, openai, stripe |

### Binary Filters (Languages, Platforms, Domains)
When the prompt mentions a language, platform, or domain, skills locked to a different value are **excluded entirely** (not penalized). A Rust-only skill never appears for a Python prompt, regardless of other matches.

### Commitment Mechanism
For HIGH confidence matches, output includes an evaluation reminder prompting Claude to pause and assess whether the skill truly fits the user's needs before blindly following instructions.

### Skills-First Ordering
In the hook output, matched skills appear before other context types, ensuring Claude sees relevant skills prominently.

### Fuzzy/Typo Tolerance (Damerau-Levenshtein)
Typos and transpositions are automatically corrected:
- `"gti"` matches `"git"` (transposition = 1 edit)
- `"dokcer"` matches `"docker"` (typo = 1 edit)
- Adaptive thresholds: 1 edit for short words, 2 for medium, 3 for long

### Task Decomposition
Complex multi-task prompts are automatically split and matched separately:
- `"set up docker and then configure ci"` → 2 sub-tasks
- Detects: conjunctions, semicolons, numbered/bulleted lists
- Scores are aggregated across sub-tasks

### Activation Logging
Privacy-preserving JSONL logs at `~/.claude/logs/pss-activations.jsonl`:
- Prompts truncated to 100 chars with SHA-256 hash
- Automatic rotation at ~10,000 entries
- Disable with `PSS_NO_LOGGING=1` env var

### Per-Skill Configuration (.pss files)
Each skill can have a `.pss` file for custom matching rules:
- Additional keywords beyond AI-analyzed defaults
- Negative keywords to prevent false matches
- Tier (primary/secondary/utility) for priority
- Score boost (-10 to +10)

### Persistent State via `${CLAUDE_PLUGIN_DATA}` (CC v2.1.78+)
PSS uses the `${CLAUDE_PLUGIN_DATA}` environment variable (introduced in Claude Code v2.1.78) as the persistent data directory for `skill-index.json` and the CozoDB database. This ensures plugin state survives across sessions and plugin updates. Falls back to `~/.claude/cache/` on older Claude Code versions.

## CLI Reference

PSS ships a native `pss` binary with **62 subcommands** spread across 6 categories. The same binary that powers the `UserPromptSubmit` hook is also a fully scriptable CLI for inspecting the index, querying installation history, running ad-hoc searches, and maintaining the database. Every subcommand prints human-readable tables by default and accepts `--json` (or `--format json`) for piping into other tools.

| Category | # cmds | Examples |
|---|---|---|
| Search & inspect | 12 | `pss search`, `pss list`, `pss inspect`, `pss stats`, `pss get-description` |
| Find by attribute | 7 | `pss find-by-name`, `pss find-by-language`, `pss find-by-framework` |
| Lifecycle filters | 3 | `pss list-added-since`, `pss list-added-between`, `pss list-updated-since` |
| Temporal queries | 30 | `pss as-of`, `pss timeline`, `pss version-history`, `pss diff`, `pss compare-snapshots` |
| Indexing & maintenance | 9 | `pss reindex`, `pss db-stats`, `pss retention`, `pss prune-history`, `pss export` |
| Internal flags | 3 | `--pass1-batch`, `--index-file`, `--extract-prev-msg` (used by the hook) |

### Canonical one-liners

```bash
# What's currently installed (any element type)?
pss list

# Full-text search across name, description, and keywords
pss search "rate limit"

# What was installed and active on a specific date?
pss as-of 2026-01-01

# Full event history for one element (installs, content changes, removals)
pss timeline pss-usage

# Find every element provided by one plugin
pss by-plugin perfect-skill-suggester

# Catch accidental duplicates (same name in 2+ scopes)
pss dedup-candidates --type skill
```

See [docs/pss-cli-reference.md](docs/pss-cli-reference.md) for every subcommand, every flag, and example output.

## Requirements

PSS runs on **macOS, Linux, and Windows**. Before installing, make sure the following are on your `PATH`:

| Tool | Why | Install |
|------|-----|---------|
| [`uv`](https://docs.astral.sh/uv/) | Hooks invoke Python via `uv run --script`. `uv` reads PEP 723 inline metadata in `scripts/pss_hook.py` and provisions a cached venv with `pycozo[embedded]` the first time the hook runs. Cross-platform. | macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh \| sh`. Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| Python ≥ 3.10 | Required by `uv run` for the hook scripts | `uv python install 3.10` (uv manages this automatically) |
| `git` | Indexer discovers skills across marketplaces (standard git clone/pull) | Pre-installed on most systems |

No other runtime packages need manual install — everything pycozo-related (pycozo, cozo-embedded RocksDB, numpy, pandas if used) is provisioned into uv's cache on the first `UserPromptSubmit` or `SessionStart` hook invocation (~2–5 s cold, <100 ms warm thereafter).

**Windows note**: `uv` and its cached venvs are fully cross-platform — `uv run --script` handles the `.venv/Scripts/python.exe` vs `.venv/bin/python` split internally, so `hooks/hooks.json` is identical on every OS.

## Installation (Production)

Install from the Emasoft marketplace. Use `--scope user` to install for all Claude Code instances, or `--scope global` for all projects.

```bash
# Add Emasoft marketplace (first time only)
claude plugin marketplace add emasoft-plugins --url https://github.com/Emasoft/emasoft-plugins

# Install plugin (--scope user = all Claude Code instances, recommended for utility plugins)
claude plugin install perfect-skill-suggester@emasoft-plugins --scope user

# RESTART Claude Code after installing (required!)
```

Utility plugins are installed once with `--scope user` and become available to all Claude Code instances.

This is a utility plugin — it provides skill suggestion hooks. No `--agent` flag needed; just start Claude Code normally and the skill suggestions will activate automatically via hooks.

## Development Only (--plugin-dir)

`--plugin-dir` loads a plugin directly from a local directory without marketplace installation. Use only during plugin development.

```bash
claude --plugin-dir ./perfect-skill-suggester
```

## Update

To update to the latest version:

```bash
# Step 1: Update marketplace cache
claude plugin marketplace update emasoft-plugins

# Step 2: Uninstall current version
claude plugin uninstall perfect-skill-suggester@emasoft-plugins

# Step 3: Install latest version
claude plugin install perfect-skill-suggester@emasoft-plugins

# Step 4: Restart Claude Code (REQUIRED)
```

**Important:** You MUST restart Claude Code after updating. The plugin's hook paths include the version number, and the running session caches the old paths until restarted.

## Uninstall

```bash
# Step 1: Uninstall
claude plugin uninstall perfect-skill-suggester@emasoft-plugins

# Step 2: Restart Claude Code
```

## Troubleshooting

### Hook path not found after version update

**Symptom:** After updating, you see:
```
UserPromptSubmit operation blocked by hook:
can't open file '.../perfect-skill-suggester/1.2.1/scripts/pss_hook.py': No such file or directory
```

**Cause:** Claude Code caches hook paths with version numbers. After updating from 1.2.1 to 1.2.2, the session still references the old 1.2.1 path.

**Solution:** Restart Claude Code. If that doesn't work, do a clean reinstall:
```bash
rm -rf ~/.claude/plugins/cache/emasoft-plugins/perfect-skill-suggester/
claude plugin uninstall perfect-skill-suggester@emasoft-plugins
claude plugin install perfect-skill-suggester@emasoft-plugins
# Then restart Claude Code
```

### Old version still installed after update

**Symptom:** `claude plugin list` shows old version even after update commands.

**Solution:** Clear cache and reinstall:
```bash
rm -rf ~/.claude/plugins/cache/emasoft-plugins/
claude plugin uninstall perfect-skill-suggester@emasoft-plugins
claude plugin install perfect-skill-suggester@emasoft-plugins
claude plugin list | grep perfect-skill  # Verify new version
# Then restart Claude Code
```

### Plugin disappears after installing another plugin

**Symptom:** `claude plugin update perfect-skill-suggester@emasoft-plugins` fails with `Plugin is not installed`, even though it was working before.

**Cause:** Claude Code 2.1.69+ uses `installed_plugins.json` **version 2** format. If any tool writes a v1-format entry into this file, Claude Code detects the malformed entry during its next sync and **rebuilds the file from its own internal state** — dropping plugins that were installed via marketplace or other mechanisms.

**v2 format** (correct — each plugin maps to a **list** of scope entries):
```json
{
  "version": 2,
  "plugins": {
    "plugin-name@marketplace": [
      {
        "scope": "user",
        "installPath": "/path/to/cache/marketplace/plugin/version",
        "version": "1.0.0",
        "installedAt": "2026-01-01T00:00:00.000Z",
        "lastUpdated": "2026-01-01T00:00:00.000Z",
        "gitCommitSha": "abc123..."
      }
    ]
  }
}
```

**v1 format** (WRONG — flat dict per plugin, causes corruption):
```json
{
  "plugin-name@marketplace": {
    "version": "1.0.0",
    "isLocal": true
  }
}
```

**Solution:** Reinstall the plugin:
```bash
claude plugin marketplace update emasoft-plugins
claude plugin install perfect-skill-suggester@emasoft-plugins
# Then restart Claude Code
```

**Prevention:** Any script that writes to `~/.claude/plugins/installed_plugins.json` MUST use v2 format (list of scope entries per plugin key, with `"version": 2` at root level). See the [Architecture docs](docs/PSS-ARCHITECTURE.md) for the full schema.

### Commands not found

**Symptom:** `/pss-reindex-skills` or `/pss-status` not recognized.

**Solution:** Restart Claude Code. Commands are only loaded at startup.

### No skill suggestions appear

**Symptom:** Plugin is installed but no skills are suggested.

**Solutions:**
1. Run `/pss-reindex-skills` to generate the skill index
2. Check the index exists: `ls ~/.claude/cache/skill-index.json` (on Claude Code v2.1.78+, the index may be at `${CLAUDE_PLUGIN_DATA}/skill-index.json` instead, with fallback to `~/.claude/cache/`)
3. Verify plugin is enabled: `claude plugin list`

### Binary not found for platform

**Symptom:** Error about missing platform binary.

**Solution:** Pre-built binaries are included for all major platforms. If yours is missing:
```bash
cd rust/skill-suggester
cargo build --release
# Copy binary to bin/ with appropriate name
```

## Quick Start

### 1. Generate Skill Index

Run the reindex command to build the skill index:

```
/pss-reindex-skills
```

This runs the 3-stage Rust pipeline (discover → enrich → merge) to index all elements. Completes in under 10 seconds.

### 2. Check Status

```
/pss-status
```

View index statistics, cache validity, and scoring configuration.

### 3. Use Naturally

Just type your requests naturally. PSS will suggest relevant skills based on weighted keyword matching:

```
"help me set up github actions"
→ Suggests: devops-expert (HIGH confidence)
```

## How It Works

### Pipeline

```
User prompt
  |
  v
Phase 1: Synonym Expansion (70+ rules)
  "pr" -> "github pull request"
  "db" -> "database"
  |
  v
Phase 2: 5-Tier Logarithmic Scoring + Binary Filters
  Score each skill using tool/framework/service/keyword matches.
  Exclude skills that fail language/platform/domain filters.
  |
  v
Phase 3: Confidence Classification
  HIGH (>= 1000) / MEDIUM (>= 100) / LOW (< 100)
```

### Why PSS used to keep two indexes — and what changed in v3.0

Through v2.10.x PSS maintained a **dual-store** element index: `skill-index.json` (canonical source of truth read by every cold-path script) and `pss-skill-index.db` (CozoDB derived runtime cache used by the hot-path Rust scorer). Both lived under `$CLAUDE_PLUGIN_DATA` (CC v2.1.78+) or `~/.claude/cache/` as fallback.

The dual-store design was well-motivated in principle — `git diff skill-index.json` was a real debugging tool, and Python didn't need a native CozoDB binding. But in April 2026 a real-world bug (`tailwind-4-docs` would sometimes vanish between reindexes when `$CLAUDE_PLUGIN_DATA` leaked across plugin scopes) made the drift between the two stores very visible. After auditing the five Python scripts that read JSON and the two that wrote it, the dual-store invariant was harder to enforce than a single-store one.

**v3.0 (Phase C of the CozoDB unification migration, TRDD-46ac514e)** promotes CozoDB to the single canonical store. All five Python scripts (`pss_merge_queue`, `pss_make_plugin`, `pss_verify_profile`, `pss_generate`, `pss_hook`) now read exclusively from CozoDB via `pycozo[embedded]`. The `--build-db` Rust subcommand is removed; the Python merge writer populates CozoDB directly under the same `fcntl.LOCK_EX` lock that previously guarded the JSON write.

**What this means for users:**

- Runtime behaviour is **unchanged** — the hook still reads CozoDB the same way, latency is still ~10 ms, suggestions are still the same quality.
- `skill-index.json` is **no longer automatically maintained**. It may be left behind from a prior install, but no Python or Rust code path writes to it on merge or reindex.
- Power users who still want a JSON snapshot for `git diff` or ad-hoc inspection run it on demand:

  ```
  pss export --json --path /tmp/pss-export.json
  ```

  Added in Phase B (v2.10.0), this subcommand reads CozoDB and writes a JSON file with the same shape the old canonical index had.
- `pycozo[embedded]>=0.7.6` is now a hard dependency (it was a soft dependency in v2.10.x). Install with `uv pip install 'pycozo[embedded]'` — the plugin's `pyproject.toml` already lists it, so a fresh install handles this automatically.

**Migration safety.** Upgrading from v2.10.x to v3.0.0 requires no user action. The hook's health check detects a missing-or-empty CozoDB and auto-spawns a background reindex (same UX as first-install). Legacy `skill-index.json` files are left in place (harmless) rather than deleted — that would be a surprising side-effect of a version bump.

**Why the change now.** Single source of truth is a cheaper invariant than dual-store consistency; the 2026-04 tailwind-4-docs bug was the fourth consecutive drift incident in six months. The Rust hot path already treated CozoDB as canonical (with JSON as a fallback that was almost never exercised in practice). Formalising the inversion collapses ~300 lines of "which store do I read?" decision logic across the Python codebase.

### 5-Tier Logarithmic Scoring

The scoring system is built around a simple idea: **not all matches are equal**. A skill that matches "bun" as a tool name is far more relevant to a bun-related prompt than a skill that happens to contain the generic word "build". The 5-tier system enforces this with a logarithmic scale where each tier is **10x more powerful** than the one below it.

| Tier | Score Range | What Matches | Examples |
|------|-------------|--------------|----------|
| **T1** | 10 - 90 | Common/generic words | "test", "build", "debug", "run", "fix" |
| **T2** | 100 - 900 | Specific keywords and phrases | "lint the script", "trace this function" |
| **T3** | 1,000 - 9,000 | Tool names | bun, webpack, vite, eslint, docker, jest |
| **T4** | 10,000 - 90,000 | Frameworks | react, nextjs, django, fastapi, flutter |
| **T5** | 100,000 - 900,000 | Services and APIs | aws, openai, vercel, supabase, stripe |

**Why logarithmic?** A single tool match (T3: 2,000 points) always outranks any number of generic keyword matches (T1: 10-90 each). You can stack 20 generic matches and still not beat one tool match. This prevents noise from drowning out signal.

#### Cumulative Scoring

If a term belongs to multiple tiers, the scores **add up**. For example, "bun" is both a tool (T3) and a framework (T4), so a bun-related skill gets points from both tiers. This rewards skills that are deeply connected to a technology across multiple dimensions.

#### Position-Based Multipliers

Within each tier, a term's score scales based on **where** it appears in the skill's metadata:

| Position | Multiplier |
|----------|-----------|
| In skill name/title | 2x per occurrence |
| In skill description | 1.5x per occurrence |
| In skill body (keywords) | 1x per occurrence (max 4x) |

A skill named "building-with-bun" gets a higher tool score for "bun" than a skill that merely lists "bun" among 20 other keywords. The more prominently a technology appears in a skill, the higher it scores.

### Binary Filters (Languages, Platforms, Domains)

Filters are fundamentally different from scoring tiers. **They don't add points -- they exclude entirely.**

When the prompt mentions a specific language, platform, or domain, skills locked to a *different* value get a score of zero and are removed from results. There is no partial penalty.

| Filter | When Prompt Says... | Skills That Are... | Result |
|--------|--------------------|--------------------|--------|
| Language | "python" | Locked to JavaScript-only | **Excluded** |
| Platform | "ios" | Locked to Android-only | **Excluded** |
| Domain | "medicine" | Gated to geography | **Excluded** |

**Why binary exclusion instead of a percentage penalty?**

Consider what happens with a soft 20% penalty:

```
Prompt: "use OpenAI for medical data analysis with bun"

Skill A: domain=geography, service=openai
  score = 200,000 (openai) x 80% penalty = 160,000

Skill B: domain=medicine, tool=bun, framework=bun
  score = 2,000 (bun as tool) + 20,000 (bun as framework) = 22,000
```

Skill A wins despite being about the **wrong domain**. A geography skill has no business ranking above a medicine skill when the user asked about medicine. With binary exclusion, Skill A is eliminated and Skill B correctly wins.

The same logic applies to languages and platforms. A Rust-only skill should never appear when the user asks about Python, no matter how many other high-tier matches it has. The math makes any soft penalty insufficient -- the 10x gaps between tiers mean even a 90% penalty on a T5 match (100K) still leaves it at 10K, which beats most T3 matches outright.

**Exemptions from filtering:**
- Skills with no language/platform/domain specified (universal skills) always pass through
- Compatible language groups are respected (TypeScript <-> JavaScript, Kotlin <-> Java)
- When a skill's tool or framework name appears explicitly in the prompt, domain gates are bypassed (e.g., "use bun" matches bun skills even without saying "javascript")

## Commands

### /pss-reindex-skills

Generate the skill index for all elements (skills, agents, commands, rules, MCP, LSP) using the deterministic Rust pipeline.

```
/pss-reindex-skills [--exclude-inactive-plugins]
```

| Flag | Description |
|------|-------------|
| `--exclude-inactive-plugins` | Skip plugins disabled in Claude Code settings (reads `enabledPlugins` from `~/.claude/settings.json`) |

Always performs a full clean-slate regeneration. Uses a 3-stage Rust pipeline: discover → enrich → merge. Completes in under 10 seconds for 10K+ elements.

### /pss-setup-agent

Analyze an agent definition and generate a `.agent.toml` configuration with AI-recommended skills, commands, rules, MCP servers, and LSP servers. Includes automatic self-review (quality checks before reporting) and a dependencies section in the generated `.agent.toml`.

```
/pss-setup-agent /path/to/agent.md
/pss-setup-agent /path/to/agent.md --requirements /path/to/prd.md /path/to/tech-spec.md
/pss-setup-agent /path/to/agent.md --output /custom/output.agent.toml
/pss-setup-agent agents/my-agent.md --interactive
```

Uses the Rust binary for fast candidate scoring + an AI agent for intelligent post-filtering (mutual exclusivity, stack compatibility, redundancy pruning). Two-pass scoring with `--requirements` separates agent-intrinsic elements from project-level elements, cherry-picking only those matching the agent's specialization.

| Flag | Description |
|------|-------------|
| `--fast` | Fast profiling mode: Rust binary only, 2-5 seconds, no AI agent needed |
| `--interactive` | Interactive review mode: pause after each tier for manual include/exclude decisions |
| `--include <name>` | Force-include a specific element in the final profile |
| `--exclude <name>` | Force-exclude a specific element from the final profile |
| `--max-primary N` | Override the maximum number of primary tier elements |
| `--max-secondary N` | Override the maximum number of secondary tier elements |
| `--max-specialized N` | Override the maximum number of specialized tier elements |
| `--requirements <files>` | Additional context files (PRDs, tech specs) for better recommendations |
| `--output <path>` | Custom output path for the generated `.agent.toml` |

**Constraint flags** narrow the candidate pool before scoring:

| Flag | Description |
|------|-------------|
| `--domain <name>` | Restrict candidates to a specific domain (e.g., `devops`, `frontend`) |
| `--language <name>` | Restrict candidates to a specific language (e.g., `python`, `typescript`) |
| `--platform <name>` | Restrict candidates to a specific platform (e.g., `linux`, `macos`) |

### /pss-add-to-index

Index a single skill/agent/command element incrementally without full reindex.

```
/pss-add-to-index /path/to/element
/pss-add-to-index --plugin /path/to/plugin
```

### /pss-add-element

Add standalone elements to existing Claude Code plugins. Supports all element types with duplicate detection and optional CPV validation.

```
/pss-add-element --type skill --source /path/to/skill-dir --plugin /path/to/plugin
/pss-add-element --type agent --source /path/to/agent.md --plugin /path/to/plugin
/pss-add-element --type hook --source /path/to/hooks.json --plugin /path/to/plugin --validate
/pss-add-element --type mcp-server --source /path/to/mcp.json --plugin /path/to/plugin
/pss-add-element --type lsp-server --source /path/to/lsp.json --plugin /path/to/plugin
/pss-add-element --type output-style --source /path/to/style.md --plugin /path/to/plugin
```

| Flag | Description |
|------|-------------|
| `--type` | Element type: `skill`, `agent`, `command`, `hook`, `rule`, `mcp-server`, `lsp-server`, `output-style` |
| `--source` | Path to element source (directory for skills, .md for agents/commands/rules/output-styles, .json for hooks/MCP/LSP) |
| `--plugin` | Path to target plugin (must contain `.claude-plugin/plugin.json`) |
| `--validate` | Run CPV validation after adding |
| `--force` | Skip duplicate/incompatibility checks |
| `--dry-run` | Preview changes without modifying files |

### /pss-get-description

Retrieve element metadata (description, type, plugin source) by name. Falls back to the CozoDB `rules` table for rule file lookups.

```
/pss-get-description senior-ios
/pss-get-description pss-authoring
```

### /pss-make-plugin-from-profile

Generate a complete, installable Claude Code plugin from an `.agent.toml` profile. Copies all referenced elements (skills, agents, commands) into a self-contained plugin directory.

```
/pss-make-plugin-from-profile agent.agent.toml --output ~/plugins/my-plugin
/pss-make-plugin-from-profile agent.agent.toml --output ./plugin --name custom-name
```

### /pss-change-agent-profile

Modify an existing `.agent.toml` profile with natural language instructions. Resolves element names against the skill index, applies changes, verifies, and validates.

```
/pss-change-agent-profile /path/to/agent.agent.toml remove all skills using tldr tool
/pss-change-agent-profile /path/to/agent.agent.toml add a subagent for github projects
/pss-change-agent-profile /path/to/agent.agent.toml --requirements docs/prd.md align with project requirements
```

| Flag | Description |
|------|-------------|
| `--requirements <files>` | Re-align profile with project requirements using two-pass scoring |

### /pss-status

View current status and test matching.

```
/pss-status [--verbose] [--test "PROMPT"]
```

| Flag | Description |
|------|-------------|
| `--verbose` | Show detailed breakdown |
| `--test "PROMPT"` | Test matching against prompt |
| `--run-tests` | Run end-to-end pipeline tests |

## Configuration

### Scoring Weights

Weights are defined in `rust/skill-suggester/src/main.rs` in the `MatchWeights` struct. Key values:

| Weight | Value | Tier |
|--------|-------|------|
| `keyword` | 100 (10 if low-signal) | T1/T2 |
| `first_match` | 300 (30 if low-signal) | T2 |
| `tool_match` | 2,000 | T3 |
| `framework_match` | 20,000 | T4 |
| `service_match` | 200,000 | T5 |
| `capped_max` | 900,000 | T5 ceiling |

Common tools/languages are dampened (divided by 5 or 20) to stay within their tier range.

### Confidence Thresholds

| Level | Threshold | Typical trigger |
|-------|-----------|-----------------|
| HIGH | >= 1,000 | One tool match or many specific keywords |
| MEDIUM | >= 100 | One specific keyword match |
| LOW | < 100 | Generic words only |

### Validation Scripts

```bash
uv run scripts/pss_validate_agent_toml.py <file.agent.toml>    # Validate TOML structure
uv run scripts/pss_verify_profile.py <file.agent.toml>          # Verify element names against index
```

## Element Index Format (v3.0)

```json
{
  "version": "3.0",
  "generated": "2026-04-13T00:00:00Z",
  "method": "ai-analyzed",
  "skill_count": 10112,
  "skills": {
    "devops-expert": {
      "source": "user",
      "path": "/path/to/SKILL.md",
      "type": "skill",
      "category": "devops-cicd",
      "secondary_categories": ["testing"],
      "keywords": ["github", "actions", "ci", "deploy"],
      "intents": ["deploy", "build", "test"],
      "patterns": ["workflow.*failed", "ci.*error"],
      "directories": ["workflows", ".github"],
      "platforms": [],
      "frameworks": [],
      "languages": ["yaml"],
      "tools": ["github-actions"],
      "services": ["github"],
      "description": "CI/CD pipeline configuration",
      "domain_gates": {
        "target_platform": ["github"]
      },
      "path_gates": []
    },
    "python-style-rule": {
      "source": "user",
      "path": "/path/to/rule.md",
      "type": "rule",
      "description": "Python code style conventions",
      "path_gates": ["**/*.py"]
    }
  }
}
```

Notes:
- **`domain_gates`**: hard prerequisite filter — ALL gates must match prompt domains (v2.7.0+)
- **`path_gates`**: rule-only activation globs from `paths:` frontmatter; filtered by project file types and languages (v2.9.35+)

## Platform Support

Pre-built binaries included for:

| Platform | Binary |
|----------|--------|
| macOS Apple Silicon | `bin/pss-darwin-arm64` |
| macOS Intel | `bin/pss-darwin-x86_64` |
| Linux x86_64 | `bin/pss-linux-x86_64` |
| Linux ARM64 | `bin/pss-linux-arm64` |
| Windows x86_64 | `bin/pss-windows-x86_64.exe` |

## Building from Source

```bash
# Build for current platform
uv run python scripts/pss_build.py

# Build all 5 platforms (cross + Docker needed for Linux/Windows)
uv run python scripts/pss_build.py --all

# Build specific target
uv run python scripts/pss_build.py --target linux-x86_64

# List all supported targets
uv run python scripts/pss_build.py --list-targets
```

Cross-compile targets use `musl` for fully static Linux binaries.

## Release

Full pipeline: test → lint → bump → changelog → build → commit → push → marketplace update.

```bash
# Full release
uv run python scripts/publish.py --bump patch

# Preview (no changes)
uv run python scripts/publish.py --bump minor --dry-run

# Version bump only (no builds)
uv run python scripts/publish.py --bump patch --skip-build

# Run pre-release gates (lint, test, validate) without releasing
uv run python scripts/publish.py --gate

# Install pre-push quality gate (runs lint + validate + test before every push)
uv run python scripts/publish.py --install-hook
```

Version is updated in 4 files: `VERSION` (source of truth), `rust/skill-suggester/Cargo.toml`,
`.claude-plugin/plugin.json`, `pyproject.toml`. The Rust binary reads the version at runtime
from `VERSION` via `CLAUDE_PLUGIN_ROOT`. Pushing triggers the marketplace notification workflow
automatically.

## Performance

| Metric | Value |
|--------|-------|
| Hook execution | ~10ms |
| Binary size | ~1MB |
| Memory usage | ~2-3MB |
| Accuracy | 88%+ |

## Documentation

| Document | Description |
|----------|-------------|
| [CHANGELOG.md](CHANGELOG.md) | Full version history (every release since v1.6.1) |
| [pss-cli-reference.md](docs/pss-cli-reference.md) | Canonical CLI reference: all 62 subcommands, every flag, example output |
| [CC-COMPATIBILITY.md](docs/CC-COMPATIBILITY.md) | Single home for Claude Code compatibility — version-by-version matrix, declared hook events, HookInput schema notes, Anthropic compliance audit |
| [PSS-ARCHITECTURE.md](docs/PSS-ARCHITECTURE.md) | Core architecture: two-pass generation, index as superset, categories vs keywords |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Development guide — building binaries, running tests, contributing |
| [PLUGIN-VALIDATION.md](docs/PLUGIN-VALIDATION.md) | Guide for writing plugin validation scripts |
| [PSS_FILE_FORMAT_SPEC.md](docs/PSS_FILE_FORMAT_SPEC.md) | PSS file format spec |
| [pss-reindex-reference.md](docs/pss-reindex-reference.md) | Reindex pipeline reference |
| [FEATURE_COMPARISON.md](docs/FEATURE_COMPARISON.md) | Feature comparison |

### Key Architecture Concepts

- **Index is a Superset**: The skill index contains ALL skills ever indexed. The agent filters suggestions against its context-injected available skills list.
- **No Staleness Checks**: `/pss-reindex-skills` performs full clean-slate regeneration. For incremental single-element updates, use `/pss-add-to-index` instead.
- **Two-Pass Generation**: Pass 1 extracts keywords/descriptions, Pass 2 uses AI to determine co-usage relationships.
- **Categories vs Keywords**: Categories are FIELDS OF COMPETENCE (16 predefined) for the CxC matrix. Keywords are a SUPERSET including specific tools/actions.

## Validation

Run CPV remote validation after every change (no local scripts needed):

```bash
uvx --from git+https://github.com/Emasoft/claude-plugins-validation --with pyyaml \
    cpv-remote-validate plugin . --verbose
```

## License

MIT License - see [LICENSE](LICENSE)

## Author

Emasoft <713559+Emasoft@users.noreply.github.com>

## Repository

https://github.com/Emasoft/perfect-skill-suggester
