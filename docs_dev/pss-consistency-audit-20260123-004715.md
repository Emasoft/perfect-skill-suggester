# PSS Consistency Audit Report

**Generated:** 2026-01-23 00:46:25

## Summary

**MAJOR INCONSISTENCY FOUND**: Documentation heavily promotes multi-word phrases (3+ words), but Rust fuzzy matching only works on single words. Substring matching supports multi-word phrases, but typo tolerance does not.

---

## 1. Documented Format (PSS-ARCHITECTURE.md)

**Keywords definition (line 49-53):**
> Keywords are a SUPERSET of categories:
> - Include category terms PLUS specific tools, names, actions, technologies
> - Examples: "docker", "next.js", "pytest", "github actions", "fix ci pipeline"

**Format:** Allows both single words and multi-word phrases. No explicit preference stated in architecture doc.

---

## 2. Reindex Skill Format (pss-reindex-skills.md)

**HEAVILY EMPHASIZES multi-word phrases:**

Line 23:
> - **Multi-word phrases**: `fix ci pipeline`, `review pull request`, `set up github actions`

Line 114:
> Generate rio-compatible keywords (8-15 keywords, **multi-word phrases preferred**)

Line 178:
> **PREFER MULTI-WORD PHRASES** (3+ words) - they are MORE SPECIFIC

Line 186-191:
> | Specificity | Example | Why |
> | **HIGH** | "set up github actions workflow" | Very specific phrase |
> | **HIGH** | "github actions yaml" | Tool + format |
> | **MEDIUM** | "ci/cd pipeline" | Domain-specific compound |

**Format:** Multi-word phrases (3+ words) are strongly preferred and recommended.

---

## 3. Rust Binary Matching Logic (main.rs)

**Two-phase matching:**

### Phase 1: Substring Match (lines 1406-1407)
```rust
if expanded_lower.contains(&kw_lower) {
    matched = true;
}
```
**Supports multi-word phrases:** ✅ YES
- "github actions workflow" will match if those words appear in sequence in the prompt

### Phase 2: Fuzzy Match Fallback (lines 1410-1416)
```rust
for word in &prompt_words {
    if is_fuzzy_match(word, &kw_lower) {
        matched = true;
        is_fuzzy = true;
        break;
    }
}
```
**Supports multi-word phrases:** ❌ NO
- Iterates over INDIVIDUAL words from the prompt
- Compares each word against the ENTIRE keyword using Damerau-Levenshtein
- If keyword is "github actions workflow", it will compare:
  - "github" vs "github actions workflow" → length diff too large, no match
  - "actions" vs "github actions workflow" → length diff too large, no match

**Result:** Multi-word phrase keywords NEVER get fuzzy matching (typo tolerance)

---

## 4. JSON Schema (pss-schema.json)

Line 48:
> "Flat array of lowercase keywords/phrases for rio v2.0 matching. Keywords are a SUPERSET of categories - they include category terms PLUS specific tools, names, actions, technologies (chrome, next.js, git, pytest, docker, setup, configure, etc.)."

**Format:** Allows both single words and multi-word phrases. Consistent with architecture doc.

---

## Inconsistency Analysis

| Component | Single Words | Multi-Word Phrases (3+) | Preference |
|-----------|--------------|-------------------------|------------|
| **Architecture Doc** | Allowed | Allowed | No explicit preference |
| **Reindex Command** | Discouraged | **STRONGLY PREFERRED** | Multi-word (3+) |
| **Schema** | Allowed | Allowed | No explicit preference |
| **Rust Substring Match** | ✅ Works | ✅ Works | No preference |
| **Rust Fuzzy Match** | ✅ Works | ❌ **BROKEN** | Single words only |

---

## The Problem

1. **Documentation says:** "PREFER MULTI-WORD PHRASES (3+ words) - they are MORE SPECIFIC"
2. **Rust binary does:** 
   - Substring match: Works for multi-word phrases ✅
   - Fuzzy match: **Only works for single words** ❌

**Impact:**
- Keywords like "github actions workflow" will match exact text, but NOT typos like "githb actions workflow"
- Keywords like "github" will match both exact ("github") AND typos ("githb") via fuzzy match
- This creates an accuracy vs. robustness tradeoff that contradicts the "prefer multi-word" guidance

---

## Root Cause

**Fuzzy matching logic (line 1410-1416)** iterates over `prompt_words` (individual words split from the prompt), then compares each word to the ENTIRE keyword string.

For multi-word keywords, this means:
- Prompt word: "github" (6 chars)
- Keyword: "github actions workflow" (25 chars)
- Length difference: 19 → exceeds threshold (line 775: `len_diff > 2`)
- Result: No fuzzy match

**The fuzzy matcher assumes keywords are single words.**

---

## Recommendations

### Option 1: Fix Rust Fuzzy Matching (Preferred)
Split multi-word keywords into individual words and try fuzzy matching on each:

```rust
// Split keyword into words
let keyword_words: Vec<&str> = kw_lower.split_whitespace().collect();
if keyword_words.len() == 1 {
    // Single-word keyword - use existing fuzzy logic
    for word in &prompt_words {
        if is_fuzzy_match(word, &kw_lower) { ... }
    }
} else {
    // Multi-word keyword - match each word individually
    let all_matched = keyword_words.iter().all(|kw_word| {
        prompt_words.iter().any(|pw| is_fuzzy_match(pw, kw_word))
    });
    if all_matched { matched = true; is_fuzzy = true; }
}
```

### Option 2: Update Documentation (Easier)
Change guidance to recommend **2-word phrases max** or single words for fuzzy matching to work.

### Option 3: Hybrid Approach
- Use multi-word phrases for HIGH specificity (exact match only)
- Include single-word variants for fuzzy matching (typo tolerance)
- Example: `["github actions workflow", "github", "actions", "workflow"]`

---

## Verification

**Test case to confirm the issue:**

```bash
# Create index with multi-word keyword
echo '{
  "version": "3.0",
  "skills": {
    "test-skill": {
      "keywords": ["github actions workflow"],
      "path": "/test/SKILL.md",
      "type": "skill"
    }
  }
}' > /tmp/test-index.json

# Test exact match (should work)
echo '{"prompt":"help with github actions workflow"}' | pss --format json

# Test fuzzy match (will NOT work)
echo '{"prompt":"help with githb actions workflow"}' | pss --format json
```

Expected: Fuzzy match fails because "githb" vs "github actions workflow" length difference > 2.

---

## Files Requiring Updates

1. **rust/skill-suggester/src/main.rs** - Fix fuzzy matching logic
2. **commands/pss-reindex-skills.md** - Update keyword guidance (if not fixing Rust)
3. **docs/PSS-ARCHITECTURE.md** - Clarify multi-word phrase limitations
4. **schemas/pss-schema.json** - Add constraint on keyword format
