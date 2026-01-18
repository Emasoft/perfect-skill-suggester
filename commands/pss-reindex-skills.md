---
name: pss-reindex-skills
description: "Scan ALL skills and generate AI-analyzed keyword/phrase index for skill activation."
argument-hint: "[--force] [--skill SKILL_NAME] [--batch-size N]"
allowed-tools: ["Bash", "Read", "Write", "Glob", "Grep", "Task"]
---

# PSS Reindex Skills Command

Generate an **AI-analyzed** keyword and phrase index for ALL skills available to Claude Code. Unlike heuristic approaches, this command has the agent **read and understand each skill** to formulate optimal activation patterns.

This is the **MOST IMPORTANT** feature of Perfect Skill Suggester - AI-generated keywords ensure 88%+ accuracy in skill matching.

## Two-Phase Architecture

### Phase 1: Discovery (Script)
The Python script `pss_discover_skills.py` scans ALL skill locations and outputs paths.

### Phase 2: Analysis (Agent)
The agent (or parallel subagents) reads each SKILL.md and formulates **rio-compatible keywords**:
- **Single keywords**: `docker`, `test`, `deploy`
- **Multi-word phrases**: `fix ci pipeline`, `review pull request`, `set up github actions`
- **Error patterns**: `build failed`, `type error`, `connection refused`

**Rio Compatibility**: Keywords are stored in a flat array and matched using `.includes()` against the lowercase user prompt. The `matchCount` is simply the number of matching keywords.

## Usage

```
/pss-reindex-skills [--force] [--skill SKILL_NAME] [--batch-size 20]
```

## Execution Protocol

### Step 1: Generate Skill Checklist

Run the discovery script with `--checklist` to generate a markdown checklist with batches:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pss_discover_skills.py --checklist --batch-size 10
```

This creates `~/.claude/cache/skill-checklist.md` with:
- All skills organized into batches (default: 10 per batch)
- Checkbox format for tracking progress
- Agent assignment suggestions (Agent A, B, C, etc.)

Example output:
```
Checklist written to: /Users/you/.claude/cache/skill-checklist.md
  216 skills in 22 batches
```

### Step 2: Divide Work Among Agents

The orchestrator reads the checklist and spawns haiku subagents, one per batch:

```
Batch 1 (skills 1-10)   → Agent A
Batch 2 (skills 11-20)  → Agent B
Batch 3 (skills 21-30)  → Agent C
...
Batch 22 (skills 211-216) → Agent V
```

**Key Workflow:**
1. Orchestrator reads the checklist file
2. For each batch, spawn a haiku subagent with:
   - The batch number and range
   - The list of skill paths in that batch
   - Instructions to read each skill and generate patterns
3. All subagents run in parallel (up to 20 concurrent)
4. Each subagent marks entries with [x] as complete
5. Orchestrator collects all results

### Step 3: Subagent Analysis

Each subagent receives a prompt like this:

**Subagent Prompt Template (rio v2.0 compatible):**

```
You are analyzing skills for Batch {batch_num} (skills {start}-{end}).

For EACH skill in your batch:
1. Read the SKILL.md at the given path
2. Analyze content to understand when this skill should activate
3. Generate rio-compatible keywords
4. Output JSON result

Skills to analyze:
{list_of_skill_paths}

For each skill, output a JSON object in rio v2.0 format:

{
  "name": "skill-name",
  "type": "skill",
  "keywords": ["keyword1", "keyword2", "multi word phrase", ...],
  "description": "One-line description of when to use this skill"
}

KEYWORD SELECTION RULES (rio v2.0):
1. Generate 8-15 keywords/phrases total
2. ALL keywords must be LOWERCASE (matching uses .includes() on lowercase prompt)
3. Include BOTH single words AND multi-word phrases in the same array
4. Focus on ACTIVATION - what would a user say that means they need THIS skill?

KEYWORD CATEGORIES TO INCLUDE:
- Tool/technology names: "docker", "typescript", "github actions"
- Action verbs: "build", "deploy", "test", "lint", "format"
- Error patterns: "build failed", "type error", "connection refused"
- Command phrases: "set up ci", "fix the build", "run tests"
- Domain concepts: "pipeline", "workflow", "container"

EXAMPLE OUTPUT:
{
  "name": "devops-expert",
  "type": "skill",
  "keywords": ["github", "actions", "ci", "cd", "pipeline", "deploy", "github actions", "ci pipeline", "workflow failed", "set up ci"],
  "description": "CI/CD pipeline configuration and GitHub Actions workflows"
}

After processing each skill, mark it complete in the checklist with [x].

Return a minimal report: one JSON object per line, no extra text.
```

### Step 4: Compile Index

Merge all subagent responses into the master index (rio v2.0 compatible format with PSS extensions):

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
      "keywords": ["github", "actions", "ci", "cd", "pipeline", "deploy", "github actions", "ci pipeline", "workflow failed", "set up ci"],
      "intents": ["deploy", "build", "test", "release"],
      "patterns": ["workflow.*failed", "ci.*error", "deploy.*stuck"],
      "directories": ["workflows", ".github"],
      "description": "CI/CD pipeline configuration and GitHub Actions workflows"
    }
  }
}
```

**Index Schema (PSS v3.0 - extends rio v2.0):**
| Field | Type | Description |
|-------|------|-------------|
| `source` | string | Where skill comes from: `user`, `project`, `plugin` |
| `path` | string | Full path to SKILL.md |
| `type` | string | `skill`, `agent`, or `command` (rio type field) |
| `keywords` | string[] | Flat array of lowercase keywords/phrases (rio compatible) |
| `intents` | string[] | PSS: Action verbs for weighted scoring (+4 points) |
| `patterns` | string[] | PSS: Regex patterns for pattern matching (+3 points) |
| `directories` | string[] | PSS: Directory contexts for directory boost (+5 points) |
| `description` | string | One-line description |

