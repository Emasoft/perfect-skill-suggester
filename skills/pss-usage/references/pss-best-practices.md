# PSS Best Practices

## Contents

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

## 1.0 When to reindex your skill index

### 1.1 Events that always require reindexing

**Always run `/pss-reindex-skills` after:**
- Installing new skills
- Modifying skill metadata (name, description, keywords, categories)
- Moving skills between directories
- Deleting skills

PSS does not auto-detect changes to the skill directories. The index reflects the state at the time of the last reindex.

### 1.2 Events that may not require reindexing

**Check but may not need reindex:**
- Modifying skill content (SKILL.md body text, references) -- these do not affect keyword or category matching
- Adding or removing skill reference files -- references are not indexed by PSS

---

## 2.0 Interpreting PSS skill suggestions accurately

### 2.1 Trusting confidence levels: HIGH, MEDIUM, LOW

**Trust the confidence level as your default decision guide:**
- **HIGH** = Activate the skill unless you are certain it is not needed
- **MEDIUM** = Review the evidence and decide based on task relevance
- **LOW** = Skip the skill unless you specifically recognize the need for it

### 2.2 Reading evidence types: intent, keyword, co_usage

**Evidence types ranked by strength:**
- `intent` evidence is strongest -- it means PSS detected a semantic category match between your prompt and the skill
- `keyword` evidence is explicit -- it means a specific word in your prompt matched a keyword defined by the skill
- `co_usage` evidence is weakest -- it means this skill is often used alongside another skill that was already matched (correlation only, not causation)

### 2.3 Evaluating suggestions with multiple evidence types

Suggestions with multiple evidence types are stronger than single-evidence suggestions:

| Evidence Combination | Strength | Example |
|---------------------|----------|---------|
| `intent:testing, keyword:pytest` | Very strong | Semantic + explicit word match |
| `keyword:docker` alone | Moderate | One explicit match |
| `co_usage:skill(0.5)` alone | Weak | Correlation only |

When PSS provides multiple evidence types for a suggestion, you can be more confident in its relevance.

---

## 3.0 Maintaining index health over time

### 3.1 Regular health checks with /pss-status

**Recommended schedule:**
- Run `/pss-status` weekly or after major skill changes
- Look for warnings about stale index (old timestamp)
- Verify that "Total Skills Indexed" matches your expected number of installed skills

### 3.2 Keeping skill metadata current

**Keep your skill metadata aligned with actual skill capabilities:**
- Update skill keywords when adding new features to a skill
- Review skill categories for accuracy after refactoring
- Add co-usage hints in skill descriptions to help PSS detect relationships

### 3.3 Periodic clean rebuilds of the index

**Occasional full rebuild ensures accuracy:**
- Delete the index file (`~/.claude/skill_index.json`) every few months
- Rebuild with `/pss-reindex-skills`
- This ensures that AI co-usage analysis (Phase 2) reflects the current skill landscape

Note: `/pss-reindex-skills` always performs a full rebuild from scratch -- there is no incremental mode. So running reindex is itself a clean rebuild. Deleting the index file first is optional but ensures no stale data persists.
