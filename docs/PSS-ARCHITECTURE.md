# Perfect Skill Suggester (PSS) Architecture

## Core Design Principles

### 1. Index is a Superset, Agent Validates Availability

**CRITICAL UNDERSTANDING**: Claude Code already indexes all skills available to an agent in each session. The agent knows its available skills via the context injected by Claude Code.

| Component | Role |
|-----------|------|
| **PSS skill-index.json** | Contains ALL skills ever indexed across all sources (superset) |
| **skill-suggester binary** | Returns candidates from index based on keyword matching |
| **Claude Code** | Injects available skills list into each agent's context |
| **Agent** | Filters PSS suggestions against its known available skills |

**Why this matters:**
- Skills can be activated/deactivated per session (plugins, --plugin-dir, etc.)
- The same index may suggest skills the current session doesn't have access to
- The agent ALREADY KNOWS what skills are available - it can filter invalid suggestions
- No runtime validation of skill existence is needed in the hook

### 2. MANDATORY: Full Regeneration From Scratch - NO Incremental Updates

> **⛔ CRITICAL RULE: PSS reindexing MUST ALWAYS be a complete regeneration from scratch.**
> **NEVER perform incremental updates, partial reindexes, or skip "unchanged" skills.**

**Phase 0 (MANDATORY, NON-NEGOTIABLE) - Backup and delete ALL previous data BEFORE discovery:**
```bash
# Create timestamped backup in system temp dir (data is preserved but GONE from active paths)
PSS_TMPDIR=$(python3 -c "import tempfile; print(tempfile.gettempdir())")
BACKUP_DIR="${PSS_TMPDIR}/pss-backup-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Move (not delete) all index data to backup
mv ~/.claude/cache/skill-index.json "$BACKUP_DIR/" 2>/dev/null
mv ~/.claude/cache/skill-checklist.md "$BACKUP_DIR/" 2>/dev/null
find ~/.claude/skills -name ".pss" -type f -exec mv {} "$BACKUP_DIR/" \; 2>/dev/null
find ~/.claude/plugins/cache -name ".pss" -type f -exec mv {} "$BACKUP_DIR/" \; 2>/dev/null

# VERIFY clean slate - exit if ANY files remain
[ -f ~/.claude/cache/skill-index.json ] && echo "FATAL: Index still exists!" && exit 1
```

**⛔ The backup ensures old data is preserved for debugging but NEVER interferes with fresh reindex.**

**DO NOT** implement:
- File existence checks at index time
- Staleness detection or cleanup scripts
- Incremental index updates
- Hash-based change detection
- Single-skill reindex (`--skill NAME` is REMOVED)
- Cache freshness checks (always reindex)

**DO** implement:
- **Phase 0: Clean slate** - Delete ALL previous index data
- **Phase 1: Discovery** - Scan ALL skill locations fresh
- **Phase 2: Analysis** - Analyze ALL discovered skills

**Why incremental updates FAIL (proven by experience):**

| Problem | Cause | Result |
|---------|-------|--------|
| Stale version paths | Plugin updated from `2.17.0` to `2.18.1` | Skill not found at indexed path |
| Orphaned entries | Skill deleted/renamed | Phantom skill persists in index |
| Name mismatches | Indexed as "Swift Concurrency", dir is `swift-concurrency` | Skill exists but not matched |
| Missing new skills | New skill added to updated plugin | Not discovered in incremental mode |
| Broken co-usage | Referenced skill was deleted | Co-usage points to non-existent skill |

**The ONLY reliable approach is DELETE → DISCOVER → REINDEX from scratch.**

### 3. Comprehensive Multi-Project Skill Discovery

**NEW in PSS 1.0:** The discovery script can scan ALL projects registered in `~/.claude.json`, not just the current project.

**Skill Discovery Sources:**

| Source | Location | Flag Required |
|--------|----------|---------------|
| User-level | `~/.claude/skills/` | Always scanned |
| Current project | `.claude/skills/` | Always scanned |
| Plugin cache | `~/.claude/plugins/cache/*/*/skills/` | Always scanned |
| Local plugins | `~/.claude/plugins/*/skills/` | Always scanned |
| Current project plugins | `.claude/plugins/*/skills/` | Always scanned |
| **All other projects** | `<project>/.claude/skills/` and `<project>/.claude/plugins/*/skills/` | **`--all-projects`** |
| Agents | `~/.claude/agents/`, `.claude/agents/`, plugin `agents/` | Always scanned |
| Commands | `~/.claude/commands/`, `.claude/commands/`, plugin `commands/` | Always scanned |
| Rules | `~/.claude/rules/`, `.claude/rules/` | Always scanned |
| MCP servers | `~/.claude.json`, `.mcp.json` | Always scanned |
| LSP servers | `~/.claude/settings.json` enabledPlugins | Always scanned |

