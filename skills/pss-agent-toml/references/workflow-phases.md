# Workflow Phases 1-3: Context, Candidates, Evaluation

## Table of Contents

- [Phase 1: Gather Context](#phase-1-gather-context)
  - [Read the agent definition file](#read-the-agent-definition-file)
  - [Read requirements documents](#read-requirements-documents)
  - [Detect project languages from cwd](#detect-project-languages-from-cwd)
- [Phase 2: Get Candidates from the Index (Two-Pass Scoring)](#phase-2-get-candidates-from-the-index-two-pass-scoring)
  - [Pass 1: Agent-only scoring](#pass-1--agent-only-scoring-baseline-profile)
  - [Pass 2: Requirements-only scoring](#pass-2--requirements-only-scoring-project-level-candidates)
  - [Search for additional candidates](#search-for-additional-candidates)
- [Phase 3: Evaluate Each Candidate](#phase-3-evaluate-each-candidate)
  - [Read the candidate's source file](#read-the-candidates-source-file)
  - [Evaluate relevance](#evaluate-relevance)
  - [Detect mutual exclusivity](#detect-mutual-exclusivity)
  - [Check for obsolescence](#check-for-obsolescence)
  - [Verify stack compatibility](#verify-stack-compatibility)
  - [Identify gaps](#identify-gaps)
  - [Prune redundancy](#prune-redundancy)

---

## Phase 1: Gather Context

**1.1 Read the agent definition file**

Read the agent's `.md` file completely. Extract:
- **name**: From YAML frontmatter `name:` field or filename stem
- **description**: From frontmatter `description:` or first non-heading paragraph
- **role**: developer, tester, reviewer, deployer, designer, security, data-scientist, orchestrator
- **agent_type**: From frontmatter `type:` field (e.g., "orchestrator", "specialist", "worker")
- **duties**: From bullet lists under headings containing "responsibilities", "duties", "tasks"
- **tools**: From frontmatter `tools:` / `allowed-tools:` or tool mentions in body
- **domains**: From frontmatter or inferred (security, frontend, backend, devops, data, etc.)
- **auto_skills**: From frontmatter `auto_skills:` list — author-declared required skills (MUST stay in primary)
- **sub_agents**: From routing tables or delegation sections
- **writes_code**: Does this agent write/edit/analyze code directly? (determines LSP and dev-skill filtering)

**Name Preservation Rule**: Names referenced in the agent definition (skills, sub-agents, commands) MUST be preserved EXACTLY as written, even if they don't exist in the local index. NEVER rename or re-prefix them.

**Auto-Skills Pinning Rule**: Any skill in `auto_skills:` frontmatter MUST appear in `[skills].primary` — never demoted.

**1.2 Read requirements documents** (if available)

Read all provided design/requirements files. Extract:
- **project_type**: What is being built (web-app, mobile-app, cli-tool, library, etc.)
- **tech_stack**: Specific technologies, frameworks, languages
- **key features**: Core capabilities the project needs
- **constraints**: Performance, compliance, platform targets

**1.3 Detect project languages from cwd**

Scan the working directory for:
- `package.json` / `tsconfig.json` → TypeScript/JavaScript
- `pyproject.toml` / `setup.py` → Python
- `Cargo.toml` → Rust
- `go.mod` → Go
- `*.swift` / `Package.swift` → Swift
- `pom.xml` / `build.gradle` → Java
- `CMakeLists.txt` → C/C++

This determines LSP server assignment.

**Phase 1 Completion Checklist** — Copy this checklist and track your progress (ALL items must be checked before proceeding to Phase 2):

- [ ] Agent `.md` file has been read in full (not just frontmatter)
- [ ] `name` extracted (from frontmatter `name:` or filename stem)
- [ ] `description` extracted (frontmatter or first non-heading paragraph)
- [ ] `role` classified (developer/tester/reviewer/deployer/designer/security/data-scientist/orchestrator)
- [ ] `agent_type` extracted from frontmatter `type:` field (if present)
- [ ] `duties` extracted (bullet lists under responsibilities/duties/tasks headings)
- [ ] `tools` extracted (from frontmatter `tools:`/`allowed-tools:` or tool mentions in body)
- [ ] `domains` extracted or inferred (security/frontend/backend/devops/data/etc.)
- [ ] `auto_skills` extracted from frontmatter (these are PINNED to primary tier)
- [ ] `sub_agents` extracted from routing tables or delegation sections
- [ ] `writes_code` determined: does this agent write/edit/analyze code or only orchestrate?
- [ ] All `--requirements` files have been read in full (or confirmed: no requirements provided)
- [ ] `project_type` identified from requirements (web-app/cli-tool/mobile-app/library/api/microservice)
- [ ] `tech_stack` extracted from requirements (specific frameworks, languages, databases)
- [ ] `key_features` noted from requirements (features that drive skill selection)
- [ ] `constraints` noted from requirements (performance, compliance, platform targets)
- [ ] Project languages detected from cwd (presence of Cargo.toml/package.json/pyproject.toml/go.mod/etc.)
- [ ] LSP server assignment pre-determined (SKIP for non-coding agents: orchestrators, coordinators, etc.)

**If ANY item is unchecked: re-read the relevant file before proceeding.**

---

## Phase 2: Get Candidates from the Index (Two-Pass Scoring)

Candidate generation uses TWO separate binary invocations to avoid mixing agent-intrinsic skills with project-level skills. This ensures the agent only gets project-derived elements that match its specialization.

**2.1 Pass 1 — Agent-only scoring (baseline profile)**

Build a descriptor from the agent definition ONLY (no requirements content):

```bash
# $$ = current shell PID, ensures unique temp file per session
cat > /tmp/pss-agent-profile-input-$$.json << 'EOF'
{
  "name": "<agent-name>",
  "description": "<agent description from .md file ONLY>",
  "role": "<role>",
  "duties": ["<duty1>", "<duty2>"],
  "tools": ["<tool1>", "<tool2>"],
  "domains": ["<domain1>", "<domain2>"],
  "requirements_summary": "",
  "cwd": "<absolute path to working directory>"
}
EOF

"$BINARY_PATH" --agent-profile /tmp/pss-agent-profile-input-$$.json --format json --top 30
```

Save output as `AGENT_CANDIDATES`. These form the **baseline profile** — skills the agent needs regardless of which project it works on.

**2.1b Pass 2 — Requirements-only scoring (project-level candidates)**

**Skip if no requirements files were provided.**

Build a SEPARATE descriptor from the requirements documents ONLY:

```bash
cat > /tmp/pss-reqs-profile-input-$$.json << 'EOF'
{
  "name": "<project-name or 'project-requirements'>",
  "description": "<condensed requirements summary>",
  "role": "project",
  "duties": ["<key_feature1>", "<key_feature2>"],
  "tools": [],
  "domains": ["<project_domain1>", "<project_domain2>"],
  "requirements_summary": "<full requirements text, max 2000 chars>",
  "cwd": "<absolute path to working directory>"
}
EOF

"$BINARY_PATH" --agent-profile /tmp/pss-reqs-profile-input-$$.json --format json --top 30
```

Save output as `REQS_CANDIDATES`. These are **project-level candidates** — everything the project needs, NOT yet filtered for this agent's specialization. Cherry-picking happens in Phase 3 (step 4g).

**IMPORTANT**: Use a DIFFERENT temp file name (`pss-reqs-profile-input`) to avoid overwriting the agent candidates.

The binary returns scored candidates grouped by type in both passes:
```json
{
  "agent": "name",
  "skills": {
    "primary": [{"name":"...", "score":0.85, "confidence":"HIGH", "evidence":["keyword:docker"], "description":"..."}],
    "secondary": [...],
    "specialized": [...]
  },
  "complementary_agents": ["agent-x"],
  "commands": [{"name":"...", "score":0.6, ...}],
  "rules": [{"name":"...", "score":0.5, ...}],
  "mcp": [{"name":"...", "score":0.4, ...}],
  "lsp": [{"name":"...", "score":0.3, ...}]
}
```

**CRITICAL**: These are CANDIDATES, not final selections. The binary scores by keyword/intent matching only. YOU must now evaluate each candidate intelligently. Agent candidates are the baseline; requirements candidates must be cherry-picked based on agent specialization (see Phase 3, step 4g).

**2.2 Search for additional candidates using CLI query commands**

If the binary output doesn't cover a known need from the requirements, use the `pss` CLI subcommands to search the index. These use CozoDB Datalog for fast indexed queries.

**IMPORTANT — Entry Identifiers**: Every entry has a unique 13-character ID (base36). Names collide frequently (11 entries named "setup", 5 named "debug"). Always reference entries by their 13-char ID, not by name, when comparing, inspecting, or resolving to file paths.

```bash
# Discover what's available — the "menu" of installed elements
pss stats                                    # Overall index statistics
pss vocab languages                          # What languages are covered?
pss vocab frameworks --type skill            # What frameworks do skills support?
pss vocab domains --top 30                   # Domain coverage
pss coverage --type skill                    # Per-language/framework coverage for skills

# Search with text query + filters (AND-combined)
pss search "websocket" --type skill          # Full-text search for websocket skills
pss search "testing" --type skill --top 10   # Testing skills
pss search "deploy" --framework kubernetes   # Kubernetes deployment entries

# List with structured filters (no text query)
pss list --type mcp --top 20                 # All MCP servers
pss list --type skill --language python --category security  # Python security skills
pss list --type agent --category mobile      # Mobile agents

# Inspect a specific entry by ID (preferred) or name
pss inspect 1o7bxu6yv8aj8                   # By 13-char ID — unambiguous
pss inspect flutter-expert                   # By name — may be ambiguous

# Compare two candidates side-by-side
pss compare <id1> <id2>                      # Shows shared/unique keywords, frameworks, etc.

# Resolve IDs to file paths (for reading actual skill/agent content)
pss resolve <id1> <id2> <id3>               # Returns file paths for each ID
```

After narrowing to ~5 candidates per slot, use `pss resolve <id1> <id2> ...` to get file paths, then read the actual SKILL.md/agent.md files to make the final selection.

**Phase 2 Completion Checklist** (ALL items must be checked before proceeding to Phase 3):

- [ ] **Pass 1 (agent-only)**: Temp descriptor written (`pss-agent-profile-input-$$.json`) with `requirements_summary: ""`
- [ ] Pass 1 descriptor contains all 8 fields: `name`, `description`, `role`, `duties`, `tools`, `domains`, `requirements_summary`, `cwd`
- [ ] Pass 1 binary invoked with `--agent-profile`, `--format json`, `--top 30`
- [ ] Pass 1 binary returned exit code 0 and valid JSON
- [ ] `AGENT_CANDIDATES` saved with candidate counts per type noted
- [ ] **Pass 2 (requirements-only)**: SKIPPED if no requirements files provided
- [ ] Pass 2 temp descriptor written (`pss-reqs-profile-input-$$.json`) — DIFFERENT filename from Pass 1
- [ ] Pass 2 `requirements_summary` is 2000 characters or fewer
- [ ] Pass 2 binary returned exit code 0 and valid JSON
- [ ] `REQS_CANDIDATES` saved with candidate counts per type noted
- [ ] Additional manual index search performed for any known needs not covered by either pass

**If either binary invocation fails: do NOT proceed. Report the error and stop.**

---

## Phase 3: Evaluate Each Candidate (AI Reasoning Required)

**This phase is WHY an AI agent is mandatory.** For every candidate returned by the binary, you must:

**3.1 Read the candidate's source file**

For each skill/agent/command/rule candidate, read its actual `.md` file (the path is in the index entry or binary output). Understand:
- What does this element ACTUALLY do (not just what the keywords suggest)?
- What frameworks/runtimes/languages does it target?
- What tools does it use or assume are available?
- What is its scope — broad or narrow?

**3.2 Evaluate relevance to the agent's role**

Ask yourself:
- Does this element solve a problem the agent will ACTUALLY encounter?
- Is it relevant to the project's tech stack and domain?
- Is it the RIGHT tool for the job, or just a keyword match?
- Would a human developer working in this role want this element?

**3.3 Detect mutual exclusivity**

These element families are mutually exclusive — only ONE from each group:

| Category | Alternatives |
|----------|-------------|
| JS Framework | React, Vue, Angular, Svelte, Solid |
| JS Runtime | Node, Deno, Bun |
| JS Bundler | Webpack, Vite, esbuild, Parcel, Turbopack |
| CSS Framework | Tailwind, Bootstrap, Bulma, Chakra UI |
| ORM | Prisma, TypeORM, Drizzle, Sequelize |
| Testing | Jest, Vitest, Mocha, Jasmine |
| State Mgmt | Redux, Zustand, MobX, Recoil, Jotai |
| Deployment | Vercel, Netlify, AWS, GCP, Azure |
| Python Web | Django, Flask, FastAPI, Starlette |
| Python Test | pytest, unittest, nose2 |
| Mobile | React Native, Flutter, SwiftUI, Kotlin Compose |

**Resolution rule**: Keep the one that matches the tech_stack in requirements. If no requirements, keep the highest-scored and document alternatives in `[skills.excluded]`.

**3.4 Check for obsolescence**

Flag elements that reference:
- Deprecated APIs or patterns (componentWillMount, var, require() in ESM)
- End-of-life runtimes (Python 2, Node 14)
- Superseded tools (TSLint → ESLint, Moment.js → Luxon/date-fns)

Use WebSearch to verify if unsure: "Is <library> deprecated in 2026?"

**3.5 Verify stack compatibility**

- Python-only skill for a TypeScript project → REMOVE
- iOS skill for a web-only project → REMOVE
- React skill when requirements specify Vue → REMOVE
- AWS deployment skill when requirements specify Vercel → REMOVE

**3.5b Non-coding agent filter** (applies when `writes_code` = false):

If the agent is an orchestrator/coordinator/manager/gatekeeper that delegates all coding to sub-agents:
- REMOVE language-specific linting/formatting skills (eslint, ruff, prettier, etc.)
- REMOVE code-fixing agents (python-code-fixer, js-code-fixer, etc.)
- REMOVE LSP-dependent skills
- REMOVE test-writing agents (python-test-writer, js-test-writer, etc.)
- KEEP code review skills (reviewing ≠ writing)
- KEEP quality gate skills (CI/CD standards, coverage thresholds)
- KEEP architecture/design skills

**3.6 Identify gaps and search for missing elements**

After reviewing candidates, check if requirements mention needs not covered:
- "real-time" → search for WebSocket/SSE skills
- "i18n" → search for internationalization skills
- "HIPAA" / "PCI" → search for compliance/security skills
- "PDF generation" → search for document processing skills
- "accessibility" → search for WCAG/a11y skills

Search the index for each gap and add qualified matches.

**3.7 Prune redundancy**

If skill A covers everything skill B does plus more, remove skill B. Example: `exhaustive-testing` subsumes `unit-testing` — keep only `exhaustive-testing`.

**3.8 Specialization-aware cherry-pick from requirements candidates**

**Skip if no requirements files were provided (no Pass 2).**

For each element in `REQS_CANDIDATES` not already in the agent candidates, ask:
1. Does this element's domain overlap with the agent's domain?
2. Does this element match one of the agent's duties?
3. Would this agent realistically USE this element daily?

If YES → add to secondary/specialized tier. If NO → document in `[skills.excluded]` with reason.

Example: Agent = "database specialist", Project = "online shopping site"
- requirements suggest: React, Stripe, shipping APIs → REJECT (not DB domain)
- requirements suggest: postgresql-best-practices, SQL optimization → ACCEPT (DB domain)

**Phase 3 Completion Checklist** (ALL items must be checked before proceeding to Phase 4):

- [ ] Every agent candidate's SKILL.md/agent.md has been READ IN FULL
- [ ] Every candidate evaluated: "Does this solve a problem this agent will ACTUALLY encounter?"
- [ ] Mutual exclusivity checked for ALL 11 families
- [ ] Only ONE element remains from each mutually exclusive family
- [ ] Obsolescence/deprecation check completed for all candidates
- [ ] Stack compatibility verified: no cross-stack elements
- [ ] Gap analysis done: every key requirement scanned for missing coverage
- [ ] Redundancy pruning done: no strict-subset skills remain alongside their superset
- [ ] **Requirements cherry-pick** (if Pass 2 was run): every requirements candidate individually evaluated against agent specialization
- [ ] Cherry-picked elements added to secondary/specialized tier only (not primary)
- [ ] Rejected requirements candidates documented in `[skills.excluded]`
- [ ] Final candidates list assembled with intended tier assignment (primary/secondary/specialized)
- [ ] All `auto_skills` from frontmatter are in the primary tier (NEVER demoted)
- [ ] All names from agent definition preserved exactly (no prefix changes, no renaming)
- [ ] Non-coding agent filter applied if agent is orchestrator/coordinator (no LSP, no linting/formatting skills)

**If ANY candidate was NOT individually read: go back and read it before proceeding.**
