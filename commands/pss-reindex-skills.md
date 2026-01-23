---
name: pss-reindex-skills
description: "Scan ALL skills and generate AI-analyzed keyword/phrase index for skill activation."
argument-hint: "[--force] [--skill SKILL_NAME] [--batch-size N]"
allowed-tools: ["Bash", "Read", "Write", "Glob", "Grep", "Task"]
---

# PSS Reindex Skills Command

Generate an **AI-analyzed** keyword and phrase index for ALL skills available to Claude Code. Unlike heuristic approaches, this command has the agent **read and understand each skill** to formulate optimal activation patterns.

This is the **MOST IMPORTANT** feature of Perfect Skill Suggester - AI-generated keywords ensure 88%+ accuracy in skill matching.

> **Architecture Reference:** See [docs/PSS-ARCHITECTURE.md](../docs/PSS-ARCHITECTURE.md) for the complete design rationale, including why no staleness checks are performed and how categories differ from keywords.

## Two-Pass Architecture

PSS uses a sophisticated two-pass agent swarm to generate both keywords AND co-usage relationships:

### Pass 1: Discovery + Keyword Analysis
The Python script `pss_discover_skills.py` scans ALL skill locations. Parallel agents then read each SKILL.md and formulate **rio-compatible keywords**:
- **Single keywords**: `docker`, `test`, `deploy`
- **Multi-word phrases**: `fix ci pipeline`, `review pull request`, `set up github actions`
- **Error patterns**: `build failed`, `type error`, `connection refused`

**Output**: `skill-index.json` with keywords + individual `.pss` files (Pass 1 format - keywords only)

### Pass 2: Co-Usage Correlation (AI Intelligence)
For EACH skill, a dedicated agent:
1. Reads the skill's incomplete `.pss` file (from Pass 1)
2. Calls `skill-suggester --incomplete-mode` to find CANDIDATE skills via keyword similarity + CxC matrix heuristics
3. Reads `.pss` files of ALL candidates to understand their use cases
4. **Uses its own AI intelligence** to determine which skills are logically co-used
5. Writes co-usage data to BOTH the global index AND the `.pss` file

**Why Pass 2 requires agents (not scripts)**:
- Only AI can understand that "docker-compose" and "microservices-architecture" are logically related
- Only AI can reason that "security-audit" typically FOLLOWS "code-review" but PRECEDES "deployment"
- Only AI can identify that "terraform" is an ALTERNATIVE to "pulumi" for infrastructure
- Scripts can only match keywords; agents understand semantic relationships

**Rio Compatibility**: Keywords are stored in a flat array and matched using `.includes()` against the lowercase user prompt. The `matchCount` is simply the number of matching keywords.

## Usage

```
/pss-reindex-skills [--force] [--skill SKILL_NAME] [--batch-size 20] [--pass1-only] [--pass2-only] [--all-projects]
```

| Flag | Description |
|------|-------------|
| `--force` | Force full reindex even if cache is fresh |
| `--skill NAME` | Reindex only the specified skill |
| `--batch-size N` | Skills per batch (default: 10) |
| `--pass1-only` | Run Pass 1 only (keywords, no co-usage) |
| `--pass2-only` | Run Pass 2 only (requires existing Pass 1 index) |
| `--all-projects` | **NEW:** Scan ALL projects registered in `~/.claude.json` |

## Comprehensive Skill Discovery

**By default**, the discovery script scans:
1. User-level skills: `~/.claude/skills/`
2. Current project skills: `.claude/skills/`
3. Plugin cache: `~/.claude/plugins/cache/*/`
4. Local plugins: `~/.claude/plugins/*/skills/`
5. Current project plugins: `.claude/plugins/*/skills/`

**With `--all-projects`**, it ALSO scans:
6. ALL projects registered in `~/.claude.json`:
   - `<project>/.claude/skills/`
   - `<project>/.claude/plugins/*/skills/`

This creates a **superset index** containing ALL skills across all your projects. At runtime, the agent filters suggestions against its context-injected available skills list (see `docs/PSS-ARCHITECTURE.md`).

**NOTE:** Deleted projects are automatically detected and skipped with a warning.

## Execution Protocol

### Step 1: Generate Skill Checklist

Run the discovery script with `--checklist` and `--all-projects` to generate a markdown checklist with batches:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pss_discover_skills.py --checklist --batch-size 10 --all-projects --generate-pss
```

The `--generate-pss` flag creates a `.pss` metadata file for each discovered skill in the same directory as its `SKILL.md`. This enables faster Pass 1/2 processing and incremental updates.

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

**Pass 1 Subagent Prompt Template (rio v2.0 compatible):**

```
You are analyzing skills for Batch {batch_num} (skills {start}-{end}).

