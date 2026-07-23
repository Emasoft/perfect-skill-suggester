# Profiler AI Post-Filtering and Element Selection (Steps 4-6f)

The Rust binary produces raw candidates. Steps 4a-4g are the profiler's critical
value-add: filtering only an AI can do. Steps 5-6f turn survivors into the
tiered element sections of the `.agent.toml`.

## Table of Contents

- [Entry IDs and CLI Tools](#entry-ids-and-cli-tools)
- [Token-Efficient Candidate Evaluation (LLM Externalizer)](#token-efficient-candidate-evaluation-llm-externalizer)
- [4a. Mutual Exclusivity Detection](#4a-mutual-exclusivity-detection)
- [4b. Obsolescence and Deprecation Check](#4b-obsolescence-and-deprecation-check)
- [4c. Stack Compatibility and Constraint Filtering](#4c-stack-compatibility-and-constraint-filtering)
- [4c-bis. Non-Coding Agent Filter](#4c-bis-non-coding-agent-filter)
- [4d. Requirements-Driven Promotion](#4d-requirements-driven-promotion)
- [4e. Redundancy Pruning](#4e-redundancy-pruning)
- [4f. Force-Include/Exclude Directives](#4f-force-includeexclude-directives)
- [4g. Specialization-Aware Cherry-Pick](#4g-specialization-aware-cherry-pick)
- [Step 5: Classify into Final Tiers](#step-5-classify-into-final-tiers)
- [Step 6: Identify Complementary Agents](#step-6-identify-complementary-agents)
- [Step 6a: Review and Confirm Tier Assignments](#step-6a-review-and-confirm-tier-assignments)
- [Step 6b: Recommended Commands](#step-6b-recommended-commands)
- [Step 6c: Recommended Rules](#step-6c-recommended-rules)
- [Step 6d: Recommended MCP Servers](#step-6d-recommended-mcp-servers)
- [Step 6e: LSP Servers (Language-Based)](#step-6e-lsp-servers-language-based)
- [Step 6f: Recommended Hooks](#step-6f-recommended-hooks)

## Entry IDs and CLI Tools

**IMPORTANT — Use Entry IDs**: Every element has a unique 13-character ID
(base36). Names collide frequently (11 "setup" entries, 5 "debug" entries). Always
use the 13-char ID when inspecting, comparing, or resolving entries. Use
`"${BINARY_PATH}" inspect <id>` to get full details and
`"${BINARY_PATH}" resolve <id>` to get the file path for reading the actual
content.

```bash
# Inspect a candidate's full metadata
"${BINARY_PATH}" inspect <13-char-id> --format json

# Compare two competing candidates (shared/unique keywords, frameworks, etc.)
"${BINARY_PATH}" compare <id1> <id2> --format json

# Get file paths to read actual SKILL.md content for final decision
"${BINARY_PATH}" resolve <id1> <id2> <id3>

# Search for additional candidates not in binary output
"${BINARY_PATH}" search "websocket" --type skill --language typescript

# Check coverage gaps
"${BINARY_PATH}" coverage --type skill
"${BINARY_PATH}" vocab languages --type skill
```

## Token-Efficient Candidate Evaluation (LLM Externalizer)

When the `mcp__plugin_llm-externalizer_llm-externalizer__chat` tool is available,
use it with `answer_mode=0` and `max_retries=3` instead of reading every SKILL.md
into your context. This saves thousands of tokens when evaluating 20-30+
candidates.

**Batch evaluation workflow:**

1. Resolve all candidate file paths: `"${BINARY_PATH}" resolve <id1> <id2> ... <idN>`
2. Build the evaluation instructions with the agent's tech stack, role, and domains
3. Call `chat` with per-file mode (`answer_mode=0`) for parallel evaluation with retry:
   ```
   mcp__plugin_llm-externalizer_llm-externalizer__chat(
     instructions: "Evaluate this skill/agent/command for an agent with role=<role>, domains=<domains>, tech_stack=<stack>. Answer these questions:
     1. MUTUAL_EXCLUSIVITY: Does it conflict with any of these frameworks/tools: <list>? (yes/no + which)
     2. OBSOLETE: Is it deprecated or superseded in 2026? (yes/no + by what)
     3. STACK_COMPATIBLE: Is it compatible with <languages/frameworks>? (yes/no)
     4. REDUNDANT_WITH: Is it a strict subset of any of these candidates: <list>? (yes/no + which)
     5. RELEVANCE: Rate 1-5 how relevant this is to the agent's duties: <duties>
     Format: one line per question, e.g. 'MUTUAL_EXCLUSIVITY: no'",
     input_files_paths: [<list of SKILL.md paths>],
     answer_mode: 0,
     max_retries: 3
   )
   ```
4. Read the output file(s) to get per-candidate evaluations
5. Use the evaluations to drive the filtering decisions below

**Fallback**: If the LLM Externalizer MCP is unavailable, read each SKILL.md
directly. Prioritize reading only the top-15 candidates by score to stay within
context budget.

## 4a. Mutual Exclusivity Detection

**NOTE**: The Rust binary already applies 25+ predefined conflict groups
(React/Vue/Angular, Jest/Vitest/Mocha, Prisma/TypeORM/Drizzle, etc.) and keeps
only the highest-scoring member per group. You do NOT need to re-check those.
Focus on conflicts the Rust binary CANNOT detect:

- **Same-purpose custom skills** from different plugins doing the same thing (Rust doesn't know skill semantics)
- **Implicit conflicts** where skills aren't in the same named group but conflict in practice (e.g., two different CI/CD pipeline skills)
- **Requirements-driven selection**: when the requirements specify a particular technology, verify the binary chose correctly

When you detect mutually exclusive candidates beyond the Rust pre-filter, KEEP the
one that best matches the requirements. If no requirements are provided, keep the
one with the higher score and note the alternatives in a TOML comment.

## 4b. Obsolescence and Deprecation Check

Flag and REMOVE skills that:
- Reference deprecated APIs, libraries, or patterns (e.g., componentWillMount, var instead of const/let)
- Target end-of-life runtimes or platforms
- Have been superseded by a better candidate already in the list

If unsure whether something is obsolete, use WebSearch to verify. For example:
- "Is library X deprecated in 2026?"
- "What replaced framework Y?"

## 4c. Stack Compatibility and Constraint Filtering

Verify each candidate is compatible with the project's actual stack:
- A Python-only skill should not be recommended for a TypeScript agent (unless polyglot)
- An iOS-specific skill should not be recommended for a web-only project
- A React skill should not be recommended if the requirements specify Vue
- A skill requiring a specific cloud provider should match the requirements

**Constraint Filtering** (if `DOMAIN_CONSTRAINTS`, `LANGUAGE_CONSTRAINTS`, or
`PLATFORM_CONSTRAINTS` are provided):
- Remove candidates whose domain doesn't match any in `DOMAIN_CONSTRAINTS`
- Remove candidates whose language doesn't match any in `LANGUAGE_CONSTRAINTS`
- Remove candidates whose platform doesn't match any in `PLATFORM_CONSTRAINTS`
- Language-agnostic or domain-agnostic candidates pass through (empty field = compatible with all)

## 4c-bis. Non-Coding Agent Filter

**NOTE**: The Rust binary already detects orchestrators (from
role/description/frontmatter `type`) and removes LSP, linting, code-fixing, and
test-writing entries. Verify the binary's detection was correct — if you disagree
with `is_orchestrator`, manually adjust:

- **KEEP** code review skills (the agent may review code without writing it)
- **KEEP** quality gate skills (CI/CD, testing standards, coverage thresholds)
- **KEEP** architecture/design skills (the agent may make architectural decisions)

## 4d. Requirements-Driven Promotion

If requirements mention specific needs not covered by high-scoring candidates, use
`pss search` to find relevant skills:

```bash
"${BINARY_PATH}" search "websocket" --type skill       # Requirements mention "real-time"
"${BINARY_PATH}" search "i18n" --type skill            # Requirements mention internationalization
"${BINARY_PATH}" search "compliance" --type skill --category security  # HIPAA/PCI needs
"${BINARY_PATH}" search "pdf" --type skill             # PDF generation needs
"${BINARY_PATH}" search "accessibility" --type skill   # WCAG/a11y needs
```

Also check coverage gaps: `"${BINARY_PATH}" coverage --type skill` shows what
languages/frameworks are covered.

## 4e. Redundancy Pruning

Remove skills that are strict subsets of other recommended skills. If skill A
covers everything skill B does plus more, remove skill B.

## 4f. Force-Include/Exclude Directives

If `INCLUDE_ELEMENTS` is non-empty:
- For each name in the list, search the index: `"${BINARY_PATH}" search "<name>" --top 5`
- Add found elements to the candidate pool (skip if already present)
- Force-included elements go to primary tier by default (user can move them via interactive review)

If `EXCLUDE_ELEMENTS` is non-empty:
- Remove every matching element from all candidate pools
- Add to `[skills.excluded]` with reason "Excluded by user directive"
- Force-exclusions cannot be overridden by scoring or auto_skills (but user can re-include via interactive review)

## 4g. Specialization-Aware Cherry-Pick

**Skip this step if `REQUIREMENTS_PATHS` was empty (no Pass 2 was run).**

**This step follows the `pss-design-alignment` skill's
[Specialization Filter](../../pss-design-alignment/references/specialization-filter.md):**
- Domain Overlap Check
- Duty Matching
- Practical Usage Test
- Filter Decision Table
- Examples by Agent Type
- Cherry-Pick Checklist

**And the [Merge Protocol](../../pss-design-alignment/references/merge-protocol.md):**
- Deduplication
- Tier Placement Rules
- Exclusion Documentation
- Verification and Validation
- Merge Checklist

You now have two candidate pools:
1. **Agent candidates** (from Step 3a) — already post-filtered in steps 4a-4f above
2. **Requirements candidates** (from Step 3b) — raw project-level candidates not yet filtered

For each element in `PSS_REQS_CANDIDATES` that is NOT already in the agent
candidates pool, evaluate:

**Specialization Filter**: Does this element relate to THIS agent's specific duties
and domain?

- **Example**: Agent = "database specialist", Requirements = "online shopping site"
  - The requirements will suggest skills for frontend (React), payments (Stripe), shipping APIs, etc.
  - The DB specialist should ONLY get: database/SQL skills, ORM skills, data migration, performance tuning
  - Frontend/payments/shipping skills → REJECT (not this agent's domain)

- **Example**: Agent = "security reviewer", Requirements = "healthcare app"
  - The requirements will suggest skills for FHIR/HL7, patient UI, appointment scheduling, etc.
  - The security reviewer should ONLY get: HIPAA compliance, auth/authz, encryption, vulnerability scanning
  - Patient UI/scheduling skills → REJECT (not this agent's domain)

**Decision criteria for each requirements candidate**:
1. Does the element's domain overlap with the agent's domain(s)? (e.g., both are "backend")
2. Does the element's purpose match one of the agent's duties? (e.g., agent does "database design", element is "postgresql-best-practices")
3. Would this agent realistically USE this element in its daily work?
4. Is this element already covered by a higher-scoring agent candidate?

If YES to criteria 1-3 and NO to 4 → ADD to the agent's candidate pool (typically
as secondary or specialized tier).
If NO to any of 1-3 → REJECT (document reason in `[skills.excluded]` with
"Excluded: requirements element outside agent specialization")

**Merge checklist**:
- [ ] Every requirements candidate has been individually evaluated against agent specialization
- [ ] Cherry-picked elements are added to secondary or specialized tier (not primary — that's reserved for agent-intrinsic skills)
- [ ] Rejected requirements candidates are documented in `[skills.excluded]` with clear reasons
- [ ] No duplicate elements after merge (requirements candidate already in agent pool → skip)
- [ ] Tier limits still respected after adding cherry-picked elements

## Step 5: Classify into Final Tiers

After post-filtering, classify the surviving skills:
- **primary** (max `MAX_PRIMARY`, default 7): Core skills the agent needs for its daily work
- **secondary** (max `MAX_SECONDARY`, default 12): Useful skills for common tasks
- **specialized** (max `MAX_SPECIALIZED`, default 8): Niche skills for specific situations

**Auto-Skills Override**: If the agent's frontmatter has an `auto_skills:` list,
ALL those skills MUST be placed in `primary` first. If this exceeds the max 7
limit, the primary limit is extended to accommodate all auto_skills (they are
author-declared requirements and take absolute priority). Only the REMAINING
primary slots (if any) are filled from scored candidates.

**Name Integrity Check**: Before writing any skill/agent/command name to the TOML,
verify it matches the exact name from the agent definition. Do NOT substitute names
from the local index. If a name from the agent definition doesn't exist locally,
include it anyway — the agent's plugin will provide it at runtime.

## Step 6: Identify Complementary Agents

From the skill index's `co_usage` data and your understanding of the agent's role:
- Find agents that commonly work alongside this agent's primary skills
- Identify agents covering complementary domains (e.g., security agent for a frontend agent)
- List only agents that genuinely add value — not every tangentially related agent

## Step 6a: Review and Confirm Tier Assignments

Before identifying complementary elements, verify the skill tier assignments from
Step 5:

- [ ] ALL `auto_skills` from frontmatter are in `primary` (NEVER demoted)
- [ ] `primary` contains 1-7 skills genuinely core to this agent's daily work (limit extends if auto_skills > 7)
- [ ] `secondary` contains useful-but-not-daily skills — max 12
- [ ] `specialized` contains niche skills for specific situations — max 8
- [ ] No skill appears in more than one tier
- [ ] No empty skill names in any tier
- [ ] Total primary + secondary + specialized ≤ 27
- [ ] ALL names match exactly what appears in the agent definition (no prefix changes)
- [ ] If agent is non-coding (orchestrator/coordinator): no LSP, linting, or code-fixing elements

If any tier exceeds its limit or a skill appears in multiple tiers, re-classify
before proceeding.

## Step 6b: Recommended Commands

From the element index, find slash commands that enhance this agent's workflow:
- Commands that automate tasks the agent performs frequently
- Commands related to the agent's domain (e.g., testing agent → /tdd command)
- Commands that complement the agent's primary skills

## Step 6c: Recommended Rules

List all available rules from the dedicated rules table (populated by Step 0):

```bash
"${BINARY_PATH}" list-rules --format json
```

For each rule, read its description and decide if it applies to this agent:
- Rules that enforce quality constraints in the agent's domain
- Rules that prevent common mistakes for the agent's type of work
- Rules that align with the agent's responsibilities

Use `"${BINARY_PATH}" get-description "<rule-name>" --format json` for details on
any rule. Rules are NOT suggestable (they're auto-injected by Claude Code), but
they MUST be listed in the `.agent.toml` so users know which behavioral
constraints apply.

## Step 6d: Recommended MCP Servers

From the element index, find MCP servers that enhance this agent's capabilities:
- MCP servers that provide tools the agent needs
- MCP servers related to the agent's domain (e.g., web dev agent → chrome-devtools MCP)

## Step 6e: LSP Servers (Language-Based)

**FIRST: Check if this agent writes code.** If the agent's role is "orchestrator",
or `agent_type` is "orchestrator", or the agent delegates ALL coding/analysis work
to sub-agents (check `writes_code` from Step 1), then LSP servers are NOT needed.
Set `recommended = []` and skip to Step 6f.

**Non-coding agent indicators** (any of these → skip LSP):
- `type: orchestrator` in frontmatter
- Role is "orchestrator", "coordinator", "manager", or "gatekeeper"
- Agent definition says "route to sub-agents", "delegate to", "does NOT write code"
- Agent has a routing table of sub-agents for all code-related tasks
- Agent's duties are exclusively: reviewing, routing, approving, reporting, coordinating

**Only for code-writing agents**, LSP assignment is language-based:

1. Detect project languages from cwd (look for package.json → TypeScript/JavaScript, pyproject.toml/setup.py → Python, Cargo.toml → Rust, go.mod → Go, *.swift → Swift, pom.xml/build.gradle → Java, *.cs/*.csproj → C#, CMakeLists.txt/Makefile → C/C++)
2. Map detected languages to LSP names:
   - Python → pyright-lsp
   - TypeScript/JavaScript → typescript-lsp
   - Go → gopls-lsp
   - Rust → rust-analyzer-lsp
   - Java → jdtls-lsp
   - C/C++ → clangd-lsp
   - Swift → swift-lsp
   - C# → csharp-lsp
3. If no software project detected in cwd, set `recommended = []` (do NOT default to any LSP)

## Step 6f: Recommended Hooks

From the agent's definition file and project context, identify hook
configurations:

1. Check the agent's `.md` frontmatter for a `hooks:` field — if present, include those hook names
2. Check `~/.claude/settings.json` and project `.claude/settings.json` for hook configurations relevant to the agent's tools (e.g., PreToolUse hooks for Bash, PostToolUse hooks for Write)
3. If the agent's primary skills define hooks in their frontmatter, include those
4. If no hook information is available from any source, leave `recommended = []`
