---
name: pss-reindex-skills
description: "Scan ALL skills and generate AI-analyzed keyword/phrase index for skill activation."
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

Generate an **AI-analyzed** keyword and phrase index for ALL skills available to Claude Code. Unlike heuristic approaches, this command has the agent **read and understand each skill** to formulate optimal activation patterns.

This is the **MOST IMPORTANT** feature of Perfect Skill Suggester - AI-generated keywords ensure 88%+ accuracy in skill matching.

> **Architecture Reference:** See [docs/PSS-ARCHITECTURE.md](../docs/PSS-ARCHITECTURE.md) for the complete design rationale.

## Two-Pass Architecture

PSS uses a sophisticated two-pass agent swarm to generate both keywords AND co-usage relationships:

### Pass 1: Discovery + Keyword Analysis
The Python script `pss_discover_skills.py` scans ALL skill locations. Parallel agents then read each SKILL.md and formulate **rio-compatible keywords**:
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

**With `--all-projects`**, it ALSO scans:
6. ALL projects registered in `~/.claude.json`:
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
1. [Phase 0] Create backup directory in /tmp
2. [Phase 0] Backup and remove skill-index.json
3. [Phase 0] Backup and remove skill-checklist.md
4. [Phase 0] VERIFY clean slate - no index files remain
5. [Phase 1] Run discovery script to generate skill checklist
6. [Phase 1] Spawn Pass 1 batch agents for keyword analysis
7. [Phase 1] Compile Pass 1 results into skill-index.json
8. [Phase 2] Spawn Pass 2 batch agents for co-usage analysis
9. [Phase 2] Verify Pass 2 results in final index
10. [Verify] Confirm index has pass:2 and all skills have co_usage
11. [Report] Report final statistics to user
```

**CRITICAL RULES:**
- Tasks 1-4 (Phase 0) MUST ALL be marked `completed` BEFORE starting task 5
- If task 4 verification FAILS, do NOT proceed - mark remaining tasks as blocked
- Update task status to `in_progress` when starting, `completed` when done
- If ANY Phase 0 task fails, STOP and report error to user

**Example TaskCreate call for first task:**
```
TaskCreate({
  subject: "[Phase 0] Create backup directory in /tmp",
  description: "Create timestamped backup dir: /tmp/pss-backup-YYYYMMDD_HHMMSS",
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
# Step 0.0: Create timestamped backup folder in /tmp
BACKUP_DIR="/tmp/pss-backup-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
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

**CHECKLIST (ALL MUST BE CHECKED BEFORE PROCEEDING):**
- [ ] Backup directory created in /tmp
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

**The backup in /tmp ensures you can debug issues if needed, but the old data is GONE from the active paths.**

---

### Step 1: Generate Skill Checklist

Run the discovery script with `--checklist` and `--all-projects` to generate a markdown checklist with batches:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pss_discover_skills.py --checklist --batch-size 10 --all-projects
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

**Pass 1 Subagent Prompt Template (rio v2.0 compatible):**

```
You are analyzing skills for Batch {batch_num} (skills {start}-{end}).

For EACH skill in your batch:
1. Read the SKILL.md at the given path THOROUGHLY - understand what it does
2. Extract the description and use_cases VERBATIM from the frontmatter or content
3. **MANDATORY: Assign ONE category from the list below** (NEVER use null)
4. **MANDATORY: Determine platform/framework/language specificity** (read carefully!)
5. **MANDATORY: Determine domain/tools/file_types** (for non-programming skills)
6. Generate rio-compatible keywords (8-15 keywords, multi-word phrases preferred)
7. Output JSON result AND write a .pss file

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
  "platforms": ["ios", "macos"],
  "frameworks": ["swiftui"],
  "languages": ["swift"],
  "domains": ["620"],
  "tools": ["ffmpeg", "ffprobe"],
  "file_types": ["mp4", "mov"],
  "keywords": ["keyword1", "keyword2", "multi word phrase", ...],
  "intents": ["deploy", "build", "test"],
  "pass": 1
}

**FIELD NOTES:**
- `domains`: Use Dewey codes from `schemas/pss-domains.json` (e.g., "620" for Video Production)
- `tools`: Extract EXACT tool/framework/library names mentioned in the skill (build the catalog!)
- `file_types`: Extract EXACT file extensions the skill handles

CRITICAL: description and use_cases MUST be copied VERBATIM from the skill.
DO NOT paraphrase, summarize, or rewrite them!

## PLATFORM/FRAMEWORK/LANGUAGE METADATA (MANDATORY)

**Read the SKILL.md carefully to determine if this skill is:**
1. **Platform-specific**: Does it target iOS, Android, macOS, Windows, Linux, or web?
2. **Framework-specific**: Does it target a specific framework like SwiftUI, React, Django, Rails?
3. **Language-specific**: Does it target a specific language like Swift, Rust, Python, TypeScript?

**RULES FOR METADATA EXTRACTION:**

| Field | Values | When to Use |
|-------|--------|-------------|
| `platforms` | `["ios"]`, `["android"]`, `["macos"]`, `["windows"]`, `["linux"]`, `["web"]`, or `["universal"]` | Based on what the skill explicitly targets |
| `frameworks` | `["swiftui"]`, `["uikit"]`, `["react"]`, `["vue"]`, `["django"]`, `["rails"]`, or `[]` | Based on frameworks mentioned in the skill |
| `languages` | `["swift"]`, `["rust"]`, `["python"]`, `["typescript"]`, or `["any"]` | Based on languages the skill is for |

**CRITICAL RULES:**
1. **READ THE SKILL THOROUGHLY** - Don't guess, read what the skill actually covers
2. **Be specific** - If a skill mentions "SwiftUI" and "iOS", set `platforms: ["ios"]`, `frameworks: ["swiftui"]`, `languages: ["swift"]`
3. **Use "universal" for platforms** only if the skill explicitly works across ALL platforms
4. **Use "any" for languages** only if the skill is truly language-agnostic (e.g., git workflow)
5. **Leave empty `[]`** if the field doesn't apply (e.g., no specific framework)

**EXAMPLES:**

iOS debugging skill:
```json
{
  "platforms": ["ios"],
  "frameworks": ["swiftui", "uikit"],
  "languages": ["swift"]
}
```

Generic git workflow skill:
```json
{
  "platforms": ["universal"],
  "frameworks": [],
  "languages": ["any"]
}
```

React web development skill:
```json
{
  "platforms": ["web"],
  "frameworks": ["react"],
  "languages": ["typescript", "javascript"]
}
```

Rust systems programming skill:
```json
{
  "platforms": ["universal"],
  "frameworks": [],
  "languages": ["rust"]
}
```

**⛔ NEVER leave these fields empty for platform-specific skills!** This metadata is CRITICAL for filtering - without it, iOS skills will be suggested for Rust projects.

## DOMAIN CLASSIFICATION (DEWEY-LIKE SYSTEM)

PSS uses a **Dewey-like hierarchical classification** for domains. Each skill is assigned one or more domain codes based on its content.

**The domain schema is in `schemas/pss-domains.json`** - consult this file for the full classification.

### Main Categories (X00)

| Code | Category | Description |
|------|----------|-------------|
| **000** | General & Meta | Cross-cutting skills (docs, planning, workflow, git) |
| **100** | Software Development | Programming, frontend, backend, mobile, testing |
| **200** | Data & Analytics | Data science, ML, visualization, databases |
| **300** | DevOps & Infrastructure | CI/CD, cloud, containers, monitoring |
| **400** | Security & Compliance | Security audits, auth, encryption, compliance |
| **500** | Content & Communication | Writing, presentations, social media |
| **600** | Media & Graphics | Design, video, audio, animation, 3D |
| **700** | Business & Professional | Project mgmt, finance, legal, marketing |
| **800** | Science & Research | Academic, bioinformatics, chemistry, physics |
| **900** | Life & Personal | Health, travel, education, DIY, events |

### Subcategories (X10-X90)

Each main category has subcategories for finer classification:

| Code | Subcategory |
|------|-------------|
| **110** | Frontend Development (Web UI) |
| **120** | Backend Development (APIs, Servers) |
| **130** | Mobile Development (iOS, Android) |
| **150** | Testing & QA |
| **220** | Machine Learning & AI Models |
| **310** | CI/CD & Automation |
| **330** | Containers & Orchestration |
| **410** | Security Auditing |
| **510** | Technical Writing |
| **620** | Video Production |
| **630** | Audio Production |
| **910** | Health & Fitness |
| **920** | Travel & Transportation |

**HOW TO ASSIGN DOMAIN CODES:**
1. Read the SKILL.md thoroughly
2. Identify the PRIMARY domain from the 000-900 categories
3. If applicable, use the more specific subcategory (e.g., "620" for video instead of "600")
4. A skill can have MULTIPLE domain codes if it spans domains

---

## TOOL/FRAMEWORK/ARTIFACT EXTRACTION (EXACT NAMES ONLY)

**⛔ CRITICAL: Extract EXACT names - do NOT use generic categories!**

The `tools` field is a **dynamic catalog** built from all skills. The hook matches these exact names against user prompts. Therefore:

1. **Extract the EXACT tool/framework/library/service names** mentioned in the SKILL.md
2. **Use the canonical name** (lowercase, as written in docs)
3. **Include version-independent names** (e.g., "ffmpeg" not "ffmpeg 6.0")
4. **Include common aliases** if the skill mentions them

### What to Extract

| Type | Examples | How to Recognize |
|------|----------|------------------|
| **CLI Tools** | `ffmpeg`, `pandoc`, `imagemagick`, `tesseract`, `sox` | Command-line utilities mentioned for processing |
| **Libraries** | `openpyxl`, `pandas`, `reportlab`, `pillow` | Import statements, pip/npm packages |
| **Frameworks** | `django`, `react`, `flutter`, `swiftui` | Architecture patterns, project structure |
| **Services** | `aws-s3`, `github-actions`, `openai-api` | External APIs, cloud services |
| **Applications** | `blender`, `inkscape`, `gimp`, `audacity` | Desktop applications used |
| **AI Models** | `stable-diffusion`, `whisper`, `llama` | ML models referenced |

### Extraction Rules

1. **Be exhaustive** - Extract ALL tools/frameworks mentioned in the skill
2. **Use lowercase** - `FFmpeg` → `ffmpeg`, `ImageMagick` → `imagemagick`
3. **Keep hyphens** - `stable-diffusion`, `yt-dlp`, `react-native`
4. **No versions** - `python` not `python3.12`, `node` not `node18`
5. **Include wrappers** - If skill uses `comfyui` for `stable-diffusion`, include BOTH

### Examples

**Video processing skill mentions:** "use FFmpeg to transcode, HandBrake for quick conversions, and yt-dlp for downloading"
```json
{
  "tools": ["ffmpeg", "handbrake", "yt-dlp"]
}
```

**Document skill mentions:** "converts using Pandoc, generates PDFs with wkhtmltopdf, handles DOCX with python-docx"
```json
{
  "tools": ["pandoc", "wkhtmltopdf", "python-docx"]
}
```

**ML skill mentions:** "runs Stable Diffusion via ComfyUI or Automatic1111, uses Whisper for transcription"
```json
{
  "tools": ["stable-diffusion", "comfyui", "automatic1111", "whisper"]
}
```

---

## FILE TYPES (EXACT EXTENSIONS)

Extract the **exact file extensions** the skill handles:

| Category | Extensions |
|----------|------------|
| Documents | `pdf`, `docx`, `doc`, `xlsx`, `xls`, `pptx`, `odt` |
| Text | `md`, `txt`, `rst`, `html`, `xml`, `json`, `yaml`, `csv` |
| Images | `png`, `jpg`, `jpeg`, `gif`, `svg`, `webp`, `ico`, `tiff` |
| Video | `mp4`, `mov`, `avi`, `mkv`, `webm`, `m4v` |
| Audio | `mp3`, `wav`, `flac`, `aac`, `ogg`, `m4a` |
| Archives | `zip`, `tar`, `gz`, `7z`, `rar` |
| Code | `py`, `js`, `ts`, `rs`, `go`, `swift`, `kt` |
| E-books | `epub`, `mobi`, `azw3` |

---

## COMPLETE EXAMPLES

**FFmpeg video processing skill:**
```json
{
  "platforms": ["universal"],
  "frameworks": [],
  "languages": ["any"],
  "domains": ["620"],
  "tools": ["ffmpeg", "ffprobe"],
  "file_types": ["mp4", "mov", "avi", "mkv", "webm", "gif"]
}
```

**PDF generation with Pandoc:**
```json
{
  "platforms": ["universal"],
  "frameworks": [],
  "languages": ["any"],
  "domains": ["510"],
  "tools": ["pandoc", "wkhtmltopdf", "weasyprint"],
  "file_types": ["pdf", "html", "docx", "md", "epub"]
}
```

**React frontend skill:**
```json
{
  "platforms": ["web"],
  "frameworks": ["react", "next.js"],
  "languages": ["typescript", "javascript"],
  "domains": ["110"],
  "tools": ["vite", "webpack", "eslint", "prettier"],
  "file_types": ["tsx", "jsx", "css", "json"]
}
```

**Stable Diffusion image generation:**
```json
{
  "platforms": ["universal"],
  "frameworks": [],
  "languages": ["python"],
  "domains": ["220", "610"],
  "tools": ["stable-diffusion", "comfyui", "automatic1111", "sdxl"],
  "file_types": ["png", "jpg", "webp", "safetensors"]
}
```

**Security audit skill:**
```json
{
  "platforms": ["universal"],
  "frameworks": [],
  "languages": ["any"],
  "domains": ["410"],
  "tools": ["nmap", "burpsuite", "sqlmap", "nikto"],
  "file_types": []
}
```

**Excel automation with Python:**
```json
{
  "platforms": ["universal"],
  "frameworks": [],
  "languages": ["python"],
  "domains": ["210", "250"],
  "tools": ["openpyxl", "pandas", "xlsxwriter"],
  "file_types": ["xlsx", "csv", "xls"]
}
```

**⛔ CRITICAL:** The `tools` field builds a **dynamic catalog** used by the hook for matching. Extract EVERY tool/framework/library name from the skill - missing entries means missing matches!

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

**⛔ PLATFORM-SPECIFIC SKILLS RULE:**
For skills targeting a SPECIFIC PLATFORM (iOS, Android, macOS, Windows, Linux), ALL keywords MUST include the platform name:
- iOS skill: "ios memory leak", "swiftui debugging ios", "xcode build failed ios"
- Android skill: "android gradle build", "kotlin coroutine android"
- macOS skill: "macos appkit menu", "macos notarization"

**WHY?** Generic keywords like "debug memory leak" would match iOS skills for a Python debugging query.
The platform name MUST be in every keyword to prevent cross-platform false positives.

**PLATFORM PREFIXING EXAMPLES:**
| Platform | WRONG (too generic) | CORRECT (platform-specific) |
|----------|---------------------|----------------------------|
| iOS | "debug memory leak" | "ios memory leak debugging" |
| iOS | "navigation stack" | "swiftui navigation stack ios" |
| Android | "gradle build" | "android gradle build error" |
| macOS | "menu bar" | "macos menu bar appkit" |

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

ALSO WRITE A TEMPORARY .pss FILE AND MERGE IT:
For each skill, write a .pss file to the temp queue directory:
- /tmp/pss-queue/<skill-name>.pss

The .pss file should contain the same JSON (prettified).

After writing EACH .pss file, immediately merge it into the index by running:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pss_merge_queue.py" "/tmp/pss-queue/<skill-name>.pss" --pass 1
```

The merge script will atomically update skill-index.json and delete the temp .pss file.
Report the merge result (1 line per skill).

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
      "description": "CI/CD pipeline configuration and GitHub Actions workflows",
      "platforms": ["universal"],
      "frameworks": [],
      "languages": ["any"]
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

### Step 5: Pass 1 Index (Built Incrementally via Merge)

Pass 1 agents write temporary `.pss` files to `/tmp/pss-queue/` and immediately merge them into `~/.claude/cache/skill-index.json` via `pss_merge_queue.py`. No explicit "Save" step is needed -- the merge happens inline during Pass 1 processing.

The orchestrator should verify after all Pass 1 agents complete that `skill-index.json` exists and contains all discovered skills with `"pass": 1`.

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

## STEP 1: Read Current State from Index
Read the skill's data from the skill-index.json. You can do this with:

```bash
python3 -c "import json; idx=json.load(open('$HOME/.claude/cache/skill-index.json')); s=idx['skills'].get('{skill_name}', {}); print(json.dumps(s, indent=2))"
```

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

## STEP 3: Read Candidate Data from Index
For each candidate skill returned, read its data from skill-index.json to understand:
- What the skill actually does (from description/use_cases)
- Its category and keywords
- Any existing co-usage data

Use the same python one-liner from Step 1 to read each candidate's data.

**ERROR HANDLING**: If a candidate doesn't exist in the index, SKIP it.

## STEP 4: Determine Co-Usage Relationships (AI INTELLIGENCE)

> **⛔ CRITICAL: CO-USAGE VALIDATION RULES**
>
> Bad co-usage associations cause TERRIBLE user experience - irrelevant skills flood the context.
> You MUST follow these strict validation rules:

### CO-USAGE VALIDATION RULES (MANDATORY)

**RULE 1: SAME-DOMAIN PREFERENCE**
Co-usage should PRIMARILY link skills in the SAME or CLOSELY RELATED categories:
- ✅ mobile → mobile (iOS skill with another iOS skill)
- ✅ devops-cicd → testing (deployment needs tests)
- ✅ web-frontend → web-backend (frontend calls APIs)
- ❌ mobile → plugin-dev (completely unrelated domains!)
- ❌ debugging → project-mgmt (no workflow connection!)

**RULE 2: WORKFLOW JUSTIFICATION REQUIRED**
For EVERY co-usage link, you MUST be able to answer: "In what realistic workflow would a developer use BOTH skills in the same session?"
- ✅ "code-review" precedes "merge-branch" - PR workflow
- ✅ "docker" usually_with "docker-compose" - container workflow
- ❌ "swiftui-debugging" usually_with "plugin-structure" - NO logical workflow!

**RULE 3: CATEGORY BOUNDARY CROSSING**
Cross-category co-usage is ONLY valid when:
1. There's a DIRECT workflow dependency (testing → deployment)
2. One skill OUTPUTS what the other skill INPUTS
3. They solve ADJACENT steps in the same development pipeline

**RULE 4: QUANTITY LIMITS**
- `usually_with`: MAX 3-5 skills (only the STRONGEST associations)
- `precedes`: MAX 2-3 skills
- `follows`: MAX 2-3 skills
- `alternatives`: MAX 2-3 skills
- If uncertain, use FEWER associations, not more!

**RULE 5: NO KEYWORD-BASED ASSOCIATIONS**
Do NOT create co-usage just because skills share keywords like:
- "debug", "test", "deploy", "fix", "build" - too generic
- "github", "code", "file" - appear in many skills
- Platform names like "ios", "swift" - need workflow justification

### Co-Usage Relationship Types

Using your understanding of software development workflows, determine:

1. **usually_with**: Skills typically used in the SAME session/task
   - Example: "docker" usually_with "docker-compose", "container-security"
   - VALIDATION: Would a developer ACTUALLY use both in one coding session?

2. **precedes**: Skills typically used BEFORE this skill
   - Example: "code-review" precedes "merge-branch"
   - VALIDATION: Is this skill a logical PREREQUISITE?

3. **follows**: Skills typically used AFTER this skill
   - Example: "write-tests" follows "implement-feature"
   - VALIDATION: Is this skill a logical NEXT STEP?

4. **alternatives**: Skills that solve the SAME problem differently
   - Example: "terraform" alternative to "pulumi"
   - VALIDATION: Are they genuinely INTERCHANGEABLE solutions?

5. **rationale**: A brief explanation of WHY these relationships exist
   - MUST include specific workflow justification
   - If you can't write a clear rationale, DO NOT include the association!

## STEP 5: Write Temporary .pss File and Merge
Write the co-usage data to a temporary .pss file and merge it into the index:

1. Write to: `/tmp/pss-queue/{skill_name}.pss`
2. The .pss file should contain:
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

3. Immediately merge into the index:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pss_merge_queue.py" "/tmp/pss-queue/{skill_name}.pss" --pass 2
```

The merge script handles atomic index updates and deletes the temp file.

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
- Write to a temp .pss file in /tmp/pss-queue/ and merge via pss_merge_queue.py

**⛔ CO-USAGE ANTI-PATTERNS (NEVER DO):**
- NEVER link skills just because they share intents like "debug", "fix", "troubleshoot"
- NEVER link skills from completely different tech stacks (e.g., iOS + Python)
- NEVER link platform-specific skills with generic tools (e.g., SwiftUI + plugin-dev)
- NEVER create more than 5 usually_with relationships - pick only the STRONGEST
- NEVER include a skill in co_usage if you cannot explain the workflow connection

**VALIDATION CHECKLIST (for each co_usage entry):**
□ Can I describe a specific workflow where both skills are needed together?
□ Are the skills in the same or adjacent categories?
□ Is this a relationship most developers would recognize?
□ Would suggesting skill B when skill A is active actually HELP the user?
If ANY answer is NO, DO NOT include that co_usage relationship!
```

### Step 8: Verify Pass 2 Results in Global Index

Pass 2 agents merge their results directly into skill-index.json via pss_merge_queue.py during processing. No separate merge step is needed. The orchestrator should verify the final index has `pass: 2` and all skills have co_usage data.

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
      "platforms": ["universal"],
      "frameworks": [],
      "languages": ["any"],
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
4. ✅ No .pss files remain in /tmp/pss-queue/

**FAILURE CONDITIONS:**
- If index shows `"pass": 1`, Pass 2 was NOT executed
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