**Usage:**
```bash
# Standard discovery (current project + global)
python3 pss_discover.py

# Comprehensive discovery (ALL projects from ~/.claude.json)
python3 pss_discover.py --all-projects

# Generate .pss metadata files for each discovered skill
python3 pss_discover.py --all-projects --generate-pss
```

**Deleted Project Handling:**
Projects in `~/.claude.json` that no longer exist on disk are automatically skipped with a warning. No error is raised.

**Why This Matters:**
- The index is a superset of ALL skills ever indexed
- The agent filters suggestions against its context-injected available skills
- Indexing skills from other projects enables better co-usage correlation in Pass 2
- Skills from inactive projects can still be suggested if they become active

### 4. Categories vs Keywords

**Categories** are FIELDS OF COMPETENCE/USAGE:
- Broader domains: web-frontend, devops-cicd, data-ml, testing, security, etc.
- Used to build the CxC (Category-to-Category) co-usage probability matrix
- 16 predefined categories in `schemas/pss-categories.json`
- A skill has ONE primary category and optional secondary categories

**Keywords** are a SUPERSET of categories:
- Include category terms PLUS specific tools, names, actions, technologies
- Examples: "docker", "next.js", "pytest", "github actions", "fix ci pipeline"
- Used for prompt matching via `.includes()` on lowercase text
- A skill has 8-15 keywords/phrases

**The distinction matters** because:
- Only categories can build a meaningful co-usage matrix (domains have predictable relationships)
- Keywords are too specific and numerous to form a matrix
- Categories enable Pass 2 heuristic candidate selection

---

## Two-Pass Agent Swarm Architecture

### Why Two Passes?

**Pass 1** collects factual data that can be extracted by reading:
- Keywords, phrases, intents
- Description and use cases (VERBATIM)
- Category assignment

**Pass 2** requires AI reasoning that cannot be scripted:
- Determining which skills are logically co-used
- Understanding that "docker-compose" and "microservices-architecture" relate
- Reasoning that "security-audit" follows "code-review" but precedes "deployment"
- Identifying that "terraform" is an alternative to "pulumi"

Scripts can match keywords; only agents can understand semantic relationships.

### Pass 1: Discovery + Keyword Analysis

**Input:** All skill locations (user, project, plugin)

**Process:**
1. `pss_discover.py` scans all skill locations
2. Generates checklist with batches (10 skills per batch)
3. Orchestrator spawns parallel agents (one per batch)
4. Each agent reads SKILL.md files and extracts:
   - `description` - VERBATIM from frontmatter
   - `use_cases` - VERBATIM list from SKILL.md
   - `category` - assigned from 16 predefined categories
   - `keywords` - 8-15 lowercase keywords/phrases for matching
   - `intents` - action verbs (deploy, test, build, etc.)

**Output:**
- `~/.claude/cache/skill-index.json` (Pass 1 format)
- Individual `.pss` files alongside each SKILL.md

**Pass 1 .pss Format:**
```json
{
  "name": "skill-name",
  "type": "skill",
  "source": "user",
  "path": "/path/to/SKILL.md",
  "description": "VERBATIM description from SKILL.md",
  "use_cases": ["VERBATIM use case 1", "VERBATIM use case 2"],
  "category": "devops-cicd",
  "keywords": ["keyword1", "multi word phrase", ...],
  "intents": ["deploy", "build"],
  "pass": 1,
  "generated": "2026-01-19T00:00:00Z"
}
```

### Pass 2: Co-Usage Correlation (AI Intelligence)

**Input:** Pass 1 index + .pss files + CxC matrix

**Process:**
For EACH skill, spawn an agent that:

1. **Reads the skill's .pss file** (from Pass 1)
   - Notes description, use_cases, keywords, category

2. **Finds candidate skills** using two methods:
   - `skill-suggester --incomplete-mode` - keyword similarity
   - CxC matrix heuristics - category co-usage probabilities

3. **Reads candidate .pss files** to understand their use cases

4. **Uses AI intelligence** to determine co-usage relationships:
   - `usually_with` - skills used in the SAME session/task
   - `precedes` - skills typically used BEFORE this skill
   - `follows` - skills typically used AFTER this skill
   - `alternatives` - skills that solve the SAME problem differently
   - `rationale` - brief explanation of why these relationships exist

5. **Writes updated .pss file** with co_usage data

