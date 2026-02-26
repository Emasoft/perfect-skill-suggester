---
name: pss-reindex-skills
description: "Scan ALL elements (skills, agents, commands, rules, MCP, LSP) and generate AI-analyzed keyword/phrase index."
argument-hint: "[--batch-size N] [--pass1-only] [--pass2-only] [--all-projects]"
allowed-tools: ["Bash", "Read", "Write", "Glob", "Grep", "Task"]
---

# PSS Reindex Skills Command

> ## ⛔ CRITICAL: FULL REGENERATION ONLY - NO INCREMENTAL UPDATES
>
> **This command ALWAYS performs a complete reindex from scratch.**
>
> **PHASE 0 (MANDATORY):** Before ANY discovery or analysis, the agent MUST:
> 1. Delete `~/.claude/cache/skill-index.json`
> 2. Delete `~/.claude/cache/skill-checklist.md`
> 3. Verify clean slate before proceeding
>
> **WHY?** Incremental indexing causes: stale version paths, orphaned entries, name mismatches, missing new skills.
> **The ONLY reliable approach is DELETE → DISCOVER → REINDEX from scratch.**
>
> **⚠️ NEVER skip Phase 0. NEVER do partial/incremental updates. ALWAYS regenerate completely.**

## Cross-Platform Temp Directory

Before executing any phase, determine the system temp directory:
```bash
PSS_TMPDIR=$(python3 -c "import tempfile; print(tempfile.gettempdir())")
```
All temporary paths below use `${PSS_TMPDIR}` as the base. This resolves to `/tmp` on Linux, a system temp dir on macOS, and the user's temp folder on Windows.

---

Generate an **AI-analyzed** keyword and phrase index for ALL skills available to Claude Code. Unlike heuristic approaches, this command has the agent **read and understand each skill** to formulate optimal activation patterns.

This is the **MOST IMPORTANT** feature of Perfect Skill Suggester - AI-generated keywords ensure 88%+ accuracy in skill matching.

> **Architecture Reference:** See [docs/PSS-ARCHITECTURE.md](../docs/PSS-ARCHITECTURE.md) for the complete design rationale.

## Two-Pass Architecture

PSS uses a sophisticated two-pass agent swarm to generate both keywords AND co-usage relationships:

### Pass 1: Discovery + Keyword Analysis
The Python script `pss_discover.py` scans ALL element locations (skills, agents, commands, rules, MCP servers, LSP servers). Parallel agents then read each element's definition file and formulate **rio-compatible keywords**. All element types produce the same output fields (keywords, intents, category, patterns, etc.):
- **Single keywords**: `docker`, `test`, `deploy`
- **Multi-word phrases**: `fix ci pipeline`, `review pull request`, `set up github actions`
- **Error patterns**: `build failed`, `type error`, `connection refused`

**Output**: `skill-index.json` with keywords (Pass 1 format - keywords only, merged incrementally via pss_merge_queue.py)

### Pass 2: Co-Usage Correlation (AI Intelligence)
For EACH skill, a dedicated agent:
1. Reads the skill's data from the skill-index.json (from Pass 1)
2. Calls `skill-suggester --incomplete-mode` to find CANDIDATE skills via keyword similarity + CxC matrix heuristics
3. Reads candidate data from skill-index.json to understand their use cases
4. **Uses its own AI intelligence** to determine which skills are logically co-used
5. Writes co-usage data to a temp .pss file and merges it into the global index via pss_merge_queue.py

**Why Pass 2 requires agents (not scripts)**:
- Only AI can understand that "docker-compose" and "microservices-architecture" are logically related
- Only AI can reason that "security-audit" typically FOLLOWS "code-review" but PRECEDES "deployment"
- Only AI can identify that "terraform" is an ALTERNATIVE to "pulumi" for infrastructure
- Scripts can only match keywords; agents understand semantic relationships

**Rio Compatibility**: Keywords are stored in a flat array and matched using `.includes()` against the lowercase user prompt. The `matchCount` is simply the number of matching keywords.

## CRITICAL: ALWAYS FULL REGENERATION - NO INCREMENTAL UPDATES

> **⚠️ MANDATORY RULE:** PSS reindexing MUST ALWAYS be a complete regeneration from scratch.
> **NEVER** attempt incremental updates or skip skills that "already exist" in the index.
>
> **Why?** Incremental indexing causes:
> - Stale version paths (plugins update, old paths remain)
> - Missing skills (new skills in updated plugins not detected)
> - Orphaned entries (deleted skills remain in index)
> - Name mismatches (skill renamed but old name persists)
>
> **The ONLY reliable approach is DELETE → DISCOVER → REINDEX from scratch.**

