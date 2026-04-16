# Perfect Skill Suggester (PSS) Architecture

## Phase B transition (v2.11.0) — CozoDB is canonical, JSON is a derived export

Starting with v2.11.0, **CozoDB is the single source of truth** for the PSS
element index. The `scripts/pss_merge_queue.py` writer now calls
`scripts/pss_cozodb.py::atomic_write_cozodb` directly after every merge,
producing all 33 columns on the `skills` relation, the 9 normalised
auxiliary relations (`skill_keywords`, `skill_intents`, `skill_tools`,
`skill_services`, `skill_frameworks`, `skill_languages`, `skill_platforms`,
`skill_domains`, `skill_file_types`), the `kw_lookup` trigram pre-filter,
the `skill_ids` ID→(name, source) lookup, and `pss_metadata` (version,
generated, generator).

**The runtime hook path is unchanged.** The Rust binary's
`load_candidates_from_db` continues to query the same schema — only the
write direction flipped.

**`skill-index.json` is retained as a derived export** for two reasons:

1. Backwards compatibility with the handful of Python scripts that still
   parse it (`pss_make_plugin.py`, `pss_verify_profile.py`, etc. — Phase C
   migrates them to pycozo queries).
2. Debugging: power users can `git diff` successive snapshots to spot
   drift. Use `pss export --json [--path P]` (new in v2.11.0) to dump the
   current CozoDB to any path.

**The Rust `pss --build-db` subcommand is now a no-op** when called against
a CozoDB whose `pss_metadata.generator` field equals `python-merge-queue`.
It logs `CozoDB already built by Python merge (Phase B); skipping
redundant rebuild` and exits 0. Legacy JSON-only installs (no CozoDB yet)
still fall through to the full rebuild path for migration. Phase C
(v3.0.0) removes this subcommand entirely.

**Timestamp preservation** across rebuilds is enforced by Python the same
way Rust used to do it: snapshot `(name, source) → first_indexed_at` from
the prior DB before `:replace`, then re-apply on insert. Empty values mean
"new install" → stamp with now. The Python implementation and the Rust
implementation produce byte-identical rows — verified by
`test_fnv1a_entry_id_matches_rust_for_react_user` against the live DB.

**Why we did this:** see `design/tasks/TRDD-46ac514e-3627-44a6-b916-f37a1504b969-cozodb-unification.md`.
The one-line summary: with two independent stores, any writer can silently
desync one from the other — and that's exactly what happened in the
v2.9.40 incident that triggered this migration. One store, one path, one
writer.

---

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

> **v2.1.0**: PSS now indexes 6 element types: **skills**, **agents**, **commands**, **rules**, **MCP servers**, and **LSP servers**. The term "skill" in this document refers to any indexed element unless otherwise specified.

**NEW in PSS 1.0:** The discovery script can scan ALL projects registered in `~/.claude.json`, not just the current project.

**Skill Discovery Sources:**

| Source | Location | Flag Required |
|--------|----------|---------------|
| User-level | `~/.claude/skills/` | Always scanned |
| Current project | `.claude/skills/` | Always scanned |
| Plugin cache | `~/.claude/plugins/cache/*/*/skills/` | Always scanned |
| Local plugins | `~/.claude/plugins/*/skills/` | Always scanned |
| Current project plugins | `.claude/plugins/*/skills/` | Always scanned |
| **All other projects** | `<project>/.claude/skills/` and `<project>/.claude/plugins/*/skills/` | Always scanned (default) |
| Agents | `~/.claude/agents/`, `.claude/agents/`, plugin `agents/` | Always scanned |
| Commands | `~/.claude/commands/`, `.claude/commands/`, plugin `commands/` | Always scanned |
| Rules | `~/.claude/rules/`, `.claude/rules/` | Always scanned |
| MCP servers | `~/.claude.json`, `.mcp.json` | Always scanned |
| LSP servers | `~/.claude/settings.json` enabledPlugins | Always scanned |
| **Inactive plugins** | Plugins with enabledPlugins=false in settings.json | Excluded with **`--exclude-inactive-plugins`** |

