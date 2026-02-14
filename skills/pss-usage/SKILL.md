---
name: pss-usage
description: "Use when working with Perfect Skill Suggester commands, interpreting skill suggestions, understanding confidence levels, or troubleshooting PSS issues. Trigger with /pss-usage or /pss-status slash commands."
argument-hint: "skill-name or keyword to search"
user-invocable: false
---

# PSS Usage Skill

## Overview

Perfect Skill Suggester (PSS) is an AI-powered plugin that automatically suggests relevant skills based on your prompts. This skill teaches you how to use PSS commands (`/pss-status`, `/pss-reindex-skills`), interpret skill suggestion output with confidence levels (HIGH/MEDIUM/LOW) and evidence types (intent/keyword/co_usage), and maintain the skill index for optimal performance.

## Prerequisites

Before using PSS, ensure:
- **PSS plugin is installed and enabled** - Verify with `/plugin list`
- **Skills are available** - At least one skill directory exists in `~/.claude/skills/` or project `.claude/skills/`
- **Index has been built** - Run `/pss-reindex-skills` at least once after installation
- **Write permissions** - PSS needs to write `skill-index.json` to `~/.claude/` directory

If index has never been built, PSS will show "Index file missing" error when trying to suggest skills.

## When to Use This Skill

**Activate this skill when:**
- User asks about skill suggestions ("which skills should I use?")
- User asks about PSS functionality ("how does skill suggestion work?")
- User requests reindexing ("update the skill index", "refresh skills")
- User asks for PSS status ("is PSS working?", "show me PSS info")
- Skill suggestions appear empty or incorrect
- PSS commands fail or produce errors

**Do NOT activate for:**
- General skill activation (use skill-specific skills instead)
- Writing skill content (use skill authoring skills instead)
- Plugin development (use plugin development skills instead)

---

## Instructions

### Step-by-Step Usage

1. **Verify PSS is working** - Run the status command to confirm the index exists and shows a recent timestamp:
   ```
   /pss-status
   ```

2. **Build or rebuild the index after installing skills** - Run the reindex command and wait for the "Phase 2: Analysis... Index updated successfully" message:
   ```
   /pss-reindex-skills
   ```

3. **Use natural prompts and review suggestions** - Enter a prompt describing the task; PSS will suggest relevant skills with confidence levels and evidence:
   ```
   "I need to write Python unit tests"
   ```

4. **Activate HIGH confidence skills** - Activate skills that PSS rates as HIGH confidence, review MEDIUM confidence based on evidence, and skip LOW confidence:
   ```
   /skill activate python-test-writer
   ```

5. **Reindex after major changes** - Run `/pss-reindex-skills` after installing, modifying, or deleting skills to keep suggestions accurate.

---

## Quick Reference

### Most Common Tasks

| Task | Command | When to Use |
|------|---------|-------------|
| **Check PSS health** | `/pss-status` | Before first use, after installing skills, when debugging issues |
| **Rebuild skill index** | `/pss-reindex-skills` | After adding/modifying skills, when suggestions are stale |
| **Understand suggestion** | Read confidence + evidence | Every time PSS suggests skills |

### Command Quick Examples

**Check if PSS is working:**
```
/pss-status
```

Expected output:
```
Perfect Skill Suggester Status
==============================
Index Status: ✓ Exists
Total Skills Indexed: 42
```

**Rebuild the index after adding skills:**
```
/pss-reindex-skills
```

> **⛔ CRITICAL:** PSS reindexing ALWAYS performs a FULL regeneration from scratch.
> The command first deletes ALL previous index data (skill-index.json, all .pss files, checklist),
> then discovers and analyzes ALL skills fresh. There is NO incremental update mode.
> This is mandatory to prevent stale paths, orphaned entries, and name mismatches.

Expected output:
```
Phase 0: Clean slate...
  ✓ Deleted skill-index.json
  ✓ Deleted 42 .pss files
  ✓ Clean slate verified

Phase 1: Discovery...
  ✓ Found 45 skills

Phase 2: Analysis...
  ✓ Index updated successfully
```

