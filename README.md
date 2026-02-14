# Perfect Skill Suggester (PSS)

> **Installation:** This plugin is distributed via the [Emasoft Plugins Marketplace](https://github.com/Emasoft/emasoft-plugins).
> See [Installation](#installation) below for instructions.

**High-accuracy skill activation (88%+) for Claude Code** with AI-analyzed keywords, weighted scoring, synonym expansion, and three-tier confidence routing.

## Features

### AI-Analyzed Keywords
Haiku subagents analyze each SKILL.md to extract optimal activation patterns. Instead of relying on manually defined keywords, the AI reads the skill content and determines what user prompts should trigger it.

### Native Rust Binary (~10ms)
A pre-compiled Rust binary handles all matching logic, keeping hook latency minimal. No Python interpreter startup, no JIT compilation - just fast native code.

### Synonym Expansion (70+ patterns)
User prompts are expanded with synonyms before matching. For example:
- `"pr"` → `"github pull request"`
- `"403"` → `"oauth2 authentication"`
- `"db"` → `"database"`
- `"ci"` → `"cicd deployment automation"`

### Weighted Scoring System
Different match types contribute different point values:
- **Directory match**: +5 points (skill is in a directory mentioned in prompt)
- **Path match**: +4 points (file paths in prompt match skill patterns)
- **Intent match**: +4 points (action verbs like "deploy", "test", "build")
- **Pattern match**: +3 points (regex patterns in skill config)
- **Keyword match**: +2 points (simple keyword matches)
- **First match bonus**: +10 points (first keyword hit gets extra weight)
- **Original bonus**: +3 points (keyword in original prompt, not from expansion)

### Three-Tier Confidence Routing
Match scores determine how suggestions are presented:
- **HIGH (≥12)**: Auto-suggest with commitment reminder
- **MEDIUM (6-11)**: Show with match evidence explaining why
- **LOW (<6)**: Include as alternatives for user consideration

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
claude --plugin-dir ./OUTPUT_SKILLS/perfect-skill-suggester
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
cd rust/skill-suggester
cargo build --release
# Copy binary to bin/ with appropriate name
```

## Quick Start

### 1. Generate Skill Index

Run the reindex command to analyze all skills with AI:

```
/pss-reindex-skills
```

This spawns Haiku subagents to analyze each SKILL.md and generate optimal activation keywords.

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

### Three-Phase Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                     USER PROMPT                              │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1: SYNONYM EXPANSION (70+ patterns)                  │
│                                                             │
│  "pr" → "github pull request"                               │
│  "403" → "oauth2 authentication"                            │
│  "db" → "database"                                          │
│  "ci" → "cicd deployment automation"                        │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 2: WEIGHTED SCORING                                  │
│                                                             │
│  • directory match    +5 points                             │
│  • path match         +4 points                             │
│  • intent match       +4 points                             │
│  • pattern match      +3 points                             │
│  • keyword match      +2 points                             │
│  • first match bonus  +10 points                            │
│  • original bonus     +3 points (not from expansion)        │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 3: CONFIDENCE CLASSIFICATION                         │
│                                                             │
│  HIGH (≥12):   Auto-suggest with commitment reminder        │
│  MEDIUM (6-11): Show with match evidence                    │
│  LOW (<6):      Include alternatives                        │
└─────────────────────────────────────────────────────────────┘
```

### Commitment Mechanism

For HIGH confidence matches, the output includes a commitment reminder:

```json
{
  "name": "devops-expert",
  "score": 0.95,
  "confidence": "HIGH",
  "commitment": "Before implementing: Evaluate YES/NO - Will this skill solve the user's actual problem?"
}
```

This helps Claude pause and evaluate before blindly following skill instructions.

## Commands

### /pss-reindex-skills

Generate AI-analyzed keyword index for all skills.

```
/pss-reindex-skills [--force] [--skill SKILL_NAME] [--batch-size N]
```

| Flag | Description |
|------|-------------|
| `--force` | Force reindex even if cache is fresh |
| `--skill NAME` | Only reindex specific skill |
| `--batch-size N` | Skills per batch (default: 10) |

### /pss-status

View current status and test matching.

```
/pss-status [--verbose] [--test "PROMPT"]
```

| Flag | Description |
|------|-------------|
| `--verbose` | Show detailed breakdown |
| `--test "PROMPT"` | Test matching against prompt |

## Configuration

### Scoring Weights

Modify weights in the Rust source at `rust/skill-suggester/src/main.rs`:

```rust
const WEIGHTS: MatchWeights = MatchWeights {
    directory: 5,
    path: 4,
    intent: 4,
    pattern: 3,
    keyword: 2,
    first_match: 10,
    original_bonus: 3,
    capped_max: 10,
};
```

### Confidence Thresholds

```rust
const HIGH_THRESHOLD: i32 = 12;
const MEDIUM_THRESHOLD: i32 = 6;
```

## Skill Index Format (v3.0)

```json
{
  "version": "3.0",
  "generated": "2026-01-18T06:00:00Z",
  "method": "ai-analyzed",
  "skills_count": 216,
  "skills": {
    "devops-expert": {
      "source": "user",
      "path": "/path/to/SKILL.md",
      "type": "skill",
      "keywords": ["github", "actions", "ci", "deploy"],
      "intents": ["deploy", "build", "test"],
      "patterns": ["workflow.*failed", "ci.*error"],
      "directories": ["workflows", ".github"],
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

## Building from Source

```bash
cd rust/skill-suggester
cargo build --release
```

Cross-compile for all platforms:

```bash
# macOS ARM64
cargo build --release --target aarch64-apple-darwin

# macOS x86_64
cargo build --release --target x86_64-apple-darwin

# Linux x86_64
cargo build --release --target x86_64-unknown-linux-gnu

# Linux ARM64
cargo build --release --target aarch64-unknown-linux-gnu

# Windows x86_64
cargo build --release --target x86_64-pc-windows-gnu
```

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