**Usage:**
```bash
# Standard discovery (current project + global + all projects)
python3 pss_discover.py

# Exclude plugins marked as inactive in settings.json
python3 pss_discover.py --exclude-inactive-plugins
```

**Deleted Project Handling:**
Projects in `~/.claude.json` that no longer exist on disk are automatically skipped with a warning. No error is raised.

**Why This Matters:**
- The index is a superset of ALL skills ever indexed
- The agent filters suggestions against its context-injected available skills
- Indexing skills from other projects enables better co-usage correlation in Pass 2
- Skills from inactive projects can still be suggested if they become active

### Claude Code Plugin Registry Format (installed_plugins.json v2)

Claude Code 2.1.69+ uses `~/.claude/plugins/installed_plugins.json` **version 2** format. Any script or agent that reads or writes this file MUST use the correct format. Writing v1 format causes Claude Code to rebuild the file on next sync, **silently dropping plugins**.

**v2 format** (correct):
```json
{
  "version": 2,
  "plugins": {
    "plugin-name@marketplace-name": [
      {
        "scope": "user",
        "installPath": "~/.claude/plugins/cache/marketplace/plugin/version",
        "version": "1.0.0",
        "installedAt": "2026-01-01T00:00:00.000Z",
        "lastUpdated": "2026-01-01T00:00:00.000Z",
        "gitCommitSha": "abc123def456..."
      }
    ]
  }
}
```

**Key differences from v1:**
| Field | v1 (OBSOLETE) | v2 (CURRENT) |
|-------|---------------|--------------|
| Root `version` | absent | `2` (required) |
| Plugin value | flat `{}` dict | `[{}]` list of scope entries |
| `scope` field | absent | `"user"` or `"project"` |
| `installPath` | absent | full path to cached plugin |
| `isLocal` | present | **removed** — do not use |
| `gitCommitSha` | absent | commit SHA from marketplace |

**Critical rules:**
- Each plugin key is `"name@marketplace"` (e.g., `"perfect-skill-suggester@emasoft-plugins"`)
- The value is always a **list** (array), even for a single scope entry
- `scope` must be `"user"` or `"project"` — never omit it
- `installPath` must point to the versioned cache directory
- Never include `isLocal` — it is not part of the v2 schema
- If migrating from v1: wrap each flat dict in a list and add `"version": 2` at root

**Related files:**
- `~/.claude/plugins/installed_plugins.json` — the registry itself
- `~/.claude/plugins/known_marketplaces.json` — marketplace metadata (source URLs, install locations)
- `~/.claude/plugins/blocklist.json` — blocked plugins (fetched from Anthropic)
- `~/.claude/settings.json` → `enabledPlugins` — per-plugin enable/disable toggles

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

## Declared Hook Events

As of v2.9.34+, PSS declares three Claude Code hook events in `hooks/hooks.json`:

| Event | Matcher | Handler | Purpose |
|-------|---------|---------|---------|
| `UserPromptSubmit` | (none) | `scripts/pss_hook.py` | Primary — scores skill suggestions on every user prompt |
| `SessionStart` | `startup\|resume` | `pss_hook.py --warm-index &` | Silent lazy warmup — spawns background reindex if the skill-index cache is missing, so the first prompt never blocks on index build |
| `PostCompact` | (none) | `pss_hook.py --post-compact` | Stub — reserves the event binding for future re-suggest-after-compaction logic |

All three hooks use `timeout` values in **seconds** (per CC hooks.md spec): 10s for UserPromptSubmit, 5s for SessionStart and PostCompact. See [`docs/CC-COMPATIBILITY.md`](CC-COMPATIBILITY.md) for the full CC version-by-version matrix and hook schema notes.

### Hook Input/Output Schema