## Usage

```
/pss-reindex-skills [--batch-size 20] [--pass1-only] [--pass2-only] [--all-projects]
```

| Flag | Description |
|------|-------------|
| `--batch-size N` | Skills per batch (default: 10) |
| `--pass1-only` | Run Pass 1 only (keywords, no co-usage) |
| `--pass2-only` | Run Pass 2 only (requires existing Pass 1 index) |
| `--all-projects` | Scan ALL projects registered in `~/.claude.json` |

**REMOVED FLAGS:**
- ~~`--force`~~ - No longer needed, full reindex is ALWAYS performed
- ~~`--skill NAME`~~ - Single-skill reindex removed to prevent partial updates

## Comprehensive Skill Discovery

**By default**, the discovery script scans:
1. User-level skills: `~/.claude/skills/`
2. Current project skills: `.claude/skills/`
3. Plugin cache: `~/.claude/plugins/cache/*/`
4. Local plugins: `~/.claude/plugins/*/skills/`
5. Current project plugins: `.claude/plugins/*/skills/`
6. Agents: `~/.claude/agents/`, `.claude/agents/`, plugin agents/
7. Commands: `~/.claude/commands/`, `.claude/commands/`, plugin commands/
8. Rules: `~/.claude/rules/`, `.claude/rules/`
9. MCP servers: `~/.claude.json`, `.mcp.json`
10. LSP servers: `~/.claude/settings.json` enabled plugins

**With `--all-projects`**, it ALSO scans:
11. ALL projects registered in `~/.claude.json`:
   - `<project>/.claude/skills/`
   - `<project>/.claude/plugins/*/skills/`

This creates a **superset index** containing ALL skills across all your projects. At runtime, the agent filters suggestions against its context-injected available skills list (see `docs/PSS-ARCHITECTURE.md`).

**NOTE:** Deleted projects are automatically detected and skipped with a warning.

## Execution Protocol

### AGENT TASK CHECKLIST (MANDATORY - CREATE BEFORE ANY WORK)

> **⛔ BEFORE EXECUTING ANY STEP, the agent MUST create a task list using TaskCreate.**
> **This checklist MUST be tracked and updated throughout the reindex process.**

**Create these tasks IN THIS EXACT ORDER using TaskCreate:**

```
1. [Phase 0] Create backup directory in system temp
2. [Phase 0] Backup and remove skill-index.json
3. [Phase 0] Backup and remove skill-checklist.md
4. [Phase 0] VERIFY clean slate - no index files remain
5. [Phase 0.5] Run pss_cleanup.py --all-projects to remove stale .pss files
6. [Phase 1] Run discovery script to generate skill checklist
7. [Phase 1] Spawn Pass 1 batch agents for keyword analysis
8. [Phase 1] Validate Pass 1 index (run CPV plugin validator: uv run --with pyyaml python scripts/validate_plugin.py . --verbose)
9. [Phase 1] Check agent tracking files for missed skills, re-run if needed
10. [Phase 2] Spawn Pass 2 batch agents for co-usage analysis
11. [Phase 2] Validate final index (run CPV plugin validator: uv run --with pyyaml python scripts/validate_plugin.py . --verbose)
12. [Phase 2] Check agent tracking files for missed skills, re-run if needed
13. [Verify] Confirm index has pass:2 and all skills have co_usage
14. [Report] Report final statistics to user
```

**CRITICAL RULES:**
- Tasks 1-4 (Phase 0) MUST ALL be marked `completed` BEFORE starting task 5
- Task 5 (Phase 0.5 cleanup) MUST complete before starting task 6
- If task 4 verification FAILS, do NOT proceed - mark remaining tasks as blocked
- Update task status to `in_progress` when starting, `completed` when done
- If ANY Phase 0 task fails, STOP and report error to user

**Example TaskCreate call for first task:**
```
TaskCreate({
  subject: "[Phase 0] Create backup directory in system temp",
  description: "Create timestamped backup dir: ${PSS_TMPDIR}/pss-backup-YYYYMMDD_HHMMSS",
  activeForm: "Creating backup directory"
})
```

---

### PHASE 0: CLEAN SLATE (MANDATORY - NEVER SKIP - NON-NEGOTIABLE)

> **⛔ THIS PHASE IS MANDATORY AND NON-NEGOTIABLE.**
> **You MUST complete ALL steps before proceeding to Phase 1.**
> **If ANY step fails, STOP and report the error. Do NOT proceed.**

