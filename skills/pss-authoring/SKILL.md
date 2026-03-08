---
name: pss-authoring
description: "Best practices for PSS skill authoring, reindexing, and suggestion quality. Use when writing skills for PSS discovery or improving suggestion accuracy. Trigger with /pss-authoring."
user-invocable: false
---

# PSS Authoring Best Practices

## Overview

Guidance for writing skills that PSS discovers effectively, maintaining index health, and interpreting suggestions accurately. Complements pss-usage (core commands and workflows).

## Prerequisites

- PSS plugin installed and enabled
- Familiarity with SKILL.md frontmatter format
- Index built via `/pss-reindex-skills`

## Instructions

1. Add proper frontmatter to your SKILL.md (name, description, categories, keywords)
2. Choose keywords that match how users naturally phrase requests
3. Select 1-2 categories from the 16 standard options
4. Reindex after any metadata changes
5. Use `/pss-status` to verify index health regularly

### Checklist

Copy this checklist and track your progress:

- [ ] Frontmatter includes name, description, categories, keywords
- [ ] Keywords match natural user phrasing
- [ ] Categories selected from standard list
- [ ] Index rebuilt after changes (`/pss-reindex-skills`)
- [ ] Suggestion quality verified with test prompts

## References

- [Best Practices](references/pss-best-practices.md)
  - When to reindex your skill index
    - Events that always require reindexing
    - Events that may not require reindexing
  - Interpreting PSS skill suggestions accurately
    - Trusting confidence levels: HIGH, MEDIUM, LOW
    - Reading evidence types: intent, keyword, co_usage
    - Evaluating suggestions with multiple evidence types
  - Maintaining index health over time
    - Regular health checks with /pss-status
    - Keeping skill metadata current
    - Periodic clean rebuilds of the index
- [Skill Authoring Tips](references/pss-skill-authoring-tips.md)
  - Making your skills discoverable by PSS
    - Essential frontmatter fields for PSS indexing
    - Choosing effective keywords that match user prompts
    - Selecting accurate categories from the 16 standard options
  - Improving suggestion quality for your skills
    - Writing descriptions that help PSS match intent
    - Including tool and action keywords
    - Leveraging co-usage relationships automatically
  - Reference: Standard categories list

## Output

Improved skill metadata and index quality. Skills with proper frontmatter appear in PSS suggestions with higher confidence.

## Error Handling

- **Skills not appearing**: Check frontmatter has `keywords` and `categories`
- **Low confidence**: Improve description specificity and keyword coverage
- **Stale suggestions**: Run `/pss-reindex-skills` after metadata changes

## Examples

Input: A skill with generic description "Does testing"
Output: Improved to "Use when writing pytest unit tests with fixtures and mocking. Trigger with /python-testing."

## Resources

- **Standard categories**: `${CLAUDE_PLUGIN_ROOT}/schemas/pss-categories.json`
- **Companion skill**: pss-usage (core commands and workflows)