- **CC → Python hook**: `scripts/pss_hook.py` reads `transcript_path` (snake_case), matching CC hooks.md "Common input fields".
- **Python → Rust binary**: `pss_hook.py` forwards `{prompt, cwd, transcript_path}` to the scorer as snake_case JSON. The Rust `HookInput` struct uses default serde naming (no `rename_all`).
- **Rust binary → CC**: `HookOutput` and `HookSpecificOutput` structs keep `#[serde(rename_all = "camelCase")]` because CC's hook-reply format requires camelCase (`hookSpecificOutput`, `hookEventName`, `additionalContext`).

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

### Runtime Modes

The Rust binary operates in two modes:

1. **Hook mode** (`--format hook`): Real-time skill suggestion during user prompt submission. Returns top matches with confidence levels. Used by `pss_hook.py` in the `UserPromptSubmit` hook.

2. **Agent-profile mode** (`--agent-profile`): Batch scoring of ALL indexed elements against an agent's requirements. Returns scored candidates across all 6 element types for the `pss-agent-profiler` agent to post-filter. Used by `/pss-setup-agent`.

---

## Scoring Gates

Two independent filtering mechanisms run before the main scoring loop. Both are hard binary filters — a failing entry is excluded entirely, not penalized.

### Domain Gates (`domain_gates`)

Introduced in v2.7.0. Hard prerequisite filters: each entry declares zero or more gates (e.g. `{"programming_language": ["python", "python3"]}`), and ALL gates must pass for the skill to be scored. A gate passes when its corresponding domain is detected in the prompt AND at least one gate keyword appears.

- **Purpose**: prevent Swift skills from matching Python prompts even if keywords overlap
- **Implementation**: `check_domain_gates()` in `rust/skill-suggester/src/main.rs`
- **Populated at**: Pass 1 enrichment from `languages`/`frameworks`/`platforms` extraction
- **Bypass**: when a framework/tool name from the skill appears verbatim in the prompt

### Rule Path Gates (`path_gates`)

Introduced in v2.9.35. Rule-only activation globs from rule frontmatter `paths:` field per the CC rules spec:

```yaml
---
paths:
  - "**/*.py"
  - "src/**/*.pyi"
---
```

When a rule declares `paths:`, it is excluded from suggestions unless at least one glob's trailing extension matches the project's file types OR the project's detected languages (mapped via `language_to_extensions()`). Non-extension globs like `src/**` or `Dockerfile*` pass permissively because PSS doesn't do full cwd glob walking yet.

- **Purpose**: honor CC's rule path-scoping in PSS's suggestion pipeline
- **Implementation**: `check_path_gates()` in `rust/skill-suggester/src/main.rs`
- **Orthogonal to domain gates**: runs unconditionally even when the domain registry is absent
- **Storage**: JSON column `path_gates_json` in CozoDB `skills` table (v2.9.37+)

---

## Plugin Generation

`commands/pss-make-plugin-from-profile.md` (implemented by `scripts/pss_make_plugin.py`) produces a fully-installable Claude Code plugin from a `.agent.toml` profile. The generator reads optional sections and propagates them verbatim into the output `plugin.json`:

- **`[metadata]`** (v2.9.34+): `homepage`, `repository`, `license` — pass-through strings
- **`[userConfig]`** (v2.9.35+): opaque dict copied verbatim into `plugin.json.userConfig` per the CC plugins-reference.md schema; PSS does NOT validate the nested structure

Both sections are guarded with `isinstance(value, dict)` so malformed profiles don't crash the generator.

---

## File Locations

| File | Purpose |
|------|---------|
| `~/.claude/cache/skill-index.json` | Global skill index (Pass 1 or Pass 2) |
| `<skill-dir>/.pss` | Per-skill metadata file alongside SKILL.md |
| `schemas/pss-categories.json` | Category definitions + CxC matrix |
| `schemas/pss-schema.json` | JSON schema for .pss files |
| `schemas/pss-skill-index-schema.json` | JSON schema for skill-index.json |
| `bin/pss-<platform>` | Pre-compiled skill-suggester binaries |
| `scripts/pss_verify_profile.py` | Element name verification against skill index (anti-hallucination) |
| `skills/pss-design-alignment/` | Requirements alignment skill (two-pass scoring) |
| `commands/pss-change-agent-profile.md` | Natural language profile modification command |