Before discovering or analyzing ANY skills, you MUST backup and delete ALL previous index data.
The backup ensures the old data is preserved for debugging, but moved out of the way so it can
NEVER interfere with the fresh reindex.

```bash
# Step 0.0: Create timestamped backup folder and ensure pss-queue dir exists
BACKUP_DIR="${PSS_TMPDIR}/pss-backup-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
mkdir -p ${PSS_TMPDIR}/pss-queue
echo "$BACKUP_DIR" > ${PSS_TMPDIR}/pss-queue/backup-dir.txt
echo "Backup directory: $BACKUP_DIR"

# Step 0.1: Backup and delete the main skill index
if [ -f ~/.claude/cache/skill-index.json ]; then
    mv ~/.claude/cache/skill-index.json "$BACKUP_DIR/"
    echo "✓ skill-index.json moved to backup"
else
    echo "○ skill-index.json did not exist"
fi

# Step 0.2: Backup and delete the skill checklist
if [ -f ~/.claude/cache/skill-checklist.md ]; then
    mv ~/.claude/cache/skill-checklist.md "$BACKUP_DIR/"
    echo "✓ skill-checklist.md moved to backup"
else
    echo "○ skill-checklist.md did not exist"
fi

# Step 0.3: VERIFY CLEAN SLATE (MANDATORY CHECK)
echo ""
echo "=== VERIFICATION ==="
if [ -f ~/.claude/cache/skill-index.json ]; then
    echo "❌ FATAL ERROR: skill-index.json still exists!"
    echo "Phase 0 FAILED. Cannot proceed."
    exit 1
fi

echo "✅ CLEAN SLATE VERIFIED"
echo "   - No skill-index.json"
echo "   - Backup at: $BACKUP_DIR"
echo ""
echo "Proceeding to Phase 1: Discovery..."
```

**IMPORTANT: PERSIST $BACKUP_DIR**
The orchestrator MUST remember the `$BACKUP_DIR` path for the rest of the reindex process.
The post-reindex validator needs this path to restore the backup if validation fails.
Store it in a variable or write it to `${PSS_TMPDIR}/pss-queue/backup-dir.txt`:
```bash
echo "$BACKUP_DIR" > ${PSS_TMPDIR}/pss-queue/backup-dir.txt
```

**CHECKLIST (ALL MUST BE CHECKED BEFORE PROCEEDING):**
- [ ] Backup directory created in `${PSS_TMPDIR}`
- [ ] `$BACKUP_DIR` path persisted to `${PSS_TMPDIR}/pss-queue/backup-dir.txt`
- [ ] `skill-index.json` moved to backup (or did not exist)
- [ ] `skill-checklist.md` moved to backup (or did not exist)
- [ ] **VERIFICATION PASSED**: No index files remain

**⛔ IF VERIFICATION FAILS, DO NOT PROCEED. Report the error and stop.**

**WHY THIS IS NON-NEGOTIABLE:**
1. Old index paths point to outdated plugin versions → skills not found
2. Renamed/moved skills create orphaned entries → phantom skills suggested
3. Skills with wrong names persist → matching fails silently
4. Deleted skills remain as phantom entries → broken suggestions
5. Co-usage data references non-existent skills → cascading errors
6. **ANY remnant of old data will corrupt the fresh index**

**The backup in `${PSS_TMPDIR}` ensures you can debug issues if needed, but the old data is GONE from the active paths.**

---

### PHASE 0.5: CLEAN STALE .PSS FILES (MANDATORY)

> **Run AFTER Phase 0 backup/deletion, BEFORE Phase 1 discovery.**
> This removes orphaned .pss files left by crashed agents or previous runs.

```bash
# Clean ALL stale .pss files system-wide (skill dirs + ${PSS_TMPDIR}/pss-queue/)
python3 "${PLUGIN_ROOT}/scripts/pss_cleanup.py" --all-projects --verbose
```

**What this does:**
- Scans ALL skill locations (user, project, plugin cache, local plugins, all projects)
- Removes any `*.pss` files found in skill directories (leftovers from pss_generate.py)
- Removes any `*.pss` files in `${PSS_TMPDIR}/pss-queue/` (leftovers from crashed agents)
- Reports count of files deleted per location

**If cleanup reports 0 files:** Good — no stale files existed. Proceed.
**If cleanup reports N files:** Files were cleaned. Proceed to Phase 1.
**If cleanup fails (exit code 1):** Non-fatal warning — log it and proceed to Phase 1.

---

### Step 1: Generate Skill Checklist

