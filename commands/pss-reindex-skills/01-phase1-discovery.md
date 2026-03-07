# Phase 1: Discovery + Keyword Analysis

## Step 1: Generate Element Checklist

Run the discovery script with `--checklist` and `--all-projects` to generate a markdown checklist with batches:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pss_discover.py --checklist --batch-size 10 --all-projects
```

This creates `~/.claude/cache/skill-checklist.md` with:
- All elements (skills, agents, commands, rules, MCP, LSP) organized into batches (default: 10 per batch)
- Checkbox format for tracking progress
- Agent assignment suggestions (Agent A, B, C, etc.)

Example output:
```
Checklist written to: ~/.claude/cache/skill-checklist.md
  350 elements in 35 batches
```

## Step 2: Divide Work Among Agents

The orchestrator reads the checklist and spawns sonnet subagents, one per batch:

```
Batch 1 (elements 1-10)   -> Agent A
Batch 2 (elements 11-20)  -> Agent B
Batch 3 (elements 21-30)  -> Agent C
...
Batch 22 (elements 211-216) -> Agent V
```

**Key Workflow:**
1. Orchestrator reads the checklist file
2. For each batch, spawn a sonnet subagent with:
   - The batch number and range
   - The list of element paths in that batch
   - Instructions to read each element and generate patterns
3. All subagents run in parallel (up to 20 concurrent)
4. Each subagent marks entries with [x] as complete
5. Orchestrator collects all results

## Step 3: Subagent Analysis

**IMPORTANT: MODEL SELECTION**
- Pass 1 agents MUST use `model: sonnet` (factual extraction only)
- Pass 2 agents MUST use `model: sonnet` (guided co-usage with decision gates)
- The orchestrator (you) runs on the parent model (Sonnet/Opus)

**IMPORTANT: PROMPT TEMPLATES**
The full Sonnet-optimized prompts are in external template files:
- **Pass 1**: Read `${CLAUDE_PLUGIN_ROOT}/prompts/pass1-sonnet.md` for the complete template
- **Pass 2**: Read `${CLAUDE_PLUGIN_ROOT}/prompts/pass2-sonnet.md` for the complete template

Read the appropriate template file, fill in the {variables}, and pass it to the sonnet subagent.

**IMPORTANT: TRIPLE VERIFICATION**
Both templates include mandatory triple-read verification steps where the agent re-reads the element file
2 additional times to cross-check its extraction results. This ensures high extraction accuracy.
Do NOT remove or skip these verification steps.

**IMPORTANT: AGENT REPORTING**
All agents must return ONLY a 1-2 line summary. No code blocks, no verbose output.
Format: `[DONE/PARTIAL/FAILED] Pass N Batch M - count/total elements processed`

**TOKEN BUDGET**: When sub-agents invoke PSS scripts, ALWAYS pass `--quiet` / `-q` to suppress per-element output. Only the final summary line is needed.

Each subagent receives the prompt built from the external template file.

**HOW TO BUILD THE PASS 1 PROMPT:**

1. Read the template file: `${CLAUDE_PLUGIN_ROOT}/prompts/pass1-sonnet.md`
2. Copy the content between `## TEMPLATE START` and `## TEMPLATE END`
3. Replace these variables:
   - `{batch_num}` -> the batch number (e.g., 3)
   - `{start}` -> first element number in batch (e.g., 21)
   - `{end}` -> last element number in batch (e.g., 30)
   - `{list_of_element_paths}` -> newline-separated list of element paths with source and name
4. Replace `${CLAUDE_PLUGIN_ROOT}` with the absolute path to the plugin directory
5. Send the filled template to the sonnet subagent

**CRITICAL**: The `${CLAUDE_PLUGIN_ROOT}` variable may NOT be available inside subagents.
You MUST resolve it to an absolute path BEFORE sending the prompt. Example:
```bash
# Resolve plugin root path first
PLUGIN_ROOT=$(cd "${CLAUDE_PLUGIN_ROOT}" && pwd)
# Then replace ${CLAUDE_PLUGIN_ROOT} with $PLUGIN_ROOT in the template
```

**BUILDING {element_tracking_rows} (MANDATORY):**

Both Pass 1 and Pass 2 templates include a `{element_tracking_rows}` variable for the batch tracking checklist.
You MUST build this from the batch's element list. Format:

```
| 1 | element-name-one | PENDING | NO |
| 2 | element-name-two | PENDING | NO |
| 3 | element-name-three | PENDING | NO |
```

Each row has: sequential number, element name, Status (initially PENDING), Merged (initially NO).
The agent will update this file as it processes each element.

## Step 4: Compile Index

Merge all subagent responses into the master index (rio v2.0 compatible format with PSS extensions).

See [04-index-schema.md](./04-index-schema.md) for the full index JSON schema and format documentation.

## Step 5: Pass 1 Index (Built Incrementally via Merge)

Pass 1 agents write temporary `.pss` files to `${PSS_TMPDIR}/pss-queue/` and immediately merge them into `~/.claude/cache/skill-index.json` via `pss_merge_queue.py`. No explicit "Save" step is needed -- the merge happens inline during Pass 1 processing.

The orchestrator should verify after all Pass 1 agents complete that `skill-index.json` exists and contains all discovered elements with `"pass": 1`.

```bash
mkdir -p ~/.claude/cache
```

**NOTE:** No staleness checks are performed. The index is a superset of all elements ever indexed.
At runtime, the agent filters suggestions against its known available elements (injected by Claude Code).
See `docs/PSS-ARCHITECTURE.md` for the full rationale.

---

## Step 5a: Validate Pass 1 Index (MANDATORY)

After ALL Pass 1 agents have completed, run the CPV plugin validator to ensure the index is structurally sound:

```bash
cd "${PLUGIN_ROOT}" && uv run --with pyyaml python3 scripts/validate_plugin.py . --verbose
```

**If validation FAILS (non-zero exit code):**
- The index has structural errors from Pass 1 agents
- Read the validator output to identify which elements have issues
- Re-run affected agents if the errors are recoverable
- If the errors are NOT recoverable: re-run ALL Pass 1 agents from scratch
- Do NOT proceed to Pass 2 until validation passes

**If validation PASSES (exit code 0):**
- Proceed to Step 5b

## Step 5b: Check Pass 1 Agent Tracking Files (MANDATORY)

The sonnet agents write per-batch tracking files to `${PSS_TMPDIR}/pss-queue/batch-*-pass1-tracking.md`.
The orchestrator MUST check these files to verify no elements were skipped:

```bash
# List all Pass 1 tracking files
ls ${PSS_TMPDIR}/pss-queue/batch-*-pass1-tracking.md

# For each tracking file, check for PENDING or FAILED elements
grep -E "PENDING|FAILED" ${PSS_TMPDIR}/pss-queue/batch-*-pass1-tracking.md
```

**If ANY element shows PENDING:**
- The agent forgot to process that element (possible with batch processing)
- Re-spawn a sonnet agent for JUST the missed elements
- The re-run agent should process ONLY the PENDING elements, not the entire batch

**If ANY element shows FAILED:**
- The agent tried but could not process that element
- Check if the element's definition file exists and is readable
- If the file exists, re-spawn an agent to retry (up to 2 retries)
- If the file does NOT exist, log a warning and skip it

**If ALL elements show DONE+YES:**
- Pass 1 is complete, proceed to Pass 2
