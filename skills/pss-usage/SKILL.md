---
name: pss-usage
description: "How to use Perfect Skill Suggester commands and interpret skill suggestions"
argument-hint: ""
user-invocable: false
---

# PSS Usage Skill

## Purpose

This skill teaches you how to:
- Use PSS (Perfect Skill Suggester) commands
- Interpret skill suggestion output
- Understand confidence levels and evidence types
- Troubleshoot common PSS issues
- Maintain the skill index

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

Expected output:
```
Reindexing skills...
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

## Understanding PSS Suggestion Output

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

## Troubleshooting Quick Links

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

### When to Reindex

**Always reindex after:**
- Installing new skills
- Modifying skill metadata (name, description, keywords, categories)
- Moving skills between directories
- Deleting skills

**Check but may not need reindex:**
- Modifying skill content (SKILL.md body, references)
- Adding/removing skill references (does not affect suggestions)

### Interpreting Suggestions

**Trust the confidence level:**
- HIGH = activate unless you know better
- MEDIUM = consider the evidence
- LOW = skip unless you recognize the need

**Read the evidence:**
- `intent` evidence is strongest (semantic understanding)
- `keyword` evidence is explicit (word matching)
- `co_usage` evidence is weakest (correlation only)

**Multiple evidence types are stronger:**
- `intent:testing, keyword:pytest` = very strong
- `keyword:docker` alone = moderate
- `co_usage:skill(0.5)` alone = weak

### Maintaining Index Health

**Regular checks:**
- Run `/pss-status` weekly or after major skill changes
- Look for warnings about stale index
- Verify skill counts match expectations

**Keep metadata current:**
- Update skill keywords when adding new features
- Review skill categories for accuracy
- Add co-usage hints in skill descriptions

**Clean index occasionally:**
- Delete index file every few months
- Rebuild with `/pss-reindex-skills`
- Ensures AI co-usage analysis is fresh

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

If you are developing skills and want PSS to suggest them effectively:

**Essential frontmatter fields:**
```yaml
---
name: my-skill
description: "When and why to use this skill (be specific!)"
categories: ["testing", "debugging"]  # Pick from 16 standard categories
keywords: ["pytest", "unittest", "test-fixture", "mock"]
---
```

**Tips for better suggestions:**
- Use specific keywords that users naturally type
- Include tool names (pytest, docker, git, etc.)
- Include action verbs (debug, deploy, refactor, etc.)
- Mention common use cases in description
- Choose accurate categories from the 16 standard options

**Categories list:**
debugging, testing, deployment, refactoring, documentation, performance, security, database, api, frontend, backend, devops, data-processing, ml-ai, collaboration, other

**Co-usage relationships:**
- PSS automatically detects co-usage during indexing
- Mention related skills in your SKILL.md content
- Reference complementary skills in examples
- No manual co-usage configuration needed

For PSS architecture and design, see `docs/PSS-ARCHITECTURE.md` in the PSS plugin directory.