### Step 5: Save Index

Write to: `~/.claude/cache/skill-index.json`

```bash
mkdir -p ~/.claude/cache
```

## Keyword Categories (rio v2.0)

All keywords go into a single flat array. Include a mix of:

### Technology Names
Tool and framework identifiers:
- `docker`, `kubernetes`, `typescript`, `python`, `rust`
- `github actions`, `gitlab ci`, `jenkins`

### Action Verbs
What the user wants to do:
- `deploy`, `test`, `review`, `refactor`, `debug`
- `build`, `lint`, `format`, `migrate`

### Command Phrases
Natural language fragments (multi-word):
- `fix the build`, `run tests`, `set up ci`
- `review this pr`, `deploy to production`

### Error Patterns
Messages that indicate the skill is needed:
- `build failed`, `type error`, `connection refused`
- `permission denied`, `module not found`

## PSS Enhanced Scoring Algorithm

PSS extends rio's matchCount with weighted scoring:

```rust
// Weighted scoring (from reliable skill-activator)
const WEIGHTS = {
    directory: 5,    // +5 - skill in matching directory
    path: 4,         // +4 - prompt mentions file path
    intent: 4,       // +4 - action verb matches
    pattern: 3,      // +3 - regex pattern matches
    keyword: 2,      // +2 - simple keyword match
    first_match: 10, // +10 - first keyword bonus (from LimorAI)
    original_bonus: 3 // +3 - keyword in original prompt (not expanded)
};

// Confidence classification
const THRESHOLDS = {
    high: 12,    // AUTO-suggest with commitment reminder
    medium: 6,   // Show with evidence
    low: 0       // Include alternatives
};
```

## Synonym Expansion (from LimorAI)

Before matching, user prompts are expanded with 70+ synonym patterns:

```
"pr" → "github pull request"
"403" → "oauth2 authentication"
"db" → "database"
"ci" → "cicd deployment automation"
"test" → "testing"
```

This improves matching accuracy significantly.

## Parallel Processing

For 200+ skills, process in batches:

```
Batch 1: Skills 1-20   → 20 parallel haiku subagents
Batch 2: Skills 21-40  → 20 parallel haiku subagents
...
Batch 11: Skills 201-216 → 16 parallel haiku subagents
```

Each subagent:
1. Reads the full SKILL.md (not just preview)
2. Analyzes content to understand the skill's purpose
3. Generates optimal activation patterns
4. Returns JSON result

## Cache Management

| Condition | Action |
|-----------|--------|
| No cache exists | Full reindex |
| Cache > 24 hours old | Full reindex |
| `--force` flag | Full reindex |
| `--skill NAME` | Reindex only that skill |
| Cache fresh | Skip (show message) |

## Example Output

```
Discovering skills...
Found 216 skills across 19 sources.

Generating checklist: ~/.claude/cache/skill-checklist.md
  22 batches (10 skills per batch)

Spawning haiku subagents (22 parallel)...
  Batch 1 (Agent A): analyzing skills 1-10...
  Batch 2 (Agent B): analyzing skills 11-20...
  ...

Collecting results...
  ✓ devops-expert: 12 keywords
  ✓ session-memory: 10 keywords
  ✓ code-reviewer: 11 keywords
  ... (213 more)

Index generated: ~/.claude/cache/skill-index.json
  216 skills analyzed
  Method: AI-analyzed (haiku)
  Format: PSS v3.0 (rio compatible)
  Total keywords: 2,592
```

## Rust Skill Suggester

For maximum performance, a native Rust binary is bundled at `rust/skill-suggester/bin/`.

**No installation required** - Pre-built binaries for all major platforms are included with the plugin.

### Supported Platforms

| Platform | Binary |
|----------|--------|
| macOS Apple Silicon | `bin/pss-darwin-arm64` |
| macOS Intel | `bin/pss-darwin-x86_64` |
| Linux x86_64 | `bin/pss-linux-x86_64` |
| Linux ARM64 | `bin/pss-linux-arm64` |
| Windows x86_64 | `bin/pss-windows-x86_64.exe` |

### Performance

| Metric | Value |
|--------|-------|
| **Binary Size** | ~1MB |
| **Startup Time** | ~5-10ms |
| **Memory Usage** | ~2-3MB |

### How It Works

1. **Reads stdin** - JSON payload from Claude Code hook
2. **Loads index** - From `~/.claude/cache/skill-index.json`
3. **Expands synonyms** - 70+ patterns for better matching
4. **Applies weighted scoring** - directory, path, intent, pattern, keyword weights
5. **Classifies confidence** - HIGH (≥12), MEDIUM (6-11), LOW (<6)
6. **Returns JSON** - Skills-first ordering with commitment mechanism

### Testing

```bash
# Test with sample prompt (use your platform's binary)
echo '{"prompt":"help me set up github actions"}' | ./rust/skill-suggester/bin/pss-darwin-arm64
```

### Debugging

```bash
RUST_LOG=debug ./rust/skill-suggester/bin/pss-darwin-arm64 < payload.json
```

## Related Commands

- `/pss-status` - View current skill index status and statistics

## Why AI-Analyzed Keywords Matter

| Aspect | Heuristic (old) | AI-Analyzed (PSS) |
|--------|-----------------|-------------------|
| Accuracy | ~70% | ~88%+ |
| Multi-word phrases | No | Yes |
| Error pattern detection | Limited | Full |
| Context understanding | None | Yes |
| Processing time | ~5 seconds | ~2-3 minutes |
| Requires API calls | No | Yes (Haiku) |
| **Commitment mechanism** | No | **Yes** |
| **Confidence routing** | No | **Yes (3-tier)** |
