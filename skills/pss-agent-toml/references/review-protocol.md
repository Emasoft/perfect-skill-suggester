# Review & Refinement Protocol (Phase 7)

## Table of Contents

- [Self-Review Checklist](#self-review-checklist)
  - [Check 1: Name Integrity](#check-1-name-integrity)
  - [Check 2: Auto-Skills Pinning](#check-2-auto-skills-pinning)
  - [Check 3: Non-Coding Agent Filter](#check-3-non-coding-agent-filter)
  - [Check 4: Coverage Analysis](#check-4-coverage-analysis)
  - [Check 5: Exclusion Quality](#check-5-exclusion-quality)
  - [Self-Review Fix Cycle](#self-review-fix-cycle)
- [Interactive Review Protocol](#interactive-review-protocol)
  - [Activation Conditions](#activation-conditions)
  - [Review Summary Format](#review-summary-format)
  - [User Directives](#user-directives)
- [Search Integration](#search-integration)
  - [Finding Alternatives](#finding-alternatives)
  - [Comparing Candidates](#comparing-candidates)
  - [Adding from Search Results](#adding-from-search-results)
- [Re-validation Loop](#re-validation-loop)
- [Completion Checklist](#completion-checklist)

---

## Self-Review Checklist

After validation (Step 8) passes, the profiler MUST perform a self-review before reporting success. Re-read BOTH the generated `.agent.toml` AND the original agent definition `.md` file, then check:

### Check 1: Name Integrity

Compare every name in the `.agent.toml` against the original agent definition:

- Every skill in `[skills].primary`, `secondary`, `specialized` that appears in the agent definition MUST match the EXACT name used there
- Every agent in `[agents].recommended` that appears in the agent definition MUST match the EXACT name from routing tables or delegation sections
- Every command in `[commands].recommended` that appears in the agent definition MUST match the EXACT name

**Failure pattern**: The binary may return similar-named elements from the local index (e.g., `eia-code-reviewer` instead of `amia-code-reviewer`). The profiler must have preserved the original names, NOT substituted local matches.

**Fix**: Replace any mismatched names with the exact names from the agent definition.

### Check 2: Auto-Skills Pinning

Extract the `auto_skills:` list from the agent definition frontmatter. Verify:

- ALL auto_skills appear in `[skills].primary`
- NONE of the auto_skills appear in `secondary` or `specialized`

**Fix**: Move any demoted auto_skills back to `primary`. If this exceeds the primary limit of 7, extend the limit (auto_skills take absolute priority).

### Check 3: Non-Coding Agent Filter

If `writes_code` was determined to be `false` in Step 1 (orchestrators, coordinators, managers, gatekeepers):

- `[lsp].recommended` MUST be `[]` (empty)
- No language-specific linting/formatting skills in any tier (eslint, ruff, prettier, biome, etc.)
- No code-fixing agents (python-code-fixer, js-code-fixer, etc.)
- No test-writing agents (python-test-writer, js-test-writer, etc.)

**Fix**: Remove offending elements. Set LSP to `[]`.

### Check 4: Coverage Analysis

For each duty/domain extracted from the agent definition in Step 1, verify at least one element in the profile supports it:

- List every duty from the agent definition
- For each duty, find at least one skill/agent/command/MCP that addresses it
- Flag duties with NO supporting elements as **coverage gaps**

**Fix**: Use `pss search` to find elements covering the gap. If found, add to appropriate tier.

### Check 5: Exclusion Quality

Check every entry in `[skills.excluded]`:

- Each excluded skill MUST have a specific, actionable reason (not generic like "not relevant")
- Valid reasons: mutual exclusivity, stack incompatibility, redundancy, obsolescence, non-coding filter
- Invalid reasons: "not relevant", "low score", "not needed" (too vague)

**Fix**: Rewrite vague exclusion reasons with specific justifications.

### Self-Review Fix Cycle

If ANY check fails:

1. Fix the `.agent.toml` in-place using the Edit tool
2. Re-run validation (Step 8) to ensure the fix didn't break TOML syntax
3. Re-run the self-review checks

**Maximum 2 fix cycles.** If checks still fail after 2 cycles, the issue is likely a deeper pipeline problem — flag it and activate Interactive Review (even in autonomous mode).

---

## Interactive Review Protocol

### Activation Conditions

Interactive review activates when ANY of these is true:

1. **User requested it**: `--interactive` flag was passed to `/pss-setup-agent`
2. **Self-review found unfixable issues**: After 2 fix cycles, some checks still fail
3. **Truly unresolvable conflicts**: Two elements with equal value and no deciding factor
4. **User asks mid-session**: User says "let me review", "show me the profile", "I want to check"

### Review Summary Format

Present this summary to the user (using the exact format below for consistency):

```
PROFILE REVIEW: <agent-name>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Skills:  P=<n>  S=<n>  Sp=<n>  Excluded=<n>
Agents:  <n>    Commands: <n>    Rules: <n>
MCP:     <n>    LSP: <n>         Hooks: <n>

PRIMARY SKILLS:
  ✓ <name>    (auto_skill, from agent definition)
  ✓ <name>    (scored <score>, <confidence> confidence)
  + <name>    (added: <reason>)
  ...

SECONDARY SKILLS:
  ✓ <name>    (scored <score>)
  ...

SPECIALIZED SKILLS:
  ✓ <name>    (scored <score>)
  ...

EXCLUDED:
  ✗ <name>    (<reason>)
  ...

SUB-AGENTS: <comma-separated list>
COMMANDS: <comma-separated list>
RULES: <comma-separated list>
MCP: <comma-separated list>
LSP: <list or "none (non-coding agent)">

SELF-REVIEW: <n> issues found, <n> auto-fixed
  ⚠ <issue description> (if any remain)
  ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Directives:
  approve         Accept profile as-is
  include <name>  Add an element (searches index)
  exclude <name>  Remove an element (with reason)
  swap <a> <b>    Replace element <a> with <b>
  move <n> <tier> Move element to primary/secondary/specialized
  search <query>  Search the index for elements
  done            Same as approve
```

### User Directives

The profiler accepts these directives during interactive review:

**`include <name>`**
Add an element to the profile. The profiler:
1. Searches the index: `pss search "<name>" --top 5`
2. If found, shows matches and asks which one
3. Determines the appropriate type (skill, agent, command, rule, MCP, LSP)
4. Adds to the appropriate tier (defaults to secondary for skills; user can specify)
5. Re-validates

**`exclude <name>`**
Remove an element from the profile. The profiler:
1. Finds the element in the current TOML (any section)
2. Removes it
3. If it's a skill, adds it to `[skills.excluded]` with the reason "Excluded by user"
4. Asks the user for a specific reason (optional — uses "Excluded by user directive" if none given)
5. Re-validates

**`swap <old> <new>`**
Replace one element with another. The profiler:
1. Finds `<old>` in the current TOML
2. Searches for `<new>`: `pss search "<new>" --top 5`
3. If found, shows `pss compare <old-id> <new-id>` to highlight differences
4. Replaces `<old>` with `<new>` in the same tier/section
5. Adds `<old>` to excluded with reason "Replaced by <new> (user directive)"
6. Re-validates

**`move <name> to <tier>`**
Move a skill between tiers. The profiler:
1. Finds `<name>` in current TOML skills
2. Removes from current tier
3. Adds to target tier (primary, secondary, or specialized)
4. Checks tier limits (warn if exceeded)
5. Re-validates

**`search <query>`**
Search the index without modifying the profile. The profiler:
1. Runs `pss search "<query>" --top 10`
2. Presents results in a compact table: name, type, score, description (truncated)
3. Asks if the user wants to include any of the results
4. Does NOT modify the TOML unless the user follows up with `include`

**`approve` / `done`**
Accept the current profile. The profiler:
1. Performs one final validation
2. Proceeds to Step 9 (cleanup and report)

---

## Search Integration

During interactive review, the profiler uses these PSS CLI commands to help the user find alternatives:

### Finding Alternatives

```bash
# Search by query (any type)
"${BINARY_PATH}" search "<query>" --top 10

# Search by query + type filter
"${BINARY_PATH}" search "<query>" --type skill --top 10
"${BINARY_PATH}" search "<query>" --type mcp --top 5
"${BINARY_PATH}" search "<query>" --type agent --top 5

# List all elements of a type
"${BINARY_PATH}" list --type mcp --top 20

# Check what's available for a language/framework
"${BINARY_PATH}" vocab frameworks --type skill
"${BINARY_PATH}" coverage --type skill
```

### Comparing Candidates

When the user wants to swap or is choosing between alternatives:

```bash
# Side-by-side comparison
"${BINARY_PATH}" compare <id1> <id2>

# Full metadata for a specific element
"${BINARY_PATH}" inspect <name-or-id> --format json
```

Present comparison results as a table showing: shared keywords, unique keywords, frameworks, languages, description snippets.

### Adding from Search Results

When search returns results and the user selects one:

1. Get the element's full metadata: `pss inspect <id>`
2. Determine the correct TOML section (skill → `[skills]`, agent → `[agents]`, etc.)
3. For skills: determine tier (ask user or default to secondary)
4. Add the element's name to the appropriate array
5. Re-validate

---

## Re-validation Loop

After EVERY directive that modifies the `.agent.toml`:

1. **Edit** the TOML file using the Edit tool (never rewrite from scratch)
2. **Re-validate** by running the validator:
   ```bash
   uv run "${CLAUDE_PLUGIN_ROOT}/scripts/pss_validate_agent_toml.py" "${OUTPUT_PATH}" --check-index --verbose
   ```
3. **If validation fails**: show the error to the user and suggest a fix
4. **If validation passes**: present the updated review summary
5. **Continue** accepting directives until the user types `approve` or `done`

---

## Completion Checklist

Before reporting success, ALL of these must be true:

- [ ] Self-review checks 1-5 all pass (name integrity, auto_skills, non-coding filter, coverage, exclusion quality)
- [ ] If `--interactive`: user typed `approve` or `done`
- [ ] If autonomous: self-review passed with ≤ 2 fix cycles
- [ ] Final validation (Step 8) returned exit code 0
- [ ] No self-review issues remain unfixed
- [ ] TOML file exists at `${OUTPUT_PATH}` and is non-empty
- [ ] Report includes self-review fix count (e.g., "self-review: 2 fixes applied")
- [ ] Report includes interactive changes count if applicable (e.g., "user changes: 3")