Run the discovery script with `--checklist` and `--all-projects` to generate a markdown checklist with batches:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pss_discover.py --checklist --batch-size 10 --all-projects
```

This creates `~/.claude/cache/skill-checklist.md` with:
- All elements (skills, agents, commands, rules, MCP, LSP) organized into batches (default: 10 per batch)
- Checkbox format for tracking progress
- Agent assignment suggestions (Agent A, B, C, etc.)

Example output:
```
Checklist written to: /Users/you/.claude/cache/skill-checklist.md
  350 elements in 35 batches
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

**IMPORTANT: MODEL SELECTION**
- Pass 1 agents MUST use `model: haiku` (factual extraction only - cheap)
- Pass 2 agents MUST use `model: haiku` (guided co-usage with decision gates)
- The orchestrator (you) runs on the parent model (Sonnet/Opus)

**IMPORTANT: PROMPT TEMPLATES**
The full Haiku-optimized prompts are in external template files:
- **Pass 1**: Read `${CLAUDE_PLUGIN_ROOT}/prompts/pass1-haiku.md` for the complete template
- **Pass 2**: Read `${CLAUDE_PLUGIN_ROOT}/prompts/pass2-haiku.md` for the complete template

Read the appropriate template file, fill in the {variables}, and pass it to the haiku subagent.

**IMPORTANT: TRIPLE VERIFICATION**
Both templates include mandatory triple-read verification steps where the agent re-reads the SKILL.md
2 additional times to cross-check its extraction results. This compensates for Haiku's lower accuracy.
Do NOT remove or skip these verification steps.

**IMPORTANT: AGENT REPORTING**
All agents must return ONLY a 1-2 line summary. No code blocks, no verbose output.
Format: `[DONE/PARTIAL/FAILED] Pass N Batch M - count/total skills processed`

Each subagent receives the prompt built from the external template file.

**HOW TO BUILD THE PASS 1 PROMPT:**

1. Read the template file: `${CLAUDE_PLUGIN_ROOT}/prompts/pass1-haiku.md`
2. Copy the content between `## TEMPLATE START` and `## TEMPLATE END`
3. Replace these variables:
   - `{batch_num}` → the batch number (e.g., 3)
   - `{start}` → first skill number in batch (e.g., 21)
   - `{end}` → last skill number in batch (e.g., 30)
   - `{list_of_skill_paths}` → newline-separated list of skill paths with source and name
4. Replace `${CLAUDE_PLUGIN_ROOT}` with the absolute path to the plugin directory
5. Send the filled template to the haiku subagent

**CRITICAL**: The `${CLAUDE_PLUGIN_ROOT}` variable may NOT be available inside subagents.
You MUST resolve it to an absolute path BEFORE sending the prompt. Example:
```bash
# Resolve plugin root path first
PLUGIN_ROOT=$(cd "${CLAUDE_PLUGIN_ROOT}" && pwd)
# Then replace ${CLAUDE_PLUGIN_ROOT} with $PLUGIN_ROOT in the template
```

**BUILDING {skill_tracking_rows} (MANDATORY):**

Both Pass 1 and Pass 2 templates include a `{skill_tracking_rows}` variable for the batch tracking checklist.
You MUST build this from the batch's skill list. Format:

```
| 1 | skill-name-one | PENDING | NO |
| 2 | skill-name-two | PENDING | NO |
| 3 | skill-name-three | PENDING | NO |
```

Each row has: sequential number, skill name, Status (initially PENDING), Merged (initially NO).
The agent will update this file as it processes each skill.

### Step 4: Compile Index

Merge all subagent responses into the master index (rio v2.0 compatible format with PSS extensions):