For EACH skill in your batch:
1. Read the SKILL.md at the given path
2. Extract the description and use_cases VERBATIM from the frontmatter or content
3. **MANDATORY: Assign ONE category from the list below** (NEVER use null)
4. Generate rio-compatible keywords (8-15 keywords, multi-word phrases preferred)
5. Output JSON result AND write a .pss file

Skills to analyze:
{list_of_skill_paths}

## CATEGORY ASSIGNMENT (MANDATORY - NEVER null)

You MUST assign exactly ONE category to each skill. Categories represent the PRIMARY FIELD OF COMPETENCE.

**CATEGORY SELECTION RULES:**
1. Read the skill's description and use_cases carefully
2. Match against the category keywords below
3. Choose the category with the MOST keyword matches
4. If tied, choose the MORE SPECIFIC category (e.g., "mobile" over "web-frontend" for iOS skills)
5. **NEVER leave category as null** - always pick the best fit

**CATEGORIES WITH MATCHING KEYWORDS:**

| Category | Matches When Skill Contains... |
|----------|-------------------------------|
| `web-frontend` | react, vue, angular, svelte, css, html, javascript frontend, typescript frontend, ui components, ux design, responsive, tailwind, styled-components |
| `web-backend` | api, rest, graphql, server, endpoint, route, middleware, express, fastapi, django, flask, node backend |
| `mobile` | ios, android, swift, kotlin, react native, flutter, mobile app, xcode, app store, play store |
| `devops-cicd` | deploy, ci/cd, pipeline, github actions, docker, kubernetes, terraform, ansible, jenkins, continuous integration |
| `testing` | test, unit test, integration test, e2e, jest, pytest, coverage, tdd, mock, assertion, test-driven |
| `security` | security, vulnerability, audit, authentication, oauth, jwt, encryption, xss, injection, penetration |
| `data-ml` | data science, machine learning, ml model, training, dataset, pandas, numpy, tensorflow, pytorch, sklearn |
| `research` | research, paper, arxiv, academic, documentation generation, wiki, technical writing |
| `code-quality` | refactor, lint, format, clean code, dead code, simplify, code review, static analysis |
| `debugging` | debug, error handling, bug fix, troubleshoot, diagnose, crash, exception, profiling, logging |
| `infrastructure` | cloud, aws, gcp, azure, serverless, lambda, container orchestration, vm, infrastructure-as-code |
| `cli-tools` | cli, terminal, command line, shell, bash, zsh, scripting, shell script |
| `visualization` | chart, graph visualization, plot, svg, diagram, mermaid, d3.js, matplotlib, data viz |
| `ai-llm` | llm, gpt, claude, prompt engineering, agent, anthropic api, openai api, huggingface, transformers |
| `project-mgmt` | planning, task management, todo, project, milestone, roadmap, spec, requirement, agile |
| `plugin-dev` | plugin, extension, hook, skill development, command creation, agent creation, mcp server |

**VALIDATION:** Your output will be REJECTED if category is null or missing.

For each skill, output a JSON object in Pass 1 format:

{
  "name": "skill-name",
  "type": "skill",
  "source": "user|project|plugin",
  "path": "/full/path/to/SKILL.md",
  "description": "VERBATIM description from SKILL.md frontmatter",
  "use_cases": ["VERBATIM use case 1", "VERBATIM use case 2"],
  "category": "devops-cicd",
  "keywords": ["keyword1", "keyword2", "multi word phrase", ...],
  "intents": ["deploy", "build", "test"],
  "pass": 1
}

CRITICAL: description and use_cases MUST be copied VERBATIM from the skill.
DO NOT paraphrase, summarize, or rewrite them!

## KEYWORD SELECTION RULES (CRITICAL FOR ACCURACY)

**Generate 10-20 keywords/phrases per skill.** Quality over quantity - bad keywords cause false positives.

**MANDATORY RULES:**
1. ALL keywords must be LOWERCASE
2. **PREFER MULTI-WORD PHRASES** (3+ words) - they are MORE SPECIFIC
3. **AVOID SINGLE COMMON WORDS** like: "test", "code", "file", "run", "build", "fix", "error", "change", "update"
4. **AVOID AMBIGUOUS WORDS** that match multiple unrelated skills
5. Keywords must be UNIQUE TO THIS SKILL - don't use words that could match 10+ other skills

**KEYWORD SPECIFICITY HIERARCHY (prefer higher):**
| Specificity | Example | Why |
|-------------|---------|-----|
| **HIGH** | "set up github actions workflow" | Very specific phrase |
| **HIGH** | "github actions yaml" | Tool + format |
| **MEDIUM** | "ci/cd pipeline" | Domain-specific compound |
| **MEDIUM** | "github actions" | Tool name (2 words) |
| **LOW** | "ci" | Too short, matches many things |
| **AVOID** | "workflow" | Too generic, matches everything |