---

## What NOT to Implement

1. **No staleness detection** - regenerate from scratch instead
2. **No file existence checks** - agent validates against available skills
3. **No incremental updates** - full regeneration is simpler and reliable
4. **No hash-based change detection** - adds complexity without value
5. **No cleanup scripts** - the index is a superset by design

### Agent TOML Generation (v2.3.0)

The `/pss-setup-agent` command + `pss-agent-profiler` agent generate `.agent.toml` configuration files.

**Key capabilities:**
- **Two-pass scoring**: agent definition scored separately from project requirements
- **Anti-hallucination verification**: all element names cross-checked against skill index
- **Change mode**: modify existing profiles with natural language via `/pss-change-agent-profile`

**Pipeline steps:**

1. **Discovery**: Analyze agent definition (.md) + optional requirements docs
2. **Two-Pass Scoring**:
   - **Pass 1** (agent-only): Rust binary scores elements against agent descriptor → baseline candidates
   - **Pass 2** (requirements-only): Rust binary scores elements against requirements descriptor → project-level candidates
3. **Specialization Cherry-Pick**: For each requirements candidate, evaluate domain overlap + duty matching + practical usage test. Only elements matching the agent's specialization are accepted (pss-design-alignment skill).
4. **AI Post-filtering**: Profiler agent applies intelligent filters:
   - Mutual exclusivity (e.g., Jest vs Vitest, React vs Vue)
   - Stack compatibility (language/framework alignment)
   - Redundancy pruning (overlapping capabilities)
5. **Tier assignment**: Elements sorted into primary/secondary/specialized tiers
6. **Validation**: `pss_validate_agent_toml.py` checks schema conformance + index cross-reference
7. **Element Verification**: `pss_verify_profile.py` checks ALL element names against the skill index (anti-hallucination). Detects misspelled names, wrong-type placements, and missing elements with fuzzy correction suggestions.
8. **Profile Modification**: `/pss-change-agent-profile` modifies existing profiles with natural language instructions, re-verifying after each change.

### Element Verification (Anti-Hallucination)

The `pss_verify_profile.py` script validates all element names in `.agent.toml` against the skill index:

| Check | Description |
|-------|-------------|
| Index lookup | Every skill/agent/command/rule/MCP/LSP name must exist in `skill-index.json` |
| Agent-defined names | Names from the agent's own plugin are marked as "agent-defined", not flagged |
| Auto-skills pinning | Skills listed in frontmatter `auto_skills:` must be in primary tier |
| Non-coding filter | Orchestrators/coordinators should not have LSP/linting/code-fixing elements |
| Fuzzy correction | Misspelled names get closest-match suggestions with hyphen/underscore normalization |
| Force include/exclude | User-specified restrictions are enforced |

```bash
uv run scripts/pss_verify_profile.py <file.agent.toml> --agent-def <agent.md> --verbose
uv run scripts/pss_verify_profile.py <file.agent.toml> --auto-fix  # Auto-correct misspellings
```

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

---

## Rust CLI reference (Phase D, v2.11.0+)

The `pss` binary exposes query and management subcommands that mirror the
Python helpers in `scripts/pss_cozodb.py` but run natively against the CozoDB
— no Python process, no pycozo import, no FFI hop. Use these when scripting
from a shell, building CI gates, or diagnosing the live index interactively.

All subcommands are read-only (no writes to the DB) and support a `--json`
flag (default `false`) that switches from human-readable tabular output to
JSON suitable for `jq` piping. Timestamp filters accept three date formats:

- **RFC 3339**: `2026-04-16T22:12:27Z` or `2026-04-16T22:12:27+00:00`
- **Date only**: `2026-04-16` (interpreted as 00:00:00 UTC)
- **Relative to now**: `1d`, `2w`, `24h`, `30m`, `120s`

### Index inventory