**Output:**
- Updated `.pss` files (Pass 2 format with co_usage)
- Orchestrator merges all .pss files into final `skill-index.json`

**Pass 2 .pss Format:**
```json
{
  "name": "skill-name",
  "type": "skill",
  "source": "user",
  "path": "/path/to/SKILL.md",
  "description": "VERBATIM description from SKILL.md",
  "use_cases": ["VERBATIM use case 1", "VERBATIM use case 2"],
  "category": "devops-cicd",
  "keywords": ["keyword1", "multi word phrase", ...],
  "intents": ["deploy", "build"],
  "co_usage": {
    "usually_with": ["docker-compose", "container-security"],
    "precedes": ["merge-branch", "deployment"],
    "follows": ["code-review", "testing"],
    "alternatives": ["podman"],
    "rationale": "Docker skills typically co-occur with compose for multi-container setups..."
  },
  "tier": "primary",
  "pass": 2,
  "generated": "2026-01-19T00:00:00Z"
}
```

### The `--incomplete-mode` Flag

The Rust skill-suggester binary supports `--incomplete-mode` for Pass 2:

```bash
echo '{"prompt": "keywords from skill"}' | pss --incomplete-mode --format json --top 10
```

**What it does:**
- Skips `tier_boost` scoring (populated in Pass 2)
- Skips explicit `boost` values (may not be set yet)
- Returns JSON with `pss_path` for agents to read candidate .pss files

**JSON output format:**
```json
[
  {
    "name": "candidate-skill",
    "path": "~/.claude/skills/candidate-skill/SKILL.md",
    "pss_path": "~/.claude/skills/candidate-skill/.pss",
    "score": 12.5,
    "confidence": "HIGH",
    "keywords_matched": ["docker", "container"]
  }
]
```

---

## CxC Co-Usage Matrix

Located at: `schemas/pss-categories.json`

The matrix provides probability (0.0-1.0) that skills from one category are used with another category:

```json
{
  "co_usage_matrix": {
    "web-frontend": {
      "web-backend": 0.9,
      "testing": 0.8,
      "devops-cicd": 0.7
    },
    "testing": {
      "code-quality": 0.85,
      "debugging": 0.8,
      "devops-cicd": 0.8
    }
  }
}
```

**Usage in Pass 2:**
- Agent looks up the skill's category
- Finds high-probability related categories
- Prioritizes candidate skills from those categories
- Combines with keyword-based candidates from skill-suggester

---

## Runtime Flow (Hook Execution)

```
User types prompt
    ↓
UserPromptSubmit hook fires
    ↓
pss_hook.py receives prompt via stdin
    ↓
skill-suggester binary matches against index
    ↓
Returns top candidates with scores
    ↓
Agent receives suggestions
    ↓
Agent compares against its known available_skills
    ↓
Agent filters out unavailable suggestions
    ↓
Agent presents relevant suggestions to user
```

**Key point:** The hook doesn't validate availability - the agent does, using its context-injected skills list.

### Hook Mode vs Agent-Profile Mode

- **Hook mode** (`--format hook`, UserPromptSubmit): Suggests **skills and agents only**. Rules, MCP servers, and LSP servers are configuration elements and not useful as prompt-time suggestions.
- **Agent-profile mode** (`--agent-profile`): Returns **all 6 types** (skills, agents, commands, rules, MCP, LSP) grouped by type. Used by `/pss-setup-agent` to generate complete `.agent.toml` files.

---

## File Locations

| File | Purpose |
|------|---------|
| `~/.claude/cache/skill-index.json` | Global skill index (Pass 1 or Pass 2) |
| `<skill-dir>/.pss` | Per-skill metadata file alongside SKILL.md |
| `schemas/pss-categories.json` | Category definitions + CxC matrix |
| `schemas/pss-schema.json` | JSON schema for .pss files |
| `schemas/pss-skill-index-schema.json` | JSON schema for skill-index.json |
| `rust/skill-suggester/bin/pss-<platform>` | Pre-compiled skill-suggester binaries |

---

## What NOT to Implement

1. **No staleness detection** - regenerate from scratch instead
2. **No file existence checks** - agent validates against available skills
3. **No incremental updates** - full regeneration is simpler and reliable
4. **No hash-based change detection** - adds complexity without value
5. **No cleanup scripts** - the index is a superset by design

---

## VERBATIM Rule

**CRITICAL:** `description` and `use_cases` fields MUST be copied VERBATIM from SKILL.md.

- NEVER paraphrase or summarize
- NEVER rewrite for "clarity"
- Copy exactly as written in the source

This ensures:
- Consistent matching behavior
- No semantic drift from original intent
- Reproducible results across reindexing
