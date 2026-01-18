# Perfect Skill Suggester (PSS)

**High-accuracy skill activation (88%+) for Claude Code** with AI-analyzed keywords, weighted scoring, synonym expansion, and three-tier confidence routing.

## Features

PSS combines the best features from 4 skill activators:

| Source | Feature | Description |
|--------|---------|-------------|
| **claude-rio** | AI-analyzed keywords | Haiku subagents analyze each SKILL.md to generate optimal activation patterns |
| **catalyst** | Rust binary (~10ms) | Native binary for minimal hook latency |
| **LimorAI** | 70+ synonym patterns | Expand user prompts for better matching |
| **LimorAI** | Skills-first ordering | Skills appear before other context in output |
| **reliable** | Weighted scoring | Directory (+5), path (+4), intent (+4), pattern (+3), keyword (+2) |
| **reliable** | Three-tier confidence | HIGH (auto-suggest), MEDIUM (show evidence), LOW (alternatives) |
| **reliable** | Commitment mechanism | HIGH confidence includes evaluation reminder |

## Installation

### Option 1: Load with --plugin-dir (Recommended for testing)

```bash
claude --plugin-dir /path/to/perfect-skill-suggester
```

### Option 2: Install from marketplace

```bash
claude plugin install perfect-skill-suggester@emasoft-plugins
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

## Comparison to Other Approaches

| Aspect | Heuristic | Rio v2.0 | PSS |
|--------|-----------|----------|-----|
| Accuracy | ~70% | ~80% | **88%+** |
| Multi-word phrases | No | Yes | Yes |
| Weighted scoring | No | No | **Yes** |
| Synonym expansion | No | No | **Yes (70+)** |
| Confidence routing | No | No | **Yes (3-tier)** |
| Commitment mechanism | No | No | **Yes** |
| AI-analyzed keywords | No | Yes | **Yes** |
| Native binary | No | No | **Yes (Rust)** |

## License

MIT License - see [LICENSE](LICENSE)

## Author

Emasoft <713559+Emasoft@users.noreply.github.com>

## Repository

https://github.com/Emasoft/perfect-skill-suggester
