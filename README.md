<p align="center">
  <img src="resources/perfect_skill_suggester_logo_header.jpeg" alt="Perfect Skill Suggester" width="800" />
</p>

# Perfect Skill Suggester (PSS)

![Version](https://img.shields.io/badge/version-2.3.46-blue)
![Platforms](https://img.shields.io/badge/platforms-6-green)
![Accuracy](https://img.shields.io/badge/accuracy-88%25+-brightgreen)
![License](https://img.shields.io/badge/license-MIT-yellow)
![Rust](https://img.shields.io/badge/rust-native_binary-orange)
![Claude Code](https://img.shields.io/badge/claude--code-plugin-blueviolet)

> **Installation:** This plugin is distributed via the [Emasoft Plugins Marketplace](https://github.com/Emasoft/emasoft-plugins).
> See [Installation](#installation) below for instructions.

> Built for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) |
> Orchestrated by [AI Maestro](https://github.com/Emasoft/ai-maestro) |
> Part of the [Emasoft Plugins](https://github.com/Emasoft/emasoft-plugins) ecosystem

**High-accuracy skill activation (88%+) for Claude Code** with AI-analyzed keywords, weighted scoring, synonym expansion, and three-tier confidence routing. Indexes 6 element types: skills, agents, commands, rules, MCP servers, and LSP servers — 874+ elements including 246 MCP servers.

## Features

### Multi-Type Element Indexing
Indexes all 6 Claude Code element types — not just skills. The unified index powers both real-time hook suggestions and AI-driven agent configuration profiling.

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

### Commands not found

**Symptom:** `/pss-reindex-skills` or `/pss-status` not recognized.

**Solution:** Restart Claude Code. Commands are only loaded at startup.

### No skill suggestions appear

**Symptom:** Plugin is installed but no skills are suggested.

**Solutions:**
1. Run `/pss-reindex-skills` to generate the skill index
2. Check the index exists: `ls ~/.claude/cache/skill-index.json`
3. Verify plugin is enabled: `claude plugin list`

### Binary not found for platform

**Symptom:** Error about missing platform binary.

**Solution:** Pre-built binaries are included for all major platforms. If yours is missing:
```bash
cd src/skill-suggester
cargo build --release
# Copy binary to bin/ with appropriate name
```

## Quick Start

### 1. Generate Skill Index

Run the reindex command to analyze all skills with AI:

```
/pss-reindex-skills
```

This spawns Sonnet subagents to analyze each element (skills, agents, commands, rules, MCP servers) and generate optimal activation keywords. Marketplace MCP servers are automatically discovered and indexed.

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

Generate AI-analyzed keyword index for all elements (skills, agents, commands, rules, MCP, LSP).

```
/pss-reindex-skills [--batch-size N] [--pass1-only] [--pass2-only] [--all-projects]
```

| Flag | Description |
|------|-------------|
| `--batch-size N` | Elements per Sonnet batch (default: 10) |
| `--pass1-only` | Run only Pass 1 (keyword extraction) |
| `--pass2-only` | Run only Pass 2 (co-usage analysis) |
| `--all-projects` | Scan all known projects, not just current |

Always performs a full clean-slate regeneration. Two-pass architecture: Pass 1 extracts keywords/metadata, Pass 2 builds co-usage relationships.

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

Weights are defined in `src/skill-suggester/src/main.rs` in the `MatchWeights` struct. Key values:

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
  "generated": "2026-02-27T06:00:00Z",
  "method": "ai-analyzed",
  "skill_count": 9172,
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
      "description": "CI/CD pipeline configuration"
    }
  }
}
```

## Platform Support

Pre-built binaries included for:

| Platform | Binary |
|----------|--------|
| macOS Apple Silicon | `bin/pss-darwin-arm64` |
| macOS Intel | `bin/pss-darwin-x86_64` |
| Linux x86_64 | `bin/pss-linux-x86_64` |
| Linux ARM64 | `bin/pss-linux-arm64` |
| Windows x86_64 | `bin/pss-windows-x86_64.exe` |
| wasm32 | `bin/pss-wasm32.wasm` |

## Building from Source

```bash
# Build for current platform
uv run python scripts/pss_build.py

# Build all 6 platforms (cross + Docker needed for Linux/Windows)
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
uv run python scripts/pss_ship.py --bump patch

# Preview (no changes)
uv run python scripts/pss_ship.py --bump minor --dry-run

# Version bump only (no builds)
uv run python scripts/pss_ship.py --bump patch --skip-build

# Run pre-release gates (lint, test, validate) without releasing
uv run python scripts/pss_ship.py --gate

# Sync CPV validation scripts from upstream before release
uv run python scripts/pss_ship.py --sync-cpv
```

Version is updated in 4 files: Cargo.toml, main.rs, plugin.json, pyproject.toml.
Pushing triggers the marketplace notification workflow automatically.

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
| [PSS-ARCHITECTURE.md](docs/PSS-ARCHITECTURE.md) | Core architecture: two-pass generation, index as superset, categories vs keywords |
| [PLUGIN-VALIDATION.md](docs/PLUGIN-VALIDATION.md) | Guide for writing plugin validation scripts |
| [pss-cli-reference.md](docs/pss-cli-reference.md) | CLI subcommands reference |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Development guide |
| [FEATURE_COMPARISON.md](docs/FEATURE_COMPARISON.md) | Feature comparison |
| [PSS_FILE_FORMAT_SPEC.md](docs/PSS_FILE_FORMAT_SPEC.md) | PSS file format spec |
| [pss-reindex-reference.md](docs/pss-reindex-reference.md) | Reindex reference |
| [ANTHROPIC-COMPLIANCE-REPORT.md](docs/ANTHROPIC-COMPLIANCE-REPORT.md) | Anthropic compliance report |

### Key Architecture Concepts

- **Index is a Superset**: The skill index contains ALL skills ever indexed. The agent filters suggestions against its context-injected available skills list.
- **No Staleness Checks**: Regenerate from scratch with `/pss-reindex-skills`. No incremental updates.
- **Two-Pass Generation**: Pass 1 extracts keywords/descriptions, Pass 2 uses AI to determine co-usage relationships.
- **Categories vs Keywords**: Categories are FIELDS OF COMPETENCE (16 predefined) for the CxC matrix. Keywords are a SUPERSET including specific tools/actions.

## Validation

Run the validation script after every change:

```bash
uv run python scripts/validate_plugin.py . --verbose
```

## License

MIT License - see [LICENSE](LICENSE)

## Author

Emasoft <713559+Emasoft@users.noreply.github.com>

## Repository

https://github.com/Emasoft/perfect-skill-suggester
