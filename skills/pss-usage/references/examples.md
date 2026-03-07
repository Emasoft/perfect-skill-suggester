# PSS Usage Examples

## Example 1: Testing Workflow

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

## Example 2: First-Time Setup

**Commands:**
```
/pss-status
```
Output: "Index file missing"

```
/pss-reindex-skills
```
Output: "Phase 2: Analysis... Index updated successfully. Total: 42 skills"

```
/pss-status
```
Output: "Index Status: Exists. Total Skills Indexed: 42"

**Result:** PSS is now ready to suggest skills.

---

## Example 3: Debugging Missing Suggestions

**Problem:** Expected skill not suggested.

**Steps:**
1. Check PSS health: `/pss-status` -> Index exists
2. Refresh index: `/pss-reindex-skills` -> Completed successfully
3. Verify skill metadata: Open `SKILL.md`, check frontmatter has `keywords` and `categories`
4. Rephrase prompt with explicit keywords: "Write pytest unit tests" -> `python-test-writer` now appears

**Resolution:** Keyword matching is sensitive; use exact terms from skill metadata.