**GOOD KEYWORD EXAMPLES:**
- Tool names (2+ words): "github actions", "docker compose", "react native"
- Specific actions: "deploy to production", "run integration tests", "lint python files"
- Error messages: "workflow failed", "type check error", "build step failed"
- Command phrases: "set up continuous integration", "configure deployment pipeline"

**BAD KEYWORD EXAMPLES (NEVER USE):**
- Single letters: "ci", "cd", "ml", "ai" (use expanded forms)
- Generic verbs: "run", "build", "test", "fix" (too broad)
- Common nouns: "code", "file", "change", "error" (match everything)
- Ambiguous: "graph" (code graph vs. data visualization graph)

**DISAMBIGUATION RULE:** If a word has multiple meanings, use the SPECIFIC phrase:
- DON'T: "graph" → DO: "data visualization graph" OR "code dependency graph"
- DON'T: "test" → DO: "unit test", "integration test", "test coverage"
- DON'T: "deploy" → DO: "deploy to production", "kubernetes deployment"

INTENT EXTRACTION:
Identify 3-5 action verbs that represent what the user WANTS TO DO:
- deploy, build, test, review, debug, refactor, migrate, configure, etc.

**EXAMPLE OUTPUT (with proper category and specific keywords):**
```json
{
  "name": "devops-expert",
  "type": "skill",
  "source": "user",
  "path": "/Users/me/.claude/skills/devops-expert/SKILL.md",
  "description": "CI/CD pipeline configuration and GitHub Actions workflows",
  "use_cases": ["Setting up GitHub Actions for automated testing", "Troubleshooting failed pipeline runs"],
  "category": "devops-cicd",
  "keywords": [
    "github actions workflow",
    "github actions yaml",
    "ci/cd pipeline configuration",
    "continuous integration setup",
    "continuous deployment",
    "workflow yaml syntax",
    "github actions job",
    "workflow run failed",
    "pipeline step failed",
    "set up github actions",
    "configure github workflow",
    "deployment automation",
    "github actions cache",
    "workflow dispatch trigger"
  ],
  "intents": ["deploy", "configure", "automate", "troubleshoot"],
  "pass": 1
}
```

**NOTE:** Keywords are now specific multi-word phrases. Avoided: "ci", "cd", "pipeline", "deploy" (too generic).

ALSO WRITE A .pss FILE:
For each skill, write a .pss file at the same directory as SKILL.md:
- /path/to/skill/SKILL.md → /path/to/skill/.pss

The .pss file should contain the same JSON (prettified).

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

### Step 5: Save Pass 1 Index + .pss Files

Write the Pass 1 index to: `~/.claude/cache/skill-index.json`

Also generate a `.pss` file for EACH skill at the same location as its SKILL.md:
- `/path/to/skill/SKILL.md` → `/path/to/skill/.pss`

**Pass 1 .pss Format** (incomplete - no co-usage yet):
```json
{
  "name": "devops-expert",
  "type": "skill",
  "source": "user",
  "path": "/path/to/SKILL.md",
  "description": "CI/CD pipeline configuration and GitHub Actions workflows",
  "use_cases": [
    "Setting up GitHub Actions for CI/CD",
    "Troubleshooting pipeline failures",
    "Configuring deployment workflows"
  ],
  "category": "devops-cicd",
  "keywords": [
    "github actions workflow",
    "ci/cd pipeline configuration",
    "continuous integration setup",
    "workflow yaml syntax",
    "set up github actions",
    "configure github workflow",
    "deployment pipeline",
    "workflow run failed"
  ],
  "intents": ["deploy", "configure", "automate"],
  "pass": 1,
  "generated": "2026-01-19T00:00:00Z"
}
```

```bash
mkdir -p ~/.claude/cache
```

**NOTE:** No staleness checks are performed. The index is a superset of all skills ever indexed.
At runtime, the agent filters suggestions against its known available skills (injected by Claude Code).
See `docs/PSS-ARCHITECTURE.md` for the full rationale.

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

### Step 7: Spawn Pass 2 Agents (Parallel, Batched)

**BATCHING (same as Pass 1):**
- Group skills into batches of 10
- Spawn up to 20 agents in parallel (2 batches at a time)
- Each agent processes ALL skills in its batch
- Wait for all batches to complete before proceeding to Step 8

**For EACH batch, spawn an agent with this prompt:**

```
You are analyzing co-usage relationships for Batch {batch_num} (skills {start}-{end}).

For EACH skill in your batch:
{list_of_skill_names_and_pss_paths}
```

**Pass 2 Agent Prompt Template (include in batch agent prompt):**