```json
{
  "version": "3.0",
  "generated": "2026-01-18T06:00:00Z",
  "generator": "ai-analyzed",
  "skill_count": 216,
  "skills": {
    "devops-expert": {
      "source": "user",
      "path": "/path/to/SKILL.md",
      "type": "skill",
      "keywords": ["github", "actions", "ci", "cd", "pipeline", "deploy", "github actions", "ci pipeline", "workflow failed", "set up ci"],
      "intents": ["deploy", "build", "test", "release"],
      "patterns": ["workflow.*failed", "ci.*error", "deploy.*stuck"],
      "directories": ["workflows", ".github"],
      "description": "CI/CD pipeline configuration and GitHub Actions workflows",
      "platforms": ["universal"],
      "frameworks": [],
      "languages": ["any"],
      "domain_gates": {}
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
| `platforms` | string[] | PSS: Target platforms (`ios`, `android`, `macos`, `windows`, `linux`, `web`, `universal`) |
| `frameworks` | string[] | PSS: EXACT framework names extracted from skill (`react`, `django`, `swiftui`, etc.) |
| `languages` | string[] | PSS: Target languages (`swift`, `rust`, `python`, etc., or `any`) |
| `domains` | string[] | PSS: Dewey domain codes from `schemas/pss-domains.json` (`310`, `620`, `910`, etc.) |
| `tools` | string[] | PSS: EXACT tool/library names extracted from skill (builds dynamic catalog) |
| `file_types` | string[] | PSS: EXACT file extensions handled (`pdf`, `xlsx`, `mp4`, `svg`, etc.) |
| `domain_gates` | object | PSS: Named keyword groups as hard prerequisite filters. Keys are gate names (`target_language`, `input_language`, `output_language`, `target_platform`, `target_framework`, `text_language`, `output_format`), values are arrays of lowercase keywords. ALL gates must have at least one keyword match in the user prompt or the skill is never suggested. Empty `{}` for generic skills. |

### Step 5: Pass 1 Index (Built Incrementally via Merge)

Pass 1 agents write temporary `.pss` files to `${PSS_TMPDIR}/pss-queue/` and immediately merge them into `~/.claude/cache/skill-index.json` via `pss_merge_queue.py`. No explicit "Save" step is needed -- the merge happens inline during Pass 1 processing.

The orchestrator should verify after all Pass 1 agents complete that `skill-index.json` exists and contains all discovered skills with `"pass": 1`.

```bash
mkdir -p ~/.claude/cache
```

**NOTE:** No staleness checks are performed. The index is a superset of all skills ever indexed.
At runtime, the agent filters suggestions against its known available skills (injected by Claude Code).
See `docs/PSS-ARCHITECTURE.md` for the full rationale.

---

### Step 5a: Validate Pass 1 Index (MANDATORY)

After ALL Pass 1 agents have completed, run the CPV plugin validator to ensure the index is structurally sound:

```bash
cd "${PLUGIN_ROOT}" && uv run --with pyyaml python scripts/validate_plugin.py . --verbose
```

**If validation FAILS (non-zero exit code):**
- The index has structural errors from Pass 1 agents
- Read the validator output to identify which skills have issues
- Re-run affected agents if the errors are recoverable
- If the errors are NOT recoverable: re-run ALL Pass 1 agents from scratch
- Do NOT proceed to Pass 2 until validation passes

**If validation PASSES (exit code 0):**
- Proceed to Step 5b

### Step 5b: Check Pass 1 Agent Tracking Files (MANDATORY)

The haiku agents write per-batch tracking files to `${PSS_TMPDIR}/pss-queue/batch-*-pass1-tracking.md`.
The orchestrator MUST check these files to verify no skills were skipped:

```bash
# List all Pass 1 tracking files
ls ${PSS_TMPDIR}/pss-queue/batch-*-pass1-tracking.md

