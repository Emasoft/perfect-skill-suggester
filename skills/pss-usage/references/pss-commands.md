# PSS Commands Reference

This document provides detailed information about Perfect Skill Suggester (PSS) commands, their usage, output interpretation, and troubleshooting.

## Contents

- 1.0 Understanding PSS command structure and invocation
  - 1.1 Command naming conventions
  - 1.2 Command invocation from Claude Code chat
- 2.0 Using /pss-status to check PSS configuration and index health
  - 2.1 Basic /pss-status usage without arguments
  - 2.2 Understanding /pss-status output: index statistics
  - 2.3 Understanding /pss-status output: skill counts and categories
  - 2.4 Interpreting /pss-status warnings and errors
- 3.0 Using /pss-reindex-skills to rebuild the skill index
  - 3.1 When to reindex: detecting stale skill data
  - 3.2 Running /pss-reindex-skills workflow step-by-step
  - 3.3 Understanding reindex progress and completion messages
  - 3.4 Verifying successful reindexing with /pss-status
- 4.0 Interpreting PSS skill suggestion output
  - 4.1 Understanding confidence levels: HIGH, MEDIUM, LOW
  - 4.2 Understanding evidence types: intent, keyword, co_usage
  - 4.3 Reading the skill suggestion table format
  - 4.4 Deciding when to activate suggested skills
- 5.0 Troubleshooting common PSS issues
  - 5.1 PSS commands not found or not responding
  - 5.2 Empty or missing skill suggestions
  - 5.3 Index file errors or corruption
  - 5.4 Reindexing failures and recovery

---

## 1.0 Understanding PSS command structure and invocation

### 1.1 Command naming conventions

All PSS commands follow the prefix convention `pss-` to avoid naming collisions with other plugins.

**Available PSS commands:**
- `/pss-status` - Check PSS configuration and index health
- `/pss-reindex-skills` - Rebuild the skill index from scratch

**Why the prefix matters:**
The `pss-` prefix ensures PSS commands do not conflict with:
- Other plugin commands
- Built-in Claude Code commands
- Future commands from other plugins

### 1.2 Command invocation from Claude Code chat

PSS commands are invoked by typing them in the Claude Code chat interface, exactly as shown with the leading slash:

```
/pss-status
```

**What happens when you invoke a command:**
1. Claude Code recognizes the `/` prefix as a command invocation
2. PSS plugin intercepts commands starting with `pss-`
3. The command executes and returns structured output
4. Claude receives and interprets the output

**Important:** Commands must be typed exactly as shown, including the slash and prefix. Variations like `pss status` or `/status` will not work.

---

## 2.0 Using /pss-status to check PSS configuration and index health

### 2.1 Basic /pss-status usage without arguments

The `/pss-status` command requires no arguments. Simply type it in the chat:

```
/pss-status
```

**What this command does:**
- Checks if the skill index file exists
- Reports the number of skills in the index
- Shows breakdown by category
- Reports the list of available skills directories
- Identifies any configuration issues

### 2.2 Understanding /pss-status output: index statistics

**Example output:**

```
Perfect Skill Suggester Status
==============================

Index File: /Users/name/.claude/skill_index.json
Index Status: ✓ Exists
Total Skills Indexed: 42
Last Modified: 2026-01-23 14:30:00

Skills by Category:
  - debugging: 5
  - testing: 8
  - deployment: 3
  - ...
```

**Key metrics explained:**

| Metric | Meaning | What to look for |
|--------|---------|------------------|
| **Index Status** | Whether index file exists | ✓ Exists (good) or ✗ Missing (bad) |
| **Total Skills Indexed** | Number of skills PSS knows about | Should match your skill count |
| **Last Modified** | When index was last updated | Should be recent if you added skills |
| **Skills by Category** | Distribution across 16 categories | Even distribution indicates good coverage |

### 2.3 Understanding /pss-status output: skill counts and categories

PSS organizes skills into 16 predefined categories:

1. **debugging** - Error analysis, stack trace interpretation
2. **testing** - Unit tests, integration tests, test automation
3. **deployment** - CI/CD, containerization, infrastructure
4. **refactoring** - Code cleanup, pattern application
5. **documentation** - README generation, API docs
6. **performance** - Optimization, profiling, benchmarking
7. **security** - Vulnerability scanning, auth, encryption
8. **database** - SQL, migrations, query optimization
9. **api** - REST, GraphQL, API design
10. **frontend** - UI/UX, frameworks, styling
11. **backend** - Server logic, middleware, services
12. **devops** - Monitoring, logging, alerting
13. **data-processing** - ETL, transformations, pipelines
14. **ml-ai** - Machine learning, model training
15. **collaboration** - Git workflows, code review
16. **other** - Miscellaneous skills

**What the category breakdown tells you:**

If most skills are in "other", the skill metadata may need better categorization.

### 2.4 Interpreting /pss-status warnings and errors

**Common warnings:**

| Warning | Meaning | Action Required |
|---------|---------|-----------------|
| `Index file missing` | PSS has never been indexed | Run `/pss-reindex-skills` |
| `Index file corrupted` | JSON syntax error in index | Run `/pss-reindex-skills` to rebuild |
| `No skills found` | Skills directories are empty | Check that skills are installed |
| `Index older than skills` | Skills modified since last index | Run `/pss-reindex-skills` |

**Common errors:**

| Error | Meaning | Action Required |
|-------|---------|-----------------|
| `Permission denied` | Cannot read/write index file | Check file permissions |
| `Invalid JSON` | Index file has syntax errors | Delete and reindex |
| `Missing skill directories` | PSS cannot find skills/ folders | Check plugin installation |

---

## 3.0 Using /pss-reindex-skills to rebuild the skill index

### 3.1 When to reindex: detecting stale skill data

**You should reindex when:**

1. **New skills added** - You installed new skills from marketplace
2. **Skills modified** - You edited skill metadata (name, description, categories)
3. **First time setup** - PSS was just installed
4. **Corrupted index** - `/pss-status` shows errors
5. **Missing suggestions** - PSS should suggest a skill but does not

**How to detect stale data:**

Check the "Last Modified" timestamp in `/pss-status` output. If it is older than your last skill change, reindex.

### 3.2 Running /pss-reindex-skills workflow step-by-step

**Step 1: Invoke the command**

Type in chat:
```
/pss-reindex-skills
```

**Step 2: Wait for completion**

The command will:
1. Scan all skills directories (user, project, local scopes)
2. Read SKILL.md files and frontmatter
3. Extract metadata (name, description, categories, keywords)
4. Use AI to analyze co-usage relationships
5. Write updated index to `~/.claude/skill_index.json`

**Step 3: Verify completion**

You will see output like:
```
Reindexing skills...
Found 42 skills across 3 scopes
Processing... (this may take 1-2 minutes)
✓ Index updated successfully
```

**Step 4: Confirm with /pss-status**

Run `/pss-status` to verify the new index:
```
Last Modified: 2026-01-23 14:45:00  ← Should be current time
Total Skills Indexed: 42             ← Should match found skills
```

### 3.3 Understanding reindex progress and completion messages

**Progress indicators:**

| Message | Stage | Estimated Time |
|---------|-------|----------------|
| `Scanning directories...` | Finding skills | 1-5 seconds |
| `Reading skill metadata...` | Parsing SKILL.md files | 5-15 seconds |
| `Analyzing relationships...` | AI co-usage analysis | 30-90 seconds |
| `Writing index...` | Saving to disk | 1 second |

**Completion messages:**

- `✓ Index updated successfully` - Reindexing completed without errors
- `⚠ Partial reindex` - Some skills could not be processed (see warnings)
- `✗ Reindex failed` - Critical error occurred (see error details)

### 3.4 Verifying successful reindexing with /pss-status

After reindexing, always run `/pss-status` to confirm:

**Checklist:**
- [ ] "Index Status: ✓ Exists"
- [ ] "Last Modified" timestamp is current
- [ ] "Total Skills Indexed" matches expected count
- [ ] No warnings or errors shown
- [ ] Skills distributed across multiple categories

**If verification fails:**
- Check for error messages in `/pss-status` output
- Review troubleshooting section 5.4 below
- Try reindexing again
- Check file permissions on `~/.claude/skill_index.json`

---

## 4.0 Interpreting PSS skill suggestion output