```
You are analyzing co-usage relationships for Batch {batch_num}.

For EACH skill in your batch, follow these steps:

---
### Processing skill: {skill_name}

## STEP 1: Read Current State
Read the incomplete .pss file at: {pss_path}
Note the skill's:
- description (VERBATIM - do not paraphrase)
- use_cases (VERBATIM - do not paraphrase)
- keywords
- category

## STEP 2: Find Candidate Skills
Run the skill-suggester in incomplete-mode to find similar skills:

```bash
echo '{{"prompt": "{keywords_as_phrase}"}}' | {binary_path} --incomplete-mode
```

The skill-suggester returns skills matching by keyword similarity.

ALSO consider the CxC matrix heuristics:
- Skills in category "{category}" have high co-usage with: {high_probability_categories}
- Use the probability scores to prioritize candidates

## STEP 3: Read Candidate .pss Files
For each candidate skill returned, read its .pss file to understand:
- What the skill actually does (from description/use_cases)
- Its category and keywords
- Any existing co-usage data

Candidate .pss locations are at the same directory as their SKILL.md.

**ERROR HANDLING**: If a candidate's .pss file does not exist, SKIP that candidate.
The index may contain stale entries for deleted skills. Do not fail - just exclude
non-existent skills from your co-usage analysis.

## STEP 4: Determine Co-Usage Relationships (AI INTELLIGENCE)
Using your understanding of software development workflows, determine:

1. **usually_with**: Skills typically used in the SAME session/task
   - Example: "docker" usually_with "docker-compose", "container-security"

2. **precedes**: Skills typically used BEFORE this skill
   - Example: "code-review" precedes "merge-branch"

3. **follows**: Skills typically used AFTER this skill
   - Example: "write-tests" follows "implement-feature"

4. **alternatives**: Skills that solve the SAME problem differently
   - Example: "terraform" alternative to "pulumi"

5. **rationale**: A brief explanation of why these relationships exist

## STEP 5: Write Updated .pss File
Update the .pss file at {pss_path} with co-usage data:

```json
{{
  "name": "{skill_name}",
  "type": "{type}",
  "source": "{source}",
  "path": "{skill_path}",
  "description": "{VERBATIM_description}",
  "use_cases": {VERBATIM_use_cases},
  "category": "{category}",
  "keywords": {keywords},
  "intents": {intents},
  "patterns": {patterns},
  "directories": {directories},
  "co_usage": {{
    "usually_with": ["skill-a", "skill-b"],
    "precedes": ["skill-x"],
    "follows": ["skill-y", "skill-z"],
    "alternatives": ["alt-skill"],
    "rationale": "Web frontend development typically requires backend APIs (web-backend), testing, and deployment pipelines."
  }},
  "tier": "primary|secondary|specialized",
  "pass": 2,
  "generated": "{timestamp}"
}}
```

## STEP 6: Return Batch Summary
After processing ALL skills in your batch, return a minimal report (1-2 lines max):
```
[DONE] Pass 2 Batch {batch_num} - {skills_processed}/{total_skills} skills with co-usage data
```

If any skills failed, report:
```
[PARTIAL] Pass 2 Batch {batch_num} - {success_count} OK, {fail_count} failed: {failed_skill_names}
```

CRITICAL RULES:
- description and use_cases MUST be VERBATIM from the SKILL.md - NEVER paraphrase
- Only include skills in co_usage that you ACTUALLY verified exist
- Do not guess - if uncertain, omit that relationship
- Write to the .pss file, NOT to the global index (orchestrator merges later)
```

### Step 8: Merge Pass 2 Results into Global Index

After all Pass 2 agents complete, the orchestrator:
1. Reads each updated `.pss` file
2. Merges co_usage data into the master `skill-index.json`
3. Validates no broken references (all co-used skills exist)

**Final Index Format (Pass 2 complete):**
```json
{
  "version": "3.0",
  "generated": "2026-01-19T00:00:00Z",
  "method": "ai-analyzed",
  "pass": 2,
  "skills_count": 216,
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

### COMPLETION CHECKPOINT (MANDATORY)

**The reindex operation is ONLY COMPLETE when:**

1. ✅ Pass 1 completed - All skills have keywords, categories, and intents
2. ✅ Pass 2 completed - All skills have co_usage relationships (usually_with, precedes, follows, alternatives)
3. ✅ Global index updated - `~/.claude/cache/skill-index.json` contains `"pass": 2`
4. ✅ All .pss files updated - Each skill's .pss file contains co_usage data

**FAILURE CONDITIONS:**
- If index shows `"pass": 1`, Pass 2 was NOT executed
- If skills have empty `co_usage`, Pass 2 agents failed or were not spawned
- If only some skills have `co_usage`, Pass 2 agents only partially completed

**REPORT TO USER:**
After completion, report:
```
PSS Reindex Complete
====================
Pass 1: {N} skills with keywords/categories
Pass 2: {M} skills with co-usage relationships
Index: ~/.claude/cache/skill-index.json (pass: 2)
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