---

## Detailed Command Reference

For comprehensive information about all PSS commands, see [pss-commands.md](references/pss-commands.md):

### Contents of pss-commands.md

- **1.0 Understanding PSS command structure and invocation**
  - 1.1 Command naming conventions
  - 1.2 Command invocation from Claude Code chat

- **2.0 Using /pss-status to check PSS configuration and index health**
  - 2.1 Basic /pss-status usage without arguments
  - 2.2 Understanding /pss-status output: index statistics
  - 2.3 Understanding /pss-status output: skill counts and categories
  - 2.4 Interpreting /pss-status warnings and errors

- **3.0 Using /pss-reindex-skills to rebuild the skill index**
  - 3.1 When to reindex: detecting stale skill data
  - 3.2 Running /pss-reindex-skills workflow step-by-step
  - 3.3 Understanding reindex progress and completion messages
  - 3.4 Verifying successful reindexing with /pss-status

- **4.0 Interpreting PSS skill suggestion output**
  - 4.1 Understanding confidence levels: HIGH, MEDIUM, LOW
  - 4.2 Understanding evidence types: intent, keyword, co_usage
  - 4.3 Reading the skill suggestion table format
  - 4.4 Deciding when to activate suggested skills

- **5.0 Troubleshooting common PSS issues**
  - 5.1 PSS commands not found or not responding
  - 5.2 Empty or missing skill suggestions
  - 5.3 Index file errors or corruption
  - 5.4 Reindexing failures and recovery

---

## Output

### Understanding PSS Suggestion Output

When PSS suggests skills, you will see output like:

```
Suggested Skills
================

Skill                    Confidence  Evidence
-----------------------------------------------
python-test-writer       HIGH        intent:testing, keyword:pytest, keyword:unittest
docker-deploy            MEDIUM      keyword:docker, co_usage:github-actions-ci(0.7)
code-reviewer            LOW         co_usage:python-test-writer(0.5)
```

### Reading This Table

**Columns explained:**
- **Skill**: The skill identifier (use this with `/skill activate <skill>`)
- **Confidence**: How strongly PSS recommends (HIGH/MEDIUM/LOW)
- **Evidence**: Why PSS suggested this (intent match, keyword match, co-usage relationship)

**Evidence types:**
- `intent:<category>` - Your prompt matches this skill category
- `keyword:<word>` - Your prompt contains this keyword defined by the skill
- `co_usage:<skill>(<weight>)` - This skill is often used with another mentioned skill

### Decision Framework

**For HIGH confidence suggestions:**
- **Default action**: Activate the skill
- **Why**: Strong evidence indicates relevance
- **Skip only if**: You are certain the skill is not needed

**For MEDIUM confidence suggestions:**
- **Default action**: Review the evidence and decide
- **Consider**: Does the evidence align with your task?
- **Activate if**: Intent or keywords match your goal

**For LOW confidence suggestions:**
- **Default action**: Skip the skill
- **Why**: Speculative suggestion based on co-usage only
- **Activate only if**: You specifically recognize the skill as needed

**Example decision process:**

Prompt: "Write unit tests for the authentication module"

PSS suggests:
1. `python-test-writer` (HIGH, intent:testing, keyword:unit, keyword:tests)
   - **Action: ACTIVATE** - Directly needed for writing tests
2. `auth-security-checker` (MEDIUM, keyword:authentication, co_usage:python-test-writer(0.7))
   - **Action: ACTIVATE** - Relevant for testing auth logic
3. `docker-deploy` (LOW, co_usage:python-test-writer(0.3))
   - **Action: SKIP** - Not relevant to writing tests

For detailed explanation of confidence levels and evidence scoring, see section 4.0 in [pss-commands.md](references/pss-commands.md).

---

## Common Workflows

### Workflow 1: First-Time PSS Setup

