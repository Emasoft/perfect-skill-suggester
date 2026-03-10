# Merge Protocol — Combining Agent Baseline with Cherry-Picked Requirements

## Table of Contents

- [Deduplication](#deduplication)
- [Tier Placement Rules](#tier-placement-rules)
- [Exclusion Documentation](#exclusion-documentation)
- [Verification and Validation](#verification-and-validation)
- [Merge Checklist](#merge-checklist)

---

## Deduplication

Before adding cherry-picked elements to the profile, check for exact and semantic duplicates:

1. **Exact name match**: If a requirements candidate has the same name as an agent baseline element → skip (already covered)
2. **Semantic overlap**: If a requirements candidate covers the same scope as an existing element → skip and note in `[skills.excluded]`
3. **Superset/subset**: If the requirements candidate is a strict superset of an existing element → replace the existing one. If it's a strict subset → skip.

## Tier Placement Rules

Cherry-picked requirements elements follow these placement rules:

| Element type | Tier placement |
|-------------|---------------|
| Skills | **secondary** (default) or **specialized** (if niche) |
| Agents | `[agents].recommended` |
| Commands | `[commands].recommended` |
| Rules | `[rules].recommended` |
| MCP servers | `[mcp].recommended` |
| LSP servers | `[lsp].recommended` (only if agent writes code) |

**NEVER place requirements-derived skills in the primary tier.** Primary is reserved for:
- `auto_skills` from the agent's frontmatter
- Skills intrinsic to the agent's own role (from Pass 1)

**Tier size limits still apply after merge:**
- primary ≤ 7 (may extend for auto_skills)
- secondary ≤ 12
- specialized ≤ 8

If secondary is at capacity after adding cherry-picked elements, move the lowest-relevance items to specialized. If specialized is also full, the least relevant cherry-picked elements must be dropped (documented in excluded with reason "Tier capacity exceeded").

## Exclusion Documentation

Every rejected requirements candidate must be documented in `[skills.excluded]`:

```toml
[skills.excluded]
# "react-frontend" = "Excluded: requirements element outside agent specialization (database agent)"
# "stripe-integration" = "Excluded: requirements element outside agent specialization (database agent)"
# "cart-management" = "Excluded: requirements element — no duty match for this agent"
```

The reason MUST include:
1. That it came from requirements scoring (not agent scoring)
2. WHY it was rejected (domain mismatch, no duty match, redundant with existing element)

## Verification and Validation

After merging, run both scripts:

```bash
# Step 1: Verify all element names (anti-hallucination)
uv run "${PLUGIN_ROOT}/scripts/pss_verify_profile.py" "${OUTPUT_PATH}" \
  --agent-def "${AGENT_PATH}" --verbose

# Step 2: Validate TOML structure
uv run "${PLUGIN_ROOT}/scripts/pss_validate_agent_toml.py" "${OUTPUT_PATH}" \
  --check-index --verbose
```

If either fails → fix and re-run (max 2 cycles).

## Re-Alignment Scenario

When `pss-change-agent-profile` is called with `--requirements` on an existing profile that already had requirements merged, special rules apply:

### Stale Element Removal

Elements cherry-picked from a previous requirements pass that are no longer relevant:

1. **Compare old vs new**: Score the new requirements document → get new `REQS_CANDIDATES`
2. **Identify stale**: Any element in the profile tagged as requirements-derived (in secondary/specialized) that does NOT appear in the new `REQS_CANDIDATES` is stale
3. **Remove stale**: Move stale elements to `[skills.excluded]` with reason "Removed: no longer relevant to updated requirements"

### Idempotency

Running requirements alignment twice with the same requirements document must produce the same profile:

1. **Skip duplicates**: If a cherry-picked candidate is already in the profile → skip silently
2. **Preserve tier placement**: Do not re-tier elements already placed by a previous merge
3. **Preserve user overrides**: If the user manually moved an element via `pss-change-agent-profile`, do not revert it

### Provenance Tracking

To support re-alignment, the merge step should add a comment to each cherry-picked element indicating its origin:

```toml
[skills]
secondary = [
    "postgresql-best-practices",  # from requirements: e-commerce-prd.md
    "redis-best-practices",       # from requirements: e-commerce-prd.md
    "api-development",            # from agent baseline
]
```

This is informational only — the validator ignores inline TOML comments. But it helps the profiler distinguish baseline vs requirements-derived elements during re-alignment.

## Merge Checklist

- [ ] Exact name deduplication: no cherry-picked element duplicates a baseline element
- [ ] Semantic deduplication: no cherry-picked element overlaps an existing element's scope
- [ ] All cherry-picked skills placed in secondary or specialized (never primary)
- [ ] Tier limits respected after merge (secondary ≤ 12, specialized ≤ 8)
- [ ] All rejected requirements candidates documented in `[skills.excluded]` with reason
- [ ] Re-alignment: stale elements from previous requirements pass removed
- [ ] Re-alignment: idempotency verified (no duplicate additions, no tier reverts)
- [ ] Verification script passed (exit code 0)
- [ ] Validation script passed (exit code 0)
- [ ] Clean up: temporary requirements descriptor file deleted