# For each tracking file, check for PENDING or FAILED skills
grep -E "PENDING|FAILED" ${PSS_TMPDIR}/pss-queue/batch-*-pass1-tracking.md
```

**If ANY skill shows PENDING:**
- The agent forgot to process that skill (common with Haiku)
- Re-spawn a haiku agent for JUST the missed skills
- The re-run agent should process ONLY the PENDING skills, not the entire batch

**If ANY skill shows FAILED:**
- The agent tried but could not process that skill
- Check if the skill's SKILL.md file exists and is readable
- If the file exists, re-spawn an agent to retry (up to 2 retries)
- If the file does NOT exist, log a warning and skip it

**If ALL skills show DONE+YES:**
- Pass 1 is complete, proceed to Pass 2

---

## CRITICAL: Pass 1 → Pass 2 Workflow Transition

**ORCHESTRATOR INSTRUCTION (MANDATORY):**

When ALL Pass 1 batch agents have completed (all batches return results):

1. **Compile Pass 1 Index** - Merge all agent results into `~/.claude/cache/skill-index.json`
2. **Verify Pass 1 Success** - Confirm index contains all discovered skills with keywords and categories
3. **IMMEDIATELY PROCEED TO PASS 2** - Do NOT stop after Pass 1

**DO NOT WAIT FOR USER INPUT** between Pass 1 and Pass 2. The reindex command is a SINGLE operation that MUST complete both passes.

If the `--pass1-only` flag was specified, SKIP Pass 2 and stop after compiling the index.
If the `--pass2-only` flag was specified, SKIP Pass 1 and proceed directly to Pass 2.
Otherwise, ALWAYS execute Pass 2 immediately after Pass 1 completes.

---

## Pass 2: Co-Usage Correlation Workflow

**EXECUTE THIS SECTION IMMEDIATELY AFTER PASS 1 COMPLETES** (unless `--pass1-only` was specified).

### Step 6: Load CxC Category Matrix

Read the category-to-category co-usage probability matrix from:
`${CLAUDE_PLUGIN_ROOT}/schemas/pss-categories.json`

This provides heuristic guidance for candidate selection:
```json
{
  "co_usage_matrix": {
    "web-frontend": {
      "web-backend": 0.9,
      "testing": 0.8,
      "devops-cicd": 0.7
    }
  }
}
```

### Step 7: Spawn Pass 2 Agents (Parallel, Batched, Haiku)

**MODEL**: Use `model: haiku` for all Pass 2 agents.

**PROMPT TEMPLATE**: Read `${CLAUDE_PLUGIN_ROOT}/prompts/pass2-haiku.md` for the complete template.
Fill in the {variables} and pass to each haiku subagent.

**BATCHING (same as Pass 1):**
- Group skills into batches of 10
- Spawn up to 20 agents in parallel (all batches simultaneously, max 20 concurrent)
- Each agent processes ALL skills in its batch
- Wait for all batches to complete before proceeding to Step 8

**TRIPLE VERIFICATION**: The Pass 2 template includes 3 verification rounds where the agent
re-reads skill data and re-validates each co-usage link. This is mandatory for Haiku accuracy.

**HOW TO BUILD THE PASS 2 PROMPT:**

1. Read the template file: `${CLAUDE_PLUGIN_ROOT}/prompts/pass2-haiku.md`
2. Copy the content between `## TEMPLATE START` and `## TEMPLATE END`
3. Replace these variables:
   - `{batch_num}` → the batch number (e.g., 3)
   - `{start}` → first skill number in batch (e.g., 21)
   - `{end}` → last skill number in batch (e.g., 30)
   - `{list_of_skill_names_and_pss_paths}` → newline-separated list of skill names
   - `{skill_name}` → each skill name (template has per-skill sections)
   - `{keywords_as_phrase}` → skill's keywords joined as a phrase
   - `{binary_path}` → absolute path to the platform-specific Rust binary (see below)
4. Replace `${CLAUDE_PLUGIN_ROOT}` with the resolved absolute path to the plugin directory
5. Send the filled template to the haiku subagent

**RESOLVING {binary_path} (platform detection):**
```bash
# Detect platform and select the correct binary
ARCH=$(uname -m)
OS=$(uname -s)
if [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then
    BINARY="${PLUGIN_ROOT}/rust/skill-suggester/bin/pss-darwin-arm64"
elif [ "$OS" = "Darwin" ] && [ "$ARCH" = "x86_64" ]; then
    BINARY="${PLUGIN_ROOT}/rust/skill-suggester/bin/pss-darwin-x86_64"
elif [ "$OS" = "Linux" ] && [ "$ARCH" = "x86_64" ]; then
    BINARY="${PLUGIN_ROOT}/rust/skill-suggester/bin/pss-linux-x86_64"
elif [ "$OS" = "Linux" ] && [ "$ARCH" = "aarch64" ]; then
    BINARY="${PLUGIN_ROOT}/rust/skill-suggester/bin/pss-linux-arm64"
fi
```

**CRITICAL**: Same as Pass 1 - resolve `${CLAUDE_PLUGIN_ROOT}` to an absolute path BEFORE sending to subagents.

### Step 8: Verify Pass 2 Results in Global Index

Pass 2 agents merge their results directly into skill-index.json via pss_merge_queue.py during processing. No separate merge step is needed. The orchestrator should verify the final index has `pass: 2` and all skills have co_usage data.

**Final Index Format (Pass 2 complete):**
```json
{
  "version": "3.0",
  "generated": "2026-01-19T00:00:00Z",
  "generator": "ai-analyzed",
  "pass": 2,
  "skill_count": 216,
  "skills": {
    "devops-expert": {
      "source": "user",
      "path": "/path/to/SKILL.md",
      "type": "skill",
      "keywords": [
        "github actions workflow",
        "ci/cd pipeline configuration",
        "continuous integration setup",
        "set up github actions",
        "deployment automation"
      ],
      "intents": ["deploy", "configure", "automate"],
      "patterns": ["workflow.*failed", "github actions.*error"],
      "directories": [".github/workflows", "workflows"],
      "description": "CI/CD pipeline configuration and GitHub Actions workflows",
      "use_cases": ["Setting up GitHub Actions", "Troubleshooting pipelines"],
      "category": "devops-cicd",
      "platforms": ["universal"],
      "frameworks": [],
      "languages": ["any"],
      "domain_gates": {},
      "co_usage": {
        "usually_with": ["github-workflow", "container-security"],
        "precedes": ["deploy-to-production"],
        "follows": ["code-review"],
        "alternatives": ["gitlab-ci", "jenkins-pipeline"],
        "rationale": "DevOps skills form a CI/CD pipeline - code review triggers builds, which trigger deployments..."
      },
      "tier": "primary"
    }
  }
}
```