**Scenario**: You just installed PSS and want to verify it works.

**Steps:**

1. **Check initial status**
   ```
   /pss-status
   ```

   Expected: "Index file missing" or old index

2. **Build the index**
   ```
   /pss-reindex-skills
   ```

   Wait for completion (1-2 minutes)

3. **Verify success**
   ```
   /pss-status
   ```

   Expected: "Index Status: ✓ Exists", recent timestamp

4. **Test with a prompt**
   ```
   "I need to write Python unit tests"
   ```

   Expected: PSS suggests relevant testing skills with HIGH confidence

**If any step fails**: See troubleshooting in section 5.0 of [pss-commands.md](references/pss-commands.md).

### Workflow 2: Adding New Skills

**Scenario**: You installed new skills from a marketplace.

**Steps:**

1. **Install skills** (via marketplace or manual installation)
   ```
   /plugin install new-skill-pack
   ```

2. **Reindex immediately**
   ```
   /pss-reindex-skills
   ```

   Why: PSS does not auto-detect new skills

3. **Verify new skills indexed**
   ```
   /pss-status
   ```

   Check: "Total Skills Indexed" should increase

4. **Test suggestion**
   Create a prompt using keywords from the new skills

   Expected: New skills appear in PSS suggestions

### Workflow 3: Debugging Missing Suggestions

**Scenario**: PSS should suggest a skill but does not.

**Steps:**

1. **Check PSS is working**
   ```
   /pss-status
   ```

   Verify: "Index Status: ✓ Exists", no errors

2. **Reindex to refresh**
   ```
   /pss-reindex-skills
   ```

3. **Check skill metadata**
   - Open the skill's SKILL.md
   - Verify frontmatter has `keywords` and `categories`
   - Check if your prompt keywords match skill keywords

4. **Try explicit keywords**
   Rephrase your prompt to use exact keywords from skill frontmatter

   Example: If skill has `keywords: ["pytest", "unittest"]`, try:
   ```
   "Write pytest tests for the API"
   ```

5. **Check skill is available to agent**
   - PSS only suggests skills the current agent can use
   - Review agent's frontmatter `available_skills` list
   - If skill missing, add it to agent's skill list

For detailed troubleshooting, see section 5.2 in [pss-commands.md](references/pss-commands.md).

---

## Error Handling

**Problem: PSS commands not found**
- See section 5.1 in [pss-commands.md](references/pss-commands.md)
- Quick fix: Check plugin enabled with `/plugin list`

**Problem: No skill suggestions**
- See section 5.2 in [pss-commands.md](references/pss-commands.md)
- Quick fix: Run `/pss-reindex-skills`

**Problem: Index file corrupted**
- See section 5.3 in [pss-commands.md](references/pss-commands.md)
- Quick fix: Delete `~/.claude/skill_index.json` and reindex

**Problem: Reindexing fails**
- See section 5.4 in [pss-commands.md](references/pss-commands.md)
- Quick fix: Check error message, verify skills directories exist

---

## Best Practices

For detailed best practices, see [pss-best-practices.md](references/pss-best-practices.md):

- **1.0 When to reindex your skill index**
  - 1.1 Events that always require reindexing
  - 1.2 Events that may not require reindexing
- **2.0 Interpreting PSS skill suggestions accurately**
  - 2.1 Trusting confidence levels: HIGH, MEDIUM, LOW
  - 2.2 Reading evidence types: intent, keyword, co_usage
  - 2.3 Evaluating suggestions with multiple evidence types
- **3.0 Maintaining index health over time**
  - 3.1 Regular health checks with /pss-status
  - 3.2 Keeping skill metadata current
  - 3.3 Periodic clean rebuilds of the index

---

## Examples

### Example 1: Testing Workflow

**User prompt:**
```
"Write pytest tests for the authentication module"
```

