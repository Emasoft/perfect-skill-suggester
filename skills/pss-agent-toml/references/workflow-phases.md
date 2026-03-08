# Workflow Phases 1-3: Context, Candidates, Evaluation

## Table of Contents

- [Phase 1: Gather Context](#phase-1-gather-context)
  - [Read the agent definition file](#read-the-agent-definition-file)
  - [Read requirements documents](#read-requirements-documents)
  - [Detect project languages from cwd](#detect-project-languages-from-cwd)
- [Phase 2: Get Candidates from the Index](#phase-2-get-candidates-from-the-index)
  - [Invoke the Rust binary](#invoke-the-rust-binary)
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
- **role**: developer, tester, reviewer, deployer, designer, security, data-scientist
- **duties**: From bullet lists under headings containing "responsibilities", "duties", "tasks"
- **tools**: From frontmatter `tools:` / `allowed-tools:` or tool mentions in body
- **domains**: From frontmatter or inferred (security, frontend, backend, devops, data, etc.)

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
- [ ] `role` classified (developer/tester/reviewer/deployer/designer/security/data-scientist)
- [ ] `duties` extracted (bullet lists under responsibilities/duties/tasks headings)
- [ ] `tools` extracted (from frontmatter `tools:`/`allowed-tools:` or tool mentions in body)
- [ ] `domains` extracted or inferred (security/frontend/backend/devops/data/etc.)
- [ ] All `--requirements` files have been read in full (or confirmed: no requirements provided)
- [ ] `project_type` identified from requirements (web-app/cli-tool/mobile-app/library/api/microservice)
- [ ] `tech_stack` extracted from requirements (specific frameworks, languages, databases)
- [ ] `key_features` noted from requirements (features that drive skill selection)
- [ ] `constraints` noted from requirements (performance, compliance, platform targets)
- [ ] Project languages detected from cwd (presence of Cargo.toml/package.json/pyproject.toml/go.mod/etc.)
- [ ] LSP server assignment pre-determined from detected languages

**If ANY item is unchecked: re-read the relevant file before proceeding.**

---

## Phase 2: Get Candidates from the Index

**2.1 Invoke the Rust binary for scored candidates**

Build a JSON descriptor and invoke the binary:

```bash
# $$ = current shell PID, ensures unique temp file per session
cat > /tmp/pss-agent-profile-input-$$.json << 'EOF'
{
  "name": "<agent-name>",
  "description": "<agent description + requirements summary>",
  "role": "<role>",
  "duties": ["<duty1>", "<duty2>"],
  "tools": ["<tool1>", "<tool2>"],
  "domains": ["<domain1>", "<domain2>"],
  "requirements_summary": "<condensed requirements text, max 2000 chars>",
  "cwd": "<absolute path to working directory>"
}
EOF

# Invoke binary — returns up to 30 scored candidates grouped by type
"$BINARY_PATH" --agent-profile /tmp/pss-agent-profile-input-$$.json --format json --top 30
```

The binary returns scored candidates grouped by type:
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

**CRITICAL**: These are CANDIDATES, not final selections. The binary scores by keyword/intent matching only. YOU must now evaluate each candidate intelligently.

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

- [ ] Temporary JSON descriptor written with session-unique filename (use PID suffix: `pss-agent-profile-input-$$.json`)
- [ ] Descriptor contains all 8 fields: `name`, `description`, `role`, `duties`, `tools`, `domains`, `requirements_summary`, `cwd`
- [ ] `requirements_summary` is 2000 characters or fewer (truncate if needed)
- [ ] Rust binary invoked with `--agent-profile`, `--format json`, `--top 30`
- [ ] Binary returned exit code 0 (non-zero = STOP and report error)
- [ ] Binary output is valid JSON (parse to verify)
- [ ] Candidates grouped by type: `skills`, `complementary_agents`, `commands`, `rules`, `mcp`, `lsp` all present
- [ ] Candidate count per type noted (for gap analysis in Phase 3)
- [ ] Additional manual index search performed for any known needs not covered by binary output

**If binary fails: do NOT proceed. Report the error and stop.**

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

**Phase 3 Completion Checklist** (ALL items must be checked before proceeding to Phase 4):

- [ ] Every candidate's SKILL.md/agent.md has been READ IN FULL (not just the binary's description)
- [ ] Every candidate evaluated: "Does this solve a problem this agent will ACTUALLY encounter?"
- [ ] Mutual exclusivity checked for ALL 11 families (JS framework, runtime, bundler, CSS, ORM, testing, state mgmt, deployment, Python web, Python test, mobile)
- [ ] Only ONE element remains from each mutually exclusive family
- [ ] Obsolescence/deprecation check completed for all candidates
- [ ] Stack compatibility verified: no cross-stack elements (Python skill for TS project, iOS for web, etc.)
- [ ] Gap analysis done: every key requirement scanned for missing coverage
- [ ] Redundancy pruning done: no strict-subset skills remain alongside their superset
- [ ] Final candidates list assembled with intended tier assignment (primary/secondary/specialized)

**If ANY candidate was NOT individually read: go back and read it before proceeding.**