**NOTE:** Category is REQUIRED and must be one of the 16 predefined categories. Keywords are specific multi-word phrases.
```

### Step 8a: Validate Final Index (MANDATORY)

After ALL Pass 2 agents have completed, run the CPV plugin validator to ensure the final index is sound:

```bash
cd "${PLUGIN_ROOT}" && uv run --with pyyaml python scripts/validate_plugin.py . --verbose
```

**What this does:**
- Validates plugin structure, manifest, and all skill/agent/command definitions
- Checks for CRITICAL and MAJOR issues that would prevent the plugin from working

**If validation FAILS (non-zero exit code):**
- The reindex has FAILED - report to user
- If a backup exists (from Phase 0), manually restore it:
  ```bash
  BACKUP_DIR=$(cat ${PSS_TMPDIR}/pss-queue/backup-dir.txt)
  cp "$BACKUP_DIR/skill-index.json" ~/.claude/cache/skill-index.json
  ```
- Include the validator's error output in the report so the user can diagnose
- Clean up temporary `.pss` files: `rm -f ${PSS_TMPDIR}/pss-queue/*.pss`

**If validation PASSES (exit code 0):**
- Proceed to Step 8b

### Step 8b: Check Pass 2 Agent Tracking Files (MANDATORY)

Same procedure as Step 5b, but for Pass 2 tracking files:

```bash
# List all Pass 2 tracking files
ls ${PSS_TMPDIR}/pss-queue/batch-*-pass2-tracking.md

# For each tracking file, check for PENDING or FAILED skills
grep -E "PENDING|FAILED" ${PSS_TMPDIR}/pss-queue/batch-*-pass2-tracking.md
```

**If ANY skill shows PENDING:**
- Re-spawn a haiku agent for JUST the missed skills
- After the re-run completes, run the validator AGAIN (Step 8a)

**If ANY skill shows FAILED:**
- Check if the skill exists in the Pass 1 index
- If yes, re-spawn an agent to retry (up to 2 retries)
- After retries complete, run the validator AGAIN (Step 8a)

**If ALL skills show DONE+YES:**
- Proceed to the COMPLETION CHECKPOINT

### Step 8c: Final Cleanup

After validation passes, clean up temporary files:

```bash
# Remove tracking files (no longer needed)
rm -f ${PSS_TMPDIR}/pss-queue/batch-*-tracking.md

# Remove backup-dir pointer
rm -f ${PSS_TMPDIR}/pss-queue/backup-dir.txt

# Comprehensive .pss cleanup: skill dirs + ${PSS_TMPDIR}/pss-queue/ (replaces simple rm -f)
python3 "${PLUGIN_ROOT}/scripts/pss_cleanup.py" --all-projects --verbose
```

**NOTE:** The backup directory in `${PSS_TMPDIR}/pss-backup-*` is intentionally NOT deleted.
It persists until the system clears the temp directory or the user manually removes it.
This provides a safety net if issues are discovered later.

### Step 8d: Aggregate Domain Gates into Domain Registry (MANDATORY)

After validation passes, aggregate all domain gates from the index into a normalized domain registry.
This registry enables the suggester to perform two-phase matching:
1. Detect which domains are relevant to the user prompt (using example keywords from the registry)
2. Check each skill's domain gates against detected domains (boolean pass/fail)

```bash
python3 "${PLUGIN_ROOT}/scripts/pss_aggregate_domains.py" --verbose
```

**What this does:**
- Reads all `domain_gates` from every skill in `~/.claude/cache/skill-index.json`
- Normalizes similar gate names to canonical forms (e.g., `input_language`, `language_input`, `input_lang` → `input_language`)
- Aggregates all keywords found across skills for each canonical domain
- Detects which domains have the `generic` wildcard keyword
- Writes the registry to `~/.claude/cache/domain-registry.json`

**If the aggregation FAILS (exit code 1):**
- The domain registry was NOT written
- This does NOT invalidate the skill index — the index is still usable
- Report the error to the user but do NOT fail the entire reindex

**If the aggregation SUCCEEDS (exit code 0):**
- Proceed to the COMPLETION CHECKPOINT

### COMPLETION CHECKPOINT (MANDATORY)

**The reindex operation is ONLY COMPLETE when ALL of these are true:**

1. ✅ Pass 1 completed - All skills have keywords, categories, and intents
2. ✅ Pass 1 validated - CPV plugin validator returned exit code 0
3. ✅ Pass 1 tracking verified - All batch tracking files show DONE+YES for all skills
4. ✅ Pass 2 completed - All skills have co_usage relationships (usually_with, precedes, follows, alternatives)
5. ✅ Pass 2 validated - CPV plugin validator returned exit code 0
6. ✅ Pass 2 tracking verified - All batch tracking files show DONE+YES for all skills
7. ✅ Global index updated - `~/.claude/cache/skill-index.json` contains `"pass": 2`
8. ✅ Domain registry generated - `~/.claude/cache/domain-registry.json` exists with aggregated domains
9. ✅ Temporary files cleaned up - No .pss files or tracking files remain in ${PSS_TMPDIR}/pss-queue/

**FAILURE CONDITIONS:**
- If index shows `"pass": 1`, Pass 2 was NOT executed
- If only some skills have `co_usage`, Pass 2 agents only partially completed
- If validator fails with `--restore-on-failure`, the OLD index was restored and reindex FAILED
- If tracking files show PENDING skills, some agents forgot to process them

**REPORT TO USER:**
After successful completion, report:
```
PSS Reindex Complete
====================
Pass 1: {N} skills with keywords/categories (validated ✅)
Pass 2: {M} skills with co-usage relationships (validated ✅)
Domains: {D} canonical domains aggregated (registry ✅)
Index: ~/.claude/cache/skill-index.json (pass: 2)
Registry: ~/.claude/cache/domain-registry.json
Backup: {BACKUP_DIR} (preserved for safety)
```

After failed completion (validator restored backup), report:
```
PSS Reindex FAILED
==================
Validation errors detected - old index restored from backup.
Backup restored from: {BACKUP_DIR}
Errors: {validator error summary}
```

---

## Keyword Best Practices (Updated for PSS v3.0)

All keywords go into a single flat array. **PRIORITIZE multi-word phrases over single words.**

### Technology Names (ALWAYS use full names)
Tool and framework identifiers - use compound names:
- **GOOD**: `docker compose`, `kubernetes deployment`, `typescript strict mode`
- **GOOD**: `github actions workflow`, `gitlab ci/cd`, `jenkins pipeline`
- **AVOID**: `docker`, `k8s`, `ts` (too short/ambiguous)

### Action Phrases (NOT single verbs)
What the user wants to do - combine verb + context:
- **GOOD**: `deploy to production`, `run unit tests`, `review pull request`
- **GOOD**: `refactor legacy code`, `debug memory leak`, `migrate database`
- **AVOID**: `deploy`, `test`, `build` (too generic)

### Command Phrases (Natural language, 3+ words)
Full phrases users would type:
- **GOOD**: `fix failing build`, `set up ci/cd pipeline`, `configure test coverage`
- **GOOD**: `review this pull request`, `deploy to staging environment`
- **AVOID**: `fix build`, `run tests` (still too generic)

### Error Patterns (Specific messages)
Messages that indicate the skill is needed:
- **GOOD**: `workflow run failed`, `typescript type error`, `connection refused error`
- **GOOD**: `permission denied ssh`, `module not found node`
- **AVOID**: `failed`, `error`, `denied` (match everything)

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

**⚠️ PSS ALWAYS performs a FULL REINDEX from scratch. There are NO incremental updates.**

| Condition | Action |
|-----------|--------|
| **ANY invocation** | **Full reindex (delete + discover + analyze)** |

**REMOVED BEHAVIORS (these caused bugs):**
- ~~Staleness checks~~ - Removed (always reindex)
- ~~Single-skill reindex~~ - Removed (always full)
- ~~Skip if cache fresh~~ - Removed (always reindex)
- ~~Incremental updates~~ - NEVER supported

**WHY FULL REINDEX ONLY:**
1. Plugin versions change - old paths become invalid
2. Skills get renamed/moved - creates orphaned entries
3. Skills get deleted - phantom entries persist
4. Co-usage references stale skills - causes broken relationships
5. Partial updates create inconsistent state - impossible to debug

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