### 4.1 Understanding confidence levels: HIGH, MEDIUM, LOW

PSS assigns a confidence level to each suggested skill based on the strength of evidence.

**Confidence levels explained:**

| Level | Score Range | Meaning | When You See This |
|-------|-------------|---------|-------------------|
| **HIGH** | 0.70 - 1.00 | Very strong match | User prompt contains explicit keywords, clear intent |
| **MEDIUM** | 0.40 - 0.69 | Good match | Partial keyword match or inferred intent |
| **LOW** | 0.10 - 0.39 | Weak match | Speculative suggestion, co-usage only |

**How to use confidence levels:**

- **HIGH**: Almost always activate - strong evidence of relevance
- **MEDIUM**: Consider context - may be relevant depending on task
- **LOW**: Usually skip - only activate if you know it is needed

**Example:**

User prompt: "Debug the failing unit tests"

| Skill | Confidence | Why |
|-------|-----------|-----|
| `python-test-fixer` | HIGH | Keywords: "debug", "unit tests" |
| `test-reporter` | MEDIUM | Related to testing, no explicit mention |
| `code-reviewer` | LOW | Co-usage with test skills, not directly relevant |

### 4.2 Understanding evidence types: intent, keyword, co_usage

PSS provides three types of evidence for each suggestion:

**1. Intent Evidence**

**What it is:** PSS analyzes the semantic meaning of your prompt to detect intent.

**Example intents:**
- "debugging" - You want to find and fix errors
- "testing" - You want to write or run tests
- "deployment" - You want to deploy or configure infrastructure

**How intent is matched:**
1. PSS reads your prompt
2. Extracts the main action or goal
3. Compares against skill categories
4. Assigns confidence based on match strength

**Example:**

Prompt: "I need to fix the broken authentication flow"
- Detected intent: **debugging** (keyword "fix"), **security** (keyword "authentication")
- Matched skills: `auth-debugger` (HIGH), `security-audit` (MEDIUM)

**2. Keyword Evidence**

**What it is:** Direct matches between words in your prompt and skill-defined keywords.

**Keyword matching logic:**
- Exact match: +0.3 confidence
- Partial match: +0.1 confidence
- Synonyms: +0.05 confidence (if skill defines them)

**Example:**

Skill `docker-deploy` keywords: `docker`, `containerize`, `dockerfile`, `docker-compose`

| Your Prompt | Match Type | Confidence Boost |
|-------------|------------|------------------|
| "build the docker image" | Exact: "docker" | +0.3 |
| "containerize the app" | Exact: "containerize" | +0.3 |
| "create docker-compose file" | Exact: "docker-compose" | +0.3 |
| "set up containers" | Partial: "container" | +0.1 |

**3. Co-usage Evidence**

**What it is:** Skills that are commonly used together based on AI-analyzed patterns.

**How co-usage works:**
1. During indexing, PSS analyzes skill descriptions and references
2. Identifies skills that complement each other
3. Stores co-usage relationships with weights
4. Suggests skills when a related skill is activated or mentioned

**Example co-usage relationships:**

| Skill A | Often Used With | Weight |
|---------|-----------------|--------|
| `python-test-writer` | `python-code-fixer` | 0.8 |
| `docker-deploy` | `github-actions-ci` | 0.7 |
| `api-designer` | `openapi-validator` | 0.9 |

**When co-usage suggestions appear:**

- **Scenario 1:** You activate a skill → PSS suggests related skills
- **Scenario 2:** Your prompt mentions a skill name → PSS suggests co-usage skills

**Co-usage confidence:**
- Strong co-usage (weight > 0.7): +0.2 confidence
- Moderate co-usage (weight 0.4-0.7): +0.1 confidence
- Weak co-usage (weight < 0.4): +0.05 confidence

### 4.3 Reading the skill suggestion table format

When PSS suggests skills, it outputs a formatted table:

```
Suggested Skills
================

Skill                    Confidence  Evidence
-----------------------------------------------
python-test-writer       HIGH        intent:testing, keyword:pytest, keyword:unittest
docker-deploy            MEDIUM      keyword:docker, co_usage:github-actions-ci(0.7)
code-reviewer            LOW         co_usage:python-test-writer(0.5)
```

