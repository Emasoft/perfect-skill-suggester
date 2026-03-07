# Phase 2: Co-Usage Correlation Workflow

## CRITICAL: Pass 1 to Pass 2 Workflow Transition

**ORCHESTRATOR INSTRUCTION (MANDATORY):**

When ALL Pass 1 batch agents have completed (all batches return results):

1. **Compile Pass 1 Index** - Merge all agent results into `~/.claude/cache/skill-index.json`
2. **Verify Pass 1 Success** - Confirm index contains all discovered elements with keywords and categories
3. **IMMEDIATELY PROCEED TO PASS 2** - Do NOT stop after Pass 1

**DO NOT WAIT FOR USER INPUT** between Pass 1 and Pass 2. The reindex command is a SINGLE operation that MUST complete both passes.

If the `--pass1-only` flag was specified, SKIP Pass 2 and stop after compiling the index.
If the `--pass2-only` flag was specified, SKIP Pass 1 and proceed directly to Pass 2.
Otherwise, ALWAYS execute Pass 2 immediately after Pass 1 completes.

---

**EXECUTE THIS SECTION IMMEDIATELY AFTER PASS 1 COMPLETES** (unless `--pass1-only` was specified).

## Step 6: Load CxC Category Matrix

Read the category-to-category co-usage probability matrix from:
`${CLAUDE_PLUGIN_ROOT}/schemas/pss-categories.json`

This provides heuristic guidance for candidate selection:
```json
{
  "co_usage_matrix": {
    "web-frontend": {
      "web-backend": 0.9,
      "testing": 0.8,
      "devops-cicd": 0.7
    }
  }
}
```

## Step 7: Spawn Pass 2 Agents (Parallel, Batched, Sonnet)

**MODEL**: Use `model: sonnet` for all Pass 2 agents.

**PROMPT TEMPLATE**: Read `${CLAUDE_PLUGIN_ROOT}/prompts/pass2-sonnet.md` for the complete template.
Fill in the {variables} and pass to each sonnet subagent.

**BATCHING (same as Pass 1):**
- Group elements into batches of 10
- Spawn up to 20 agents in parallel (all batches simultaneously, max 20 concurrent)
- Each agent processes ALL elements in its batch
- Wait for all batches to complete before proceeding to Step 8

**TRIPLE VERIFICATION**: The Pass 2 template includes 3 verification rounds where the agent
re-reads element data and re-validates each co-usage link. This ensures high extraction accuracy.

**MANDATORY BINARY CHECK (before spawning ANY Pass 2 agents):**

Pass 2 agents invoke the Rust binary in `--incomplete-mode` for candidate generation. If the binary is missing or not executable, ALL Pass 2 agents will fail. Verify first:

```bash
# Verify binary exists and is executable
if [ ! -f "${BINARY}" ]; then
    echo "[FAILED] PSS binary not found at: ${BINARY}"
    echo "Build with: cd ${PLUGIN_ROOT}/rust/skill-suggester && cargo build --release"
    # Attempt restore from backup before exiting
    exit 1
fi
if [ ! -x "${BINARY}" ]; then
    chmod +x "${BINARY}"
    echo "Fixed binary permissions: ${BINARY}"
fi
echo "Binary verified: ${BINARY}"
```

Do NOT spawn any Pass 2 agents if the binary check fails. This is a hard gate.

**HOW TO BUILD THE PASS 2 PROMPT:**

1. Read the template file: `${CLAUDE_PLUGIN_ROOT}/prompts/pass2-sonnet.md`
2. Copy the content between `## TEMPLATE START` and `## TEMPLATE END`
3. Replace these variables:
   - `{batch_num}` -> the batch number (e.g., 3)
   - `{start}` -> first element number in batch (e.g., 21)
   - `{end}` -> last element number in batch (e.g., 30)
   - `{list_of_element_names_and_pss_paths}` -> newline-separated list of element names
   - `{element_name}` -> each element name (template has per-element sections)
   - `{keywords_as_phrase}` -> element's keywords joined as a phrase
   - `{binary_path}` -> absolute path to the platform-specific Rust binary (see below)
4. Replace `${CLAUDE_PLUGIN_ROOT}` with the resolved absolute path to the plugin directory
5. Send the filled template to the sonnet subagent

**RESOLVING {binary_path} (platform detection):**
```bash
# Detect platform and select the correct binary
ARCH=$(uname -m)
OS=$(uname -s)
if [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then
    BINARY="${PLUGIN_ROOT}/rust/skill-suggester/bin/pss-darwin-arm64"
elif [ "$OS" = "Darwin" ] && [ "$ARCH" = "x86_64" ]; then
    BINARY="${PLUGIN_ROOT}/rust/skill-suggester/bin/pss-darwin-x86_64"
elif [ "$OS" = "Linux" ] && [ "$ARCH" = "x86_64" ]; then
    BINARY="${PLUGIN_ROOT}/rust/skill-suggester/bin/pss-linux-x86_64"
elif [ "$OS" = "Linux" ] && [ "$ARCH" = "aarch64" ]; then
    BINARY="${PLUGIN_ROOT}/rust/skill-suggester/bin/pss-linux-arm64"
fi
```

