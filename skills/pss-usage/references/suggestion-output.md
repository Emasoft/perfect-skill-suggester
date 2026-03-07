# Understanding PSS Suggestion Output

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

## Reading This Table

**Columns explained:**
- **Skill**: The skill identifier (use this with `/skill activate <skill>`)
- **Confidence**: How strongly PSS recommends (HIGH/MEDIUM/LOW)
- **Evidence**: Why PSS suggested this (intent match, keyword match, co-usage relationship)

**Evidence types:**
- `intent:<category>` - Your prompt matches this skill category
- `keyword:<word>` - Your prompt contains this keyword defined by the skill
- `co_usage:<skill>(<weight>)` - This skill is often used with another mentioned skill

## Decision Framework

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

For details on 4.1 Understanding confidence levels: HIGH, MEDIUM, LOW and 4.2 Understanding evidence types: intent, keyword, co_usage, see [pss-commands.md](pss-commands.md).