**Column explanations:**

| Column | Content | How to Read |
|--------|---------|-------------|
| **Skill** | Skill name | The skill identifier (used in `/skill activate`) |
| **Confidence** | HIGH/MEDIUM/LOW | How strongly PSS recommends this skill |
| **Evidence** | Comma-separated list | Why PSS suggested this skill |

**Evidence format:**

Each evidence item has a type and value:

| Format | Type | Example |
|--------|------|---------|
| `intent:<category>` | Category match | `intent:testing` |
| `keyword:<word>` | Keyword match | `keyword:pytest` |
| `co_usage:<skill>(<weight>)` | Co-usage relationship | `co_usage:code-reviewer(0.7)` |

### 4.4 Deciding when to activate suggested skills

**Decision framework:**

**HIGH confidence suggestions:**
- Default action: **Activate** unless you know it is not needed
- These are strong matches with explicit evidence
- Skipping HIGH suggestions often means missing relevant help

**MEDIUM confidence suggestions:**
- Default action: **Review** the evidence and decide
- Check if the evidence makes sense for your task
- Activate if the intent or keywords align with your goal

**LOW confidence suggestions:**
- Default action: **Skip** unless you specifically need it
- These are speculative based on co-usage
- Only activate if you recognize the skill as relevant

**Example decision process:**

Task: "Write unit tests for the payment processor"

PSS suggests:
1. `python-test-writer` - HIGH (intent:testing, keyword:unit, keyword:tests)
   - **Decision: ACTIVATE** - Directly relevant
2. `code-coverage-reporter` - MEDIUM (co_usage:python-test-writer(0.8))
   - **Decision: ACTIVATE** - Useful for measuring test quality
3. `api-mocking` - MEDIUM (keyword:payment, co_usage:python-test-writer(0.6))
   - **Decision: ACTIVATE** - Payment processor likely calls external APIs
4. `docker-deploy` - LOW (co_usage:python-test-writer(0.3))
   - **Decision: SKIP** - Not relevant to writing tests

---

## 5.0 Troubleshooting common PSS issues

### 5.1 PSS commands not found or not responding

**Symptom:** Typing `/pss-status` or `/pss-reindex-skills` shows "command not found" or no response.

**Possible causes:**

1. **PSS plugin not installed**
   - **Check:** Run `/plugin list` and look for `perfect-skill-suggester`
   - **Fix:** Install PSS via marketplace or `--plugin-dir` flag

2. **PSS plugin not enabled**
   - **Check:** Run `/plugin list` and verify PSS shows "enabled: true"
   - **Fix:** Run `/plugin enable perfect-skill-suggester`

3. **Commands directory not loaded**
   - **Check:** Verify `commands/` directory exists in PSS plugin folder
   - **Fix:** Restart Claude Code to reload plugins

4. **Command files have wrong permissions**
   - **Check:** Run `ls -l` on command files, should be readable
   - **Fix:** Run `chmod +r` on command files

**Diagnostic steps:**

```bash
# 1. Check plugin installation
/plugin list

# 2. Check plugin directory structure
ls -la ~/.claude/plugins/perfect-skill-suggester/

# 3. Check command files exist
ls -la ~/.claude/plugins/perfect-skill-suggester/commands/

# 4. Restart Claude Code
# Exit and relaunch
```

### 5.2 Empty or missing skill suggestions

**Symptom:** PSS suggests zero skills, or misses skills you know are relevant.

**Possible causes:**

1. **Index not created**
   - **Check:** Run `/pss-status`, look for "Index Status: ✗ Missing"
   - **Fix:** Run `/pss-reindex-skills`

2. **Skills not in agent's available skills list**
   - **Explanation:** PSS only suggests skills that are available to the current agent (see PSS-ARCHITECTURE.md section 2.1)
   - **Check:** Review the agent's frontmatter `available_skills` block
   - **Fix:** Add missing skills to agent's skill list, then `/pss-reindex-skills`

3. **Stale index**
   - **Check:** Run `/pss-status`, compare "Last Modified" to when you added skills
   - **Fix:** Run `/pss-reindex-skills`

4. **Skill metadata incomplete**
   - **Check:** Open SKILL.md, verify frontmatter has `keywords` and `categories`
   - **Fix:** Add missing metadata, then `/pss-reindex-skills`