**PSS suggests:**
- `python-test-writer` (HIGH, intent:testing, keyword:pytest, keyword:tests)
- `auth-security-checker` (MEDIUM, keyword:authentication, co_usage:python-test-writer(0.7))
- `docker-deploy` (LOW, co_usage:python-test-writer(0.3))

**Actions:**
1. Activate `python-test-writer` (HIGH confidence, directly needed)
2. Activate `auth-security-checker` (MEDIUM confidence, relevant for auth testing)
3. Skip `docker-deploy` (LOW confidence, not relevant to test writing)

---

### Example 2: First-Time Setup

**Commands:**
```
/pss-status
```
Output: "Index file missing"

```
/pss-reindex-skills
```
Output: "Phase 2: Analysis... ✓ Index updated successfully. Total: 42 skills"

```
/pss-status
```
Output: "Index Status: ✓ Exists. Total Skills Indexed: 42"

**Result:** PSS is now ready to suggest skills.

---

### Example 3: Debugging Missing Suggestions

**Problem:** Expected skill not suggested.

**Steps:**
1. Check PSS health: `/pss-status` → Index exists
2. Refresh index: `/pss-reindex-skills` → Completed successfully
3. Verify skill metadata: Open `SKILL.md`, check frontmatter has `keywords` and `categories`
4. Rephrase prompt with explicit keywords: "Write pytest unit tests" → `python-test-writer` now appears

**Resolution:** Keyword matching is sensitive; use exact terms from skill metadata.

---

## Resources

### Related Documentation

- **[pss-commands.md](references/pss-commands.md)** - Complete command reference with detailed explanations of `/pss-status` and `/pss-reindex-skills`
- **PSS Architecture** - See `docs/PSS-ARCHITECTURE.md` in PSS plugin directory for design principles
- **Plugin Validation** - See `docs/PLUGIN-VALIDATION.md` for PSS validation procedures

### Related Skills

- **Skill authoring skills** - For creating/modifying skills that PSS will index
- **Plugin development skills** - For modifying PSS plugin behavior

### External References

- **Agent Skills Open Standard** - https://github.com/agentskills/agentskills
- **Claude Code Documentation** - https://platform.claude.com/llms.txt

---

## Checklist

Use this checklist to verify your PSS workflow is complete:

- [ ] PSS plugin is installed and enabled (`/plugin list` shows it)
- [ ] Skill index has been built at least once (`/pss-reindex-skills`)
- [ ] `/pss-status` shows "Index Status: Exists" with a recent timestamp
- [ ] Skill count in `/pss-status` matches expected number of installed skills
- [ ] Test a natural language prompt and verify suggestions appear
- [ ] HIGH confidence suggestions match your task intent
- [ ] MEDIUM confidence suggestions have relevant evidence
- [ ] After installing new skills, reindex was run again
- [ ] After modifying skill metadata, reindex was run again
- [ ] Skills you authored have `keywords` and `categories` in frontmatter

---

## Summary

**Two commands, simple usage:**
- `/pss-status` - Check PSS health
- `/pss-reindex-skills` - Rebuild skill index

**Three confidence levels:**
- HIGH - Activate by default
- MEDIUM - Review evidence
- LOW - Skip unless certain

**Three evidence types:**
- intent - Semantic category match
- keyword - Word match
- co_usage - Related skill correlation

**For complete details, see:**
- [pss-commands.md](references/pss-commands.md) - Full command reference and troubleshooting

---

## Notes for Skill Authors

For tips on making your skills discoverable by PSS, see [pss-skill-authoring-tips.md](references/pss-skill-authoring-tips.md):

- **1.0 Making your skills discoverable by PSS**
  - 1.1 Essential frontmatter fields for PSS indexing
  - 1.2 Choosing effective keywords that match user prompts
  - 1.3 Selecting accurate categories from the 16 standard options
- **2.0 Improving suggestion quality for your skills**
  - 2.1 Writing descriptions that help PSS match intent
  - 2.2 Including tool and action keywords
  - 2.3 Leveraging co-usage relationships automatically
- **3.0 Reference: Standard categories list**