```bash
pss count                           # Plain integer on stdout
pss count --json                    # {"count": 8479}

pss stats                           # JSON (legacy default)
pss stats --format table            # Human-readable banner + counts-by-X

pss health; echo $?                 # 0=populated, 1=empty/corrupt, 2=missing
pss health --verbose                # Prints "OK (8479 entries)" etc.
```

`pss stats` prints a banner as of v2.11.0:

```
Total: 8479 entries
Oldest first_indexed_at: 2026-04-16T22:12:27Z (entry: some-skill)
Newest first_indexed_at: 2026-04-17T05:33:12Z (entry: newly-installed)
Last reindex (newest last_updated_at): 2026-04-17T10:00:00Z
```

### Lookup by identity

```bash
pss get tailwind-4-docs             # Fetch a single entry (human format)
pss get tailwind-4-docs --json      # Fetch as JSON
pss get react --source user         # Disambiguate when multiple sources share a name
```

Exits non-zero if no entry matches. When `--source` is omitted and multiple
rows match, JSON output becomes an array; human output becomes one block per
row separated by a blank line.

### Timestamp-based filters

These commands read `first_indexed_at` (install time) or `last_updated_at`
(reindex time) on the `skills` relation. Both are RFC 3339 UTC strings
written by the Python writer (Phase B).

```bash
pss list-added-since 1d                             # Last 24h
pss list-added-since 2026-04-16                     # Since midnight on that date
pss list-added-since 2026-04-16T22:12:27Z --limit 100

pss list-added-between 2026-04-01 2026-04-16 --limit 200
pss list-updated-since 1w                           # Any entry touched in last 7 days
```

Output columns: `TYPE NAME SOURCE FIRST_INDEXED_AT DESCRIPTION` (or
`LAST_UPDATED_AT` for the updated-since variant). Default limit is 50.
Invalid datetimes fail fast with a clear error, never silently defaulting
to "now".

### Content-based filters

```bash
pss find-by-name docker --limit 20                  # Substring on name column
pss find-by-keyword kubernetes --json               # Exact match via skill_keywords
pss find-by-domain security                         # Via skill_domains
pss find-by-language python                         # Via skill_languages
```

All four `find-by-*` commands default to a 50-row limit. `find-by-name` is
case-insensitive substring; the others hit the normalised auxiliary
relations (`skill_keywords`, `skill_domains`, `skill_languages`) for exact
match.

### Snapshot export

```bash
pss export --json                                   # Write to $CLAUDE_PLUGIN_DATA/skill-index.export.json
pss export --json --path /tmp/my-snapshot.json      # Custom path
```

The default destination is `$CLAUDE_PLUGIN_DATA/skill-index.export.json`
(falling back to `~/.claude/cache/skill-index.export.json` if the env var
is unset). Atomic write via temp file + rename.

### Parallel Python API

All of the above are also exposed as Python helpers in
`scripts/pss_cozodb.py`:

| Rust CLI                           | Python equivalent                                 |
|------------------------------------|---------------------------------------------------|
| `pss count`                        | `count_skills()`                                  |
| `pss health`                       | `db_is_healthy()`                                 |
| `pss get <name> [--source S]`      | `get_by_name(name, source=...)`                   |
| `pss list-added-since <when>`      | `added_since(when, limit=...)`                    |
| `pss list-added-between <a> <b>`   | `added_between(a, b, limit=...)`                  |
| `pss list-updated-since <when>`    | `updated_since(when, limit=...)`                  |
| `pss find-by-name <sub>`           | `search_by_name(sub, limit=...)`                  |
| `pss find-by-keyword <kw>`         | `search_by_keyword(kw, limit=...)`                |
| `pss find-by-domain <d>`           | `search_by_domain(d, limit=...)`                  |
| `pss find-by-language <l>`         | `search_by_language(l, limit=...)`                |
| `pss export --json --path P`       | `export_json_snapshot(P)`                         |

Use the Python helpers from scripts that already import pycozo; use the
Rust CLI everywhere else (shell pipelines, CI, ad-hoc inspection).