**CRITICAL**: Same as Pass 1 - resolve `${CLAUDE_PLUGIN_ROOT}` to an absolute path BEFORE sending to subagents.

## Step 8: Verify Pass 2 Results in Global Index

Pass 2 agents merge their results directly into skill-index.json via pss_merge_queue.py during processing. No separate merge step is needed. The orchestrator should verify the final index has `pass: 2` and all elements have co_usage data.

**Final Index Format (Pass 2 complete):** See [04-index-schema.md](./04-index-schema.md) for the complete schema.

**NOTE:** Category is REQUIRED and must be one of the 16 predefined categories. Keywords are specific multi-word phrases.

## Step 8a: Validate Final Index (MANDATORY)

After ALL Pass 2 agents have completed, run the CPV plugin validator to ensure the final index is sound:

```bash
cd "${PLUGIN_ROOT}" && uv run --with pyyaml python3 scripts/validate_plugin.py . --verbose
```

**What this does:**
- Validates plugin structure, manifest, and all element definitions (skills, agents, commands, rules, MCP, LSP)
- Checks for CRITICAL and MAJOR issues that would prevent the plugin from working

**If validation FAILS (non-zero exit code):**
- The reindex has FAILED - report to user
- If a backup exists (from Phase 0), manually restore it:
  ```bash
  BACKUP_DIR=$(cat ${PSS_TMPDIR}/pss-queue/backup-dir.txt)
  cp "$BACKUP_DIR/skill-index.json" ~/.claude/cache/skill-index.json
  ```
- Include the validator's error output in the report so the user can diagnose
- Clean up temporary `.pss` files: `rm -f ${PSS_TMPDIR}/pss-queue/*.pss`

**If validation PASSES (exit code 0):**
- Proceed to Step 8b

## Step 8b: Check Pass 2 Agent Tracking Files (MANDATORY)

Same procedure as Step 5b, but for Pass 2 tracking files:

```bash
# List all Pass 2 tracking files
ls ${PSS_TMPDIR}/pss-queue/batch-*-pass2-tracking.md

# For each tracking file, check for PENDING or FAILED elements
grep -E "PENDING|FAILED" ${PSS_TMPDIR}/pss-queue/batch-*-pass2-tracking.md
```

**If ANY element shows PENDING:**
- Re-spawn a sonnet agent for JUST the missed elements
- After the re-run completes, run the validator AGAIN (Step 8a)

**If ANY element shows FAILED:**
- Check if the element exists in the Pass 1 index
- If yes, re-spawn an agent to retry (up to 2 retries)
- After retries complete, run the validator AGAIN (Step 8a)

**If ALL elements show DONE+YES:**
- Proceed to the COMPLETION CHECKPOINT

## Step 8c: Final Cleanup

After validation passes, clean up temporary files:

```bash
# Remove tracking files (no longer needed)
rm -f ${PSS_TMPDIR}/pss-queue/batch-*-tracking.md

# Remove backup-dir pointer
rm -f ${PSS_TMPDIR}/pss-queue/backup-dir.txt

# Comprehensive .pss cleanup: element dirs + ${PSS_TMPDIR}/pss-queue/ (replaces simple rm -f)
python3 "${PLUGIN_ROOT}/scripts/pss_cleanup.py" --all-projects --verbose
```

**NOTE:** The backup directory in `${PSS_TMPDIR}/pss-backup-*` is intentionally NOT deleted.
It persists until the system clears the temp directory or the user manually removes it.
This provides a safety net if issues are discovered later.

## Step 8d: Aggregate Domain Gates into Domain Registry (MANDATORY)

After validation passes, aggregate all domain gates from the index into a normalized domain registry.
This registry enables the suggester to perform two-phase matching:
1. Detect which domains are relevant to the user prompt (using example keywords from the registry)
2. Check each element's domain gates against detected domains (boolean pass/fail)

```bash
python3 "${PLUGIN_ROOT}/scripts/pss_aggregate_domains.py" --verbose
```

**What this does:**
- Reads all `domain_gates` from every element in `~/.claude/cache/skill-index.json`
- Normalizes similar gate names to canonical forms (e.g., `input_language`, `language_input`, `input_lang` -> `input_language`)
- Aggregates all keywords found across skills for each canonical domain
- Detects which domains have the `generic` wildcard keyword
- Writes the registry to `~/.claude/cache/domain-registry.json`

**If the aggregation FAILS (exit code 1):**
- The domain registry was NOT written
- This does NOT invalidate the element index -- the index is still usable
- Report the error to the user but do NOT fail the entire reindex

**If the aggregation SUCCEEDS (exit code 0):**
- Proceed to the COMPLETION CHECKPOINT