5. **Prompt keywords do not match skill keywords**
   - **Check:** Review skill's defined keywords in SKILL.md frontmatter
   - **Fix:** Either rephrase prompt or add keywords to skill, then reindex

**Diagnostic steps:**

```bash
# 1. Check index status
/pss-status

# 2. Reindex to refresh
/pss-reindex-skills

# 3. Try a test prompt with explicit keywords
"I need help with pytest unit testing"  # Should suggest python-test-writer

# 4. Check skill metadata
cat ~/.claude/skills/python-test-writer/SKILL.md | head -20
```

### 5.3 Index file errors or corruption

**Symptom:** `/pss-status` shows "corrupted" or "invalid JSON" error.

**Possible causes:**

1. **Partial write during indexing**
   - **Cause:** Indexing was interrupted (Ctrl+C, crash)
   - **Fix:** Delete index file, run `/pss-reindex-skills`

2. **Manual editing of index**
   - **Cause:** Index file was edited by hand and has syntax errors
   - **Fix:** Never edit index manually; delete and reindex

3. **Disk full during write**
   - **Cause:** No space left when writing index
   - **Fix:** Free up disk space, delete partial index, reindex

**How to recover:**

```bash
# 1. Back up corrupted index (optional)
cp ~/.claude/skill_index.json ~/.claude/skill_index.json.backup

# 2. Delete corrupted index
rm ~/.claude/skill_index.json

# 3. Rebuild from scratch
/pss-reindex-skills

# 4. Verify
/pss-status
```

**Prevention:**

- Do not interrupt `/pss-reindex-skills` while running
- Do not manually edit `skill_index.json`
- Ensure adequate disk space before reindexing

### 5.4 Reindexing failures and recovery

**Symptom:** `/pss-reindex-skills` fails with an error message.

**Common failure scenarios:**

**1. Permission denied on index file**

**Error message:** `Cannot write to ~/.claude/skill_index.json`

**Cause:** File permissions prevent writing

**Fix:**
```bash
chmod u+w ~/.claude/skill_index.json
/pss-reindex-skills
```

**2. Skills directory not found**

**Error message:** `No skills directories found`

**Cause:** PSS cannot locate skills/ folders in user/project/local scopes

**Fix:**
```bash
# Check if skills directories exist
ls -la ~/.claude/skills/
ls -la .claude/skills/
ls -la .claude/local/skills/

# If missing, install skills from marketplace
/plugin marketplace add <marketplace_url>
/plugin install <skill_name>
```

**3. Malformed skill metadata**

**Error message:** `Failed to parse SKILL.md frontmatter for <skill_name>`

**Cause:** SKILL.md frontmatter has YAML syntax errors

**Fix:**
```bash
# Find the problematic skill
grep -r "name: <skill_name>" ~/.claude/skills/

# Open and fix frontmatter YAML
# Ensure proper indentation, quotes, and YAML syntax
```

**4. AI analysis timeout**

**Error message:** `Timeout during co-usage analysis`

**Cause:** Too many skills, AI analysis takes too long

**Fix:**
- Split skills into batches
- Run `/pss-reindex-skills` again (it will retry)
- If persistent, report as a bug

**Recovery procedure:**

```bash
# 1. Check detailed error message
/pss-reindex-skills
# Read the error output carefully

# 2. Based on error type, apply fix above

# 3. Retry reindexing
/pss-reindex-skills

# 4. If still failing, try manual rebuild
# Delete index and retry
rm ~/.claude/skill_index.json
/pss-reindex-skills

# 5. If all else fails, report issue
# Include:
# - Full error message
# - /pss-status output
# - List of skills directories
```

---

## Summary

This reference document covers:
- **Command structure**: How PSS commands are named and invoked
- **Status checking**: Using `/pss-status` to monitor PSS health
- **Reindexing**: When and how to rebuild the skill index
- **Output interpretation**: Understanding confidence levels and evidence types
- **Troubleshooting**: Fixing common issues and recovering from errors

For architectural details and design decisions, see `PSS-ARCHITECTURE.md`.

For plugin validation, see `PLUGIN-VALIDATION.md`.
