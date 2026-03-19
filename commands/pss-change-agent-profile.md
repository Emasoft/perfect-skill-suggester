---
name: pss-change-agent-profile
description: "Modify an existing .agent.toml profile with natural language instructions"
argument-hint: "<profile-path> <change-instructions> [--requirements PATH...]"
allowed-tools: ["Task", "Read", "Write", "Edit", "Bash", "Glob", "Grep", "mcp__plugin_llm-externalizer_llm-externalizer__batch_check", "mcp__plugin_llm-externalizer_llm-externalizer__code_task", "mcp__plugin_llm-externalizer_llm-externalizer__chat"]
---

# PSS Change Agent Profile

Modify an existing `.agent.toml` profile based on natural language instructions. The profiler agent reads the current profile, applies the requested changes, verifies all element names against the skill index, re-validates, and writes the updated file.

Optionally, a `--requirements` document can be provided to re-align the profile with project requirements using the `pss-design-alignment` skill (two-pass scoring with specialization-aware cherry-picking).

## Usage

```
/pss-change-agent-profile /path/to/agent.agent.toml remove all skills using tldr tool
/pss-change-agent-profile /path/to/agent.agent.toml add a subagent to handle github projects
/pss-change-agent-profile /path/to/agent.agent.toml move skill-x from secondary to primary
/pss-change-agent-profile /path/to/agent.agent.toml replace jest-testing with vitest
/pss-change-agent-profile /path/to/agent.agent.toml add websocket-handler to primary skills
/pss-change-agent-profile /path/to/agent.agent.toml exclude all python-specific skills
/pss-change-agent-profile /path/to/agent.agent.toml --requirements docs/prd.md align with project requirements
```

## Argument Parsing

1. **Profile path** (required, first positional argument):
   - Path to an existing `.agent.toml` file
   - If the file doesn't exist → error

2. **`--requirements PATH...`** (optional, one or more paths):
   - Design/requirements document(s) describing the project
   - When provided: runs the `pss-design-alignment` skill's two-pass scoring (requirements-only scoring + specialization-aware cherry-pick), then merges into the existing profile
   - Elements cherry-picked from requirements go to secondary/specialized tier only

3. **Change instructions** (required, remaining arguments after flags):
   - Free-form natural language describing the changes to make
   - Supports: add, remove, replace/swap, move between tiers, exclude with reason
   - Multiple changes can be described in one instruction
   - If `--requirements` is provided without change instructions, defaults to "align with project requirements"

## Execution

### Step 1: Resolve Environment

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
if [ -z "$PLUGIN_ROOT" ]; then
  echo "ERROR: CLAUDE_PLUGIN_ROOT not set"
  exit 1
fi
```

Detect platform binary:
```bash
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$ARCH" in x86_64) ARCH="x86_64" ;; arm64|aarch64) ARCH="arm64" ;; esac
BINARY_PATH="${PLUGIN_ROOT}/bin/pss-${OS}-${ARCH}"
```

Set paths:
```bash
INDEX_PATH="${HOME}/.claude/cache/skill-index.json"
VERIFY_SCRIPT="${PLUGIN_ROOT}/scripts/pss_verify_profile.py"
VALIDATE_SCRIPT="${PLUGIN_ROOT}/scripts/pss_validate_agent_toml.py"
```

### Step 2: Read Current Profile

Read the `.agent.toml` file. Extract:
- Agent name and path to the original `.md` definition
- Current skills (primary, secondary, specialized, excluded)
- Current agents, commands, rules, MCP, LSP, hooks
- Dependencies

If the `.agent.toml` has `[agent].path`, also read the original agent `.md` file for context.

### Step 3: Parse Change Instructions

Analyze the natural language instructions and determine the operations:

| Pattern | Operation |
|---------|-----------|
| "add X", "include X" | Add element to appropriate section |
| "remove X", "delete X", "drop X" | Remove element from profile |
| "replace X with Y", "swap X for Y" | Remove X, add Y |
| "move X to primary/secondary/specialized" | Change skill tier |
| "exclude X", "exclude all X-related" | Remove + add to excluded |
| "add subagent for X", "add agent for X" | Search index for matching agent, add to [agents] |
| "add rule for X" | Search index for matching rule, add to [rules] |
| "add MCP for X" | Search index for matching MCP server, add to [mcp] |

### Step 4: Search and Resolve Elements

For each operation that adds a new element:

1. Search the index: `"${BINARY_PATH}" search "<query>" --type <type> --top 10`
2. Pick the best match based on the user's description
3. Verify the element exists: `"${BINARY_PATH}" inspect <name> --format json`

For removal operations, verify the element is actually in the profile before removing.

### Step 4b: Requirements Alignment (when `--requirements` is provided)

If requirements documents were provided, run the `pss-design-alignment` skill:

1. **Score requirements**: Build a requirements-only descriptor, invoke the Rust binary (see `pss-design-alignment` scoring protocol)
2. **Cherry-pick by specialization**: For each requirements candidate, evaluate domain overlap, duty matching, and practical usage against this agent's role (see `pss-design-alignment` specialization filter)
3. **Merge**: Add cherry-picked elements to secondary/specialized tiers (see `pss-design-alignment` merge protocol)
4. **Document rejections**: Add rejected requirements candidates to `[skills.excluded]`

### Step 5: Apply Changes

Modify the TOML data structure:
- Add/remove elements from the appropriate arrays
- Apply requirements cherry-picks (if Step 4b was run)
- Update `[skills.excluded]` with reasons for removals
- Maintain TOML formatting and comments

### Step 6: Verify and Validate

Run both verification and validation:

```bash
# Verify all element names against the index (--agent-def enables agent-defined name detection)
uv run "${VERIFY_SCRIPT}" "${PROFILE_PATH}" --agent-def "${AGENT_PATH}" --verbose

# Validate TOML structure
uv run "${VALIDATE_SCRIPT}" "${PROFILE_PATH}" --check-index --verbose
```

If either fails, fix the issues and retry (max 2 cycles).

**Token-efficient post-change verification**: If `mcp__plugin_llm-externalizer_llm-externalizer__code_task` is available, use it to verify the changes without re-reading both files into context:
```
mcp__plugin_llm-externalizer_llm-externalizer__code_task(
  instructions: "Verify this .agent.toml was correctly modified. Check: (1) TOML syntax valid, (2) no duplicate elements across tiers, (3) no empty names, (4) excluded entries have reasons. List any issues found.",
  input_files_paths: "<PROFILE_PATH>",
  max_tokens: 500,
  ensemble: false
)
```

### Step 7: Report

Output: `[DONE] pss-change-agent-profile - <agent-name>: <summary of changes>. Output: <profile-path>`

## Error Handling

- Profile not found: `ERROR: Profile not found: <path>`
- No changes understood: `ERROR: Could not parse change instructions. Examples: "add skill-x", "remove agent-y", "move skill-z to primary"`
- Element not found in index: `WARNING: '<name>' not found in index. Searching for alternatives...`
- Validation fails after changes: Fix and retry, report failure after 3 attempts
