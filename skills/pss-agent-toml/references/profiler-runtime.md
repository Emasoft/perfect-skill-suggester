# Profiler Runtime: Inputs, Debug, Steps 0-3b, Step 9, Change Mode, Errors

Runtime contract for the `pss-agent-profiler` agent. Steps 4-6f live in
[profiler-postfilter.md](profiler-postfilter.md); Steps 7-8b live in
[profiler-toml-and-validation.md](profiler-toml-and-validation.md).

## Table of Contents

- [Inputs Contract](#inputs-contract)
- [Debug Output Protocol](#debug-output-protocol)
- [Step 0: Index Rule Files](#step-0-index-rule-files)
- [Step 1: Read and Analyze the Agent](#step-1-read-and-analyze-the-agent)
- [Step 2: Read Requirements Documents](#step-2-read-requirements-documents)
- [Step 3a: Pass 1 — Agent-Only Descriptor](#step-3a-pass-1--agent-only-descriptor)
- [Step 3b: Pass 2 — Requirements-Only Descriptor](#step-3b-pass-2--requirements-only-descriptor)
- [Step 9: Clean Up and Report](#step-9-clean-up-and-report)
- [Invocation Examples](#invocation-examples)
- [Change Mode](#change-mode)
- [Error Handling (Fail-Fast)](#error-handling-fail-fast)

## Inputs Contract

The command passes these to the profiler:

- `AGENT_PATH` — absolute path to the `<agent-name>.md` file
- `REQUIREMENTS_PATHS` — list of absolute paths to design/requirements files (may be empty)
- `INDEX_PATH` — absolute path to skill-index.json (usually `~/.claude/cache/skill-index.json`)
- `BINARY_PATH` — absolute path to the platform-specific Rust binary
- `OUTPUT_PATH` — absolute path where the .agent.toml should be written
- `INTERACTIVE` — whether interactive review mode is enabled (true/false)
- `INCLUDE_ELEMENTS` — list of element names to force-include (may be empty)
- `EXCLUDE_ELEMENTS` — list of element names to force-exclude (may be empty)
- `MAX_PRIMARY` — override for primary tier limit (default: 7)
- `MAX_SECONDARY` — override for secondary tier limit (default: 12)
- `MAX_SPECIALIZED` — override for specialized tier limit (default: 8)
- `DOMAIN_CONSTRAINTS` — list of allowed domains (empty = no constraint)
- `LANGUAGE_CONSTRAINTS` — list of allowed languages (empty = no constraint)
- `PLATFORM_CONSTRAINTS` — list of allowed platforms (empty = no constraint)

## Debug Output Protocol

When running under `claude --debug`, emit verbose status messages at each phase
boundary. Use `stderr` (print to console) — it does not affect the orchestrator's
token budget.

**Format**: `[PSS-PROFILER] Step <N>: <status> — <details>`

Example debug trace:
```
[PSS-PROFILER] Step 1: Reading agent definition — /path/to/agent.md
[PSS-PROFILER] Step 1: Extracted: name=my-agent, role=developer, writes_code=true, auto_skills=3, sub_agents=5
[PSS-PROFILER] Step 2: Reading 2 requirements files
[PSS-PROFILER] Step 2: Detected tech_stack=[typescript, react, postgresql], project_type=web-app
[PSS-PROFILER] Step 3a: Pass 1 — agent-only scoring (no requirements in descriptor)
[PSS-PROFILER] Step 3a: Binary returned 24 agent candidates: skills=15, agents=3, commands=3, rules=2, mcp=1
[PSS-PROFILER] Step 3b: Pass 2 — requirements-only scoring (project-level candidates)
[PSS-PROFILER] Step 3b: Binary returned 28 project candidates: skills=18, agents=4, commands=3, rules=2, mcp=1
[PSS-PROFILER] Step 4a: Mutual exclusivity — removed vue-frontend (conflicts with react)
[PSS-PROFILER] Step 4b: Obsolescence — removed moment-js (superseded by date-fns)
[PSS-PROFILER] Step 4c: Stack filter — removed 3 python-only skills
[PSS-PROFILER] Step 4f: Force-include: websocket-handler; Force-exclude: jest-testing
[PSS-PROFILER] Step 4g: Cherry-pick from requirements — 5 elements match agent specialization, 12 rejected
[PSS-PROFILER] Step 5: Classified — P=6 S=10 Sp=4 excluded=8
[PSS-PROFILER] Step 7: Writing .agent.toml to /output/path.agent.toml
[PSS-PROFILER] Step 8: Validation PASSED (exit code 0)
[PSS-PROFILER] Step 8a: Verification — 22 verified, 8 agent-defined, 0 not-found, 0 violations
[PSS-PROFILER] Step 8b-i: Self-review — 5/5 checks passed, 0 fixes needed
[PSS-PROFILER] Step 8b-ii: Interactive review — SKIPPED (autonomous mode)
[PSS-PROFILER] Step 9: Done — P=6 S=10 Sp=4 excluded=8
```

To check if debug mode is active, test whether the `CLAUDE_DEBUG` environment
variable is set. If not set, suppress all `[PSS-PROFILER]` messages.

## Step 0: Index Rule Files

Before profiling, ensure rule files are indexed in the DB so Step 6c has a
complete catalogue:

```bash
"${BINARY_PATH}" index-rules --project-root "$(pwd)" --format json
```

This scans `~/.claude/rules/*.md` (user-level) and `.claude/rules/*.md`
(project-level), extracts names and descriptions, and stores them in a separate
`rules` table. It's fast (filesystem scan, no AI), idempotent (re-running updates
existing entries), and only needs to happen once per profiling session.

## Step 1: Read and Analyze the Agent

Read the `<agent-name>.md` file completely. Extract:

- **name**: The agent's name (from filename or content header)
- **description**: What the agent does (from first paragraph or description field)
- **role**: The agent's primary role (developer, tester, reviewer, deployer, orchestrator, etc.)
- **agent_type**: From frontmatter `type:` field (e.g., "orchestrator", "specialist", "worker")
- **domain**: The agent's domain (security, frontend, backend, devops, data, etc.)
- **tools**: Tools the agent uses (from allowed-tools or tool mentions in the content)
- **duties**: What the agent is responsible for (from bullet points, task descriptions, headers)
- **auto_skills**: From frontmatter `auto_skills:` list — these are AUTHOR-DECLARED required skills
- **sub_agents**: From routing tables, delegation sections — agents this agent delegates to
- **examples**: Example use cases or trigger phrases mentioned in the file
- **trigger_patterns**: Phrases that would invoke this agent
- **writes_code**: Does this agent write/edit/analyze code directly, or only orchestrate?
- **effort**: From frontmatter `effort:` field (low/medium/high) — controls reasoning depth (CC v2.1.78+)
- **maxTurns**: From frontmatter `maxTurns:` field — max agentic turns before stopping (CC v2.1.78+)
- **disallowedTools**: From frontmatter `disallowedTools:` list — tools the agent must NOT use (CC v2.1.78+)

**CRITICAL — Name Preservation Rule**: The agent definition may reference skills,
sub-agents, and commands from its OWN plugin (not installed locally). These names
MUST be preserved EXACTLY as written in the agent definition, even if they don't
exist in the local skill index. NEVER rename, re-prefix, or "correct" names from
the agent definition to match locally installed elements. For example, if the agent
references `amia-code-reviewer`, do NOT change it to `eia-code-reviewer` or any
other prefix — use `amia-code-reviewer` exactly.

**CRITICAL — Auto-Skills Pinning Rule**: Any skill listed in the frontmatter
`auto_skills:` field is an AUTHOR-DECLARED requirement. These skills MUST always
appear in `[skills].primary` — they may NEVER be demoted to secondary or
specialized, regardless of scoring. The agent's author explicitly chose these
skills; the profiler has no authority to override that decision.

## Step 2: Read Requirements Documents

If `REQUIREMENTS_PATHS` is non-empty, read ALL requirements files. Extract and
store these SEPARATELY from the agent info (they are used in a separate scoring
pass):

- **project_type**: What is being built (web app, mobile app, CLI tool, library, etc.)
- **tech_stack**: Specific technologies, frameworks, languages mentioned
- **apis_and_services**: External APIs, databases, cloud services referenced
- **key_features**: Core features the project must implement
- **constraints**: Performance requirements, platform targets, compliance needs
- **domain_specifics**: Industry-specific terminology (fintech, healthcare, media, etc.)

**DO NOT** merge requirements into the agent descriptor. The requirements are
scored separately in Step 3b (using the `pss-design-alignment` skill's scoring
protocol) to produce project-level candidates, which are then cherry-picked based
on agent specialization in Step 4g (using the `pss-design-alignment` skill's
specialization filter).

## Step 3a: Pass 1 — Agent-Only Descriptor

This pass scores candidates based on the agent definition ALONE — its role,
duties, tools, domains, and auto_skills. No requirements content is included.
This produces the **baseline agent profile**.

Determine the system temp directory and create session-unique temp file paths:

```bash
PSS_TMPDIR=$(uv run python3 -c "import tempfile; print(tempfile.gettempdir())")
PSS_AGENT_INPUT="${PSS_TMPDIR}/pss-agent-profile-input-$$.json"
PSS_REQS_INPUT="${PSS_TMPDIR}/pss-reqs-profile-input-$$.json"
```

```json
{
  "name": "<agent-name>",
  "description": "<agent description from the .md file ONLY>",
  "role": "<agent role>",
  "duties": ["<duty1>", "<duty2>", ...],
  "tools": ["<tool1>", "<tool2>", ...],
  "domains": ["<domain1>", "<domain2>", ...],
  "requirements_summary": "",
  "cwd": "<current working directory>"
}
```

Invoke the Rust binary:

```bash
"${BINARY_PATH}" --agent-profile "${PSS_AGENT_INPUT}" --format json --top 30
```

Save the output as `PSS_AGENT_CANDIDATES`. These are the **baseline candidates**
derived from the agent's own definition.

## Step 3b: Pass 2 — Requirements-Only Descriptor

**Skip this step if `REQUIREMENTS_PATHS` is empty.** Only run when
design/requirements documents were provided.

**This step follows the `pss-design-alignment` skill's
[Scoring Protocol](../../pss-design-alignment/references/scoring-protocol.md):**
- Requirements Descriptor Format
- Binary Invocation
- Output Format
- Scoring Checklist

This pass scores candidates based on the requirements document ALONE. It produces
**project-level candidates** — everything the project needs, regardless of which
agent handles what.

Write the requirements-only descriptor to a DIFFERENT temp file
(`${PSS_REQS_INPUT}`):

```json
{
  "name": "<project-name or 'project-requirements'>",
  "description": "<condensed summary of all requirements files>",
  "role": "project",
  "duties": ["<key_feature1>", "<key_feature2>", ...],
  "tools": [],
  "domains": ["<domain1>", "<domain2>", ...],
  "requirements_summary": "<full requirements summary — MAX 2000 characters>",
  "cwd": "<current working directory>"
}
```

Invoke the Rust binary:

```bash
"${BINARY_PATH}" --agent-profile "${PSS_REQS_INPUT}" --format json --top 30
```

Save the output as `PSS_REQS_CANDIDATES`. These are **project-level candidates** —
NOT yet filtered for this specific agent.

**CRITICAL**: The requirements candidates file uses a DIFFERENT filename
(`pss-reqs-profile-input-$$.json`) to avoid overwriting the agent candidates from
Step 3a.

The binary returns results grouped by type in both passes:
- `skills` — tiered skill/agent recommendations (primary, secondary, specialized)
- `complementary_agents` — agents that work well alongside
- `commands` — recommended slash commands
- `rules` — recommended rules
- `mcp` — recommended MCP servers
- `lsp` — recommended LSP servers

**After both passes**, you have TWO candidate pools:
1. `PSS_AGENT_CANDIDATES` — derived from the agent's own role/duties/tools (baseline)
2. `PSS_REQS_CANDIDATES` — derived from the project requirements document (project-level)

The agent candidates (Pass 1) form the core of the profile. The requirements
candidates (Pass 2) are cherry-picked in Step 4g based on the agent's
specialization.

## Step 9: Clean Up and Report

- Delete the temporary `${PSS_AGENT_INPUT}` file (agent-only descriptor from Step 3a)
- Delete the temporary `${PSS_REQS_INPUT}` file if it exists (requirements descriptor from Step 3b)
- **TOKEN BUDGET RULE**: Return ONLY a 1-2 line summary to the orchestrator. NEVER
  return verbose text, code blocks, TOML contents, candidate lists, or detailed
  reasoning. Write any detailed report to a file instead.
- Output format: `[DONE] pss-agent-profiler - <agent-name>: P=<n> S=<n> Sp=<n> excluded=<n> review-fixes=<n> user-changes=<n>. Output: <OUTPUT_PATH>`
- If failed: `[FAILED] pss-agent-profiler - <error summary>`

**Step 9 Completion Checklist** (MANDATORY before reporting DONE):

- [ ] Structural validator returned exit code 0 (Step 8)
- [ ] Element verifier returned exit code 0 — no hallucinations, no pinning/coding/restriction violations (Step 8a)
- [ ] Temporary agent input file `${PSS_AGENT_INPUT}` deleted
- [ ] Temporary requirements input file `${PSS_REQS_INPUT}` deleted (if Pass 2 was run)
- [ ] Output file exists at `${OUTPUT_PATH}` and is non-empty
- [ ] Summary includes: primary count (P), secondary count (S), specialized count (Sp), excluded count
- [ ] No validation or verification errors remain
- [ ] Self-review passed (all 5 checks green, or issues fixed within 2 cycles)
- [ ] If `--interactive`: user explicitly typed `approve` or `done`
- [ ] Response to orchestrator is MAX 2 lines — no verbose output

## Invocation Examples

<example>
Context: User wants to profile a new code review agent
user: "/pss-setup-agent agents/code-reviewer.md"
assistant: "I'll use the pss-agent-profiler agent to analyze the code-reviewer definition and generate a .agent.toml profile."
<commentary>
The user wants to create a configuration profile for their code review agent. The profiler will read the agent definition, invoke the Rust binary for candidate scoring, apply AI post-filtering (mutual exclusivity, stack compatibility, redundancy pruning), and write a validated .agent.toml file.
</commentary>
</example>

<example>
Context: User wants to profile an agent with project requirements
user: "/pss-setup-agent agents/backend-architect.md --requirements docs/prd.md docs/tech-spec.md"
assistant: "I'll use the pss-agent-profiler agent to analyze the backend-architect definition alongside the project requirements."
<commentary>
The user provides requirements documents. The profiler uses two-pass scoring: Pass 1 scores the agent definition alone (baseline profile), Pass 2 scores the requirements document alone (project-level candidates), then cherry-picks from Pass 2 only the elements matching the backend-architect's specialization (e.g., API design, database, infrastructure — not frontend or mobile).
</commentary>
</example>

## Change Mode

When invoked with `MODE=change`, the profiler modifies an existing `.agent.toml`
instead of creating one from scratch. The change command
(`/pss-change-agent-profile`) passes:

- `MODE=change` — activates this mode
- `PROFILE_PATH` — path to the existing `.agent.toml`
- `AGENT_PATH` — path to the agent `.md` (extracted from `[agent].path` in the TOML)
- `CHANGE_INSTRUCTIONS` — natural language describing what to change
- `REQUIREMENTS_PATHS` — optional design documents for re-alignment
- `BINARY_PATH`, `INDEX_PATH` — same as create mode

**Change mode workflow:**

1. **Read current profile**: Load the `.agent.toml` and extract all sections
2. **Read agent definition**: Load the `.md` for context (role, duties, domains)
3. **Parse instructions**: Interpret the natural language change request (add/remove/swap/move/exclude)
4. **Search and resolve**: For add operations, search the index via `"${BINARY_PATH}" search` to find matching elements
5. **Requirements alignment** (if `REQUIREMENTS_PATHS` provided): Run the `pss-design-alignment` skill — score requirements separately (Pass 2), cherry-pick by agent specialization, merge into profile
6. **Apply changes**: Edit the TOML data structure
7. **Verify (Step 8a)**: Run `pss_verify_profile.py` with `--agent-def`
8. **Validate (Step 8)**: Run `pss_validate_agent_toml.py` with `--check-index`
9. **Report**: Same format as create mode

All verification, validation, and anti-hallucination checks from create mode apply
equally to change mode.

## Error Handling (Fail-Fast)

Every error is fatal. Do NOT attempt workarounds, bypasses, or simplified
alternatives. Either the pipeline works correctly end-to-end, or it fails with a
clear error.

- If `<agent-name>.md` doesn't exist → `[FAILED] Agent file not found: <path>` — EXIT
- If any requirements file doesn't exist → `[FAILED] Requirements file not found: <path>` — EXIT
- If skill-index.json doesn't exist → `[FAILED] Skill index not found. Run /pss-reindex-skills first.` — EXIT
- If Rust binary doesn't exist → `[FAILED] PSS binary not found for this platform. Run cargo build.` — EXIT
- If Rust binary exits non-zero → `[FAILED] PSS binary error: <stderr output>` — EXIT
- If Rust binary returns invalid JSON → `[FAILED] PSS binary returned unparseable output` — EXIT
- If output directory can't be created → `[FAILED] Cannot create output directory: <path>` — EXIT
- If a candidate skill's SKILL.md cannot be read → skip that single candidate, note in report (non-fatal)
- If validation fails after 3 attempts → `[FAILED] TOML validation failed: <validator errors>` — EXIT
