# PSS CLI Reference — Query & Inspect Commands

The `pss` binary provides 11 subcommands for querying, searching, and inspecting the skill index. These commands use CozoDB (Datalog) for fast indexed lookups — no full index scan needed.

## Entry Identifiers

Every entry in the index has a **13-character deterministic ID** (base36, lowercase alphanumeric). This ID is the only reliable way to reference entries because:

- **Names collide**: 11 entries named "setup", 5 named "debug", etc.
- **Paths change**: plugin staging copies entries to cache dirs; reinstalling changes paths
- **Namespaces overlap**: different plugins can register same-named skills

The ID is derived from the entry's name and source using FNV-1a 64-bit hash. Same entry always gets the same ID, even after re-indexing.

**Always use IDs** (not names) when programmatically referencing entries. Use `search` or `list` to find IDs, then `inspect` or `resolve` with the ID.

## Commands

### `pss search <query> [filters]`

Full-text search across entry names, descriptions, and keywords. Results are AND-filtered by any additional criteria.

```bash
# Find authentication-related skills
pss search "authentication" --type skill --top 10

# Find Python MCP servers
pss search "python" --type mcp

# Find Docker-related entries for the kubernetes framework
pss search "deploy" --framework kubernetes --platform cloud

# Search with language filter
pss search "testing" --language rust --type skill
```

**Options:**
| Flag | Description | Example values |
|------|-------------|----------------|
| `--type` | Entry type | skill, agent, command, rule, mcp, lsp |
| `--domain` | Domain area | security, ai-ml, devops |
| `--language` | Programming language | python, typescript, rust, go |
| `--framework` | Framework | react, django, flutter, kubernetes |
| `--tool` | Tool name | docker, terraform, ffmpeg |
| `--category` | Category | web-frontend, mobile, data-ml |
| `--file-type` | File extension | pdf, svg, xlsx |
| `--keyword` | Specific keyword | |
| `--platform` | Target platform | ios, linux, web, universal |
| `--top` | Max results (default: 20) | |
| `--format` | Output: json (default), table | |

### `pss list [filters]`

List entries with optional filtering. No text query — just filter by attributes. Use `--sort category` to group by category.

```bash
# All MCP servers
pss list --type mcp

# Skills for Python + security category
pss list --type skill --language python --category security

# Agents in mobile category
pss list --type agent --category mobile

# Commands sorted by category
pss list --type command --sort category --top 100
```

**Options:** Same as `search` plus `--sort` (name or category).

### `pss inspect <name-or-id>`

Show full details of one entry. Accepts either a name or a 13-char ID. Returns ALL fields including keywords, intents, co_usage, domain_gates, etc.

```bash
# By name
pss inspect flutter-expert

# By ID (preferred — unambiguous)
pss inspect 1o7bxu6yv8aj8

# Table format for human reading
pss inspect flutter-expert --format table
```

**Output (JSON)** includes: id, name, path, type, source, description, tier, boost, category, keywords, intents, languages, frameworks, platforms, domains, tools, file_types, use_cases, alternatives, negative_keywords, domain_gates, co_usage (usually_with, precedes, follows), and MCP/LSP fields if applicable.

With composite key `(name, source)`, `inspect` returns all entries matching the given name. If multiple entries exist from different sources, JSON format returns an array; table format prints each entry separately.

### `pss compare <ref1> <ref2>`

Side-by-side comparison of two entries. Shows shared and unique attributes per field, plus scalar differences.

```bash
# Compare two authentication skills
pss compare auth0-authentication clerk-authentication

# Compare by IDs
pss compare 1o7bxu6yv8aj8 r5ur3ulziqud

# Human-readable output
pss compare flutter-expert senior-ios --format table
```

**Output (JSON):**
```json
{
  "entry_a": {"name": "...", "scalars": {...}},
  "entry_b": {"name": "...", "scalars": {...}},
  "shared": {"keywords": [...], "languages": [...]},
  "unique_a": {"frameworks": [...]},
  "unique_b": {"frameworks": [...]},
  "scalar_diffs": {"type": ["agent", "skill"], "boost": [0, 2]}
}
```

### `pss stats`

Index statistics — total count and distribution by type, source, domain, category, language, framework, platform, tool.

```bash
pss stats
pss stats --format table
```

### `pss vocab <field> [--type T]`

List all distinct values for a metadata field with counts. This is the "menu" — shows what's available in the index.

Valid fields: `languages`, `frameworks`, `tools`, `domains`, `keywords`, `intents`, `platforms`, `file-types`, `categories`, `types`

```bash
# What programming languages are covered?
pss vocab languages

# What frameworks do MCP servers support?
pss vocab frameworks --type mcp

# Top 30 domains
pss vocab domains --top 30

# What types exist?
pss vocab types
```

### `pss coverage [--type T]`

Per-type coverage breakdown. Shows what languages, frameworks, domains, tools, and platforms are covered for a given entry type (or all types).

Use this to identify gaps: "All your skills are Go — install Python/JS skills before profiling an agent."

```bash
# Coverage for all skills
pss coverage --type skill

# Coverage for agents
pss coverage --type agent

# All types
pss coverage
```

### `pss resolve <id1> [id2...]`

Resolve one or more entry IDs to their file paths. This is the final step: after filtering 9000 entries down to 5 candidates, the agent reads the actual files to make the final choice.

```bash
# Single ID
pss resolve 1o7bxu6yv8aj8

# Multiple IDs
pss resolve 1o7bxu6yv8aj8 r5ur3ulziqud0 3gg562reilpd9

# Table format
pss resolve 1o7bxu6yv8aj8 --format table
```

**Output:**
```json
[
  {
    "id": "1o7bxu6yv8aj8",
    "name": "flutter-expert",
    "path": "/Users/.../.claude/plugins/cache/.../agents/flutter-expert.md",
    "type": "agent",
    "description": "Master Flutter development..."
  }
]
```

### `pss get-description <name> [--batch] [--format json|table]`

Retrieve lightweight metadata for one or more elements. Designed for tooltips, UI panels, and token-efficient lookups without reading entire skill/agent files.

```bash
# Single element
pss get-description react

# Namespaced lookup (plugin:element)
pss get-description "cpv:skill-validation"

# Batch mode (comma-separated)
pss get-description "react,flutter,vue" --batch

# Table format
pss get-description react --format table
```

**Options:**
| Flag | Description |
|------|-------------|
| `--batch` | Treat input as comma-separated names; returns JSON array |
| `--format` | Output: json (default), table |

**Output (JSON):**
```json
{
  "name": "react",
  "type": "skill",
  "description": "Expert in React development...",
  "source": "user",
  "source_path": "/path/to/SKILL.md",
  "scope": "user",
  "plugin": null,
  "trigger": ["react", "hooks", "jsx"]
}
```

**Ambiguity handling:** When multiple entries share the same name (from different sources), the response includes `"ambiguous": true` with a `"matches"` array. Use namespace-qualified names (e.g., `plugin-name:element-name`) or 13-char IDs to disambiguate.

**Rules fallback:** If no match is found in the main skill index, `get-description` falls back to the rules table (populated by `pss index-rules`). This enables metadata lookups for rule files used in agent profiling and description retrieval.

### `pss index-rules [--project-root PATH] [--format json|table]`

Index rule files from `~/.claude/rules/` (user scope) and `.claude/rules/` (project scope) into the rules table. Rules are not suggestable (they are auto-injected by Claude Code) but are needed for agent profiling and `get-description` lookups.

```bash
# Index rules from default locations (cwd as project root)
pss index-rules

# Specify a project root for .claude/rules/ discovery
pss index-rules --project-root /path/to/project

# Table output
pss index-rules --format table
```

**Options:**
| Flag | Description | Default |
|------|-------------|---------|
| `--project-root` | Project root directory for finding `.claude/rules/` | Current working directory |
| `--format` | Output: json (default), table | json |

**Behavior:**
- Scans `~/.claude/rules/` for user-scope rules and `<project-root>/.claude/rules/` for project-scope rules
- Extracts the rule name from the filename (e.g., `claim-verification.md` becomes `claim-verification`)
- Extracts the description from the first non-heading, non-empty content line of the file
- Idempotent — re-running updates existing entries rather than creating duplicates
- Returns a summary of indexed rules (count per scope, any errors)

### `pss list-rules [--scope user|project] [--format json|table]`

List all indexed rules with their descriptions.

```bash
# List all rules
pss list-rules

# Filter by scope
pss list-rules --scope user
pss list-rules --scope project

# Table format for human reading
pss list-rules --format table
```

**Options:**
| Flag | Description | Default |
|------|-------------|---------|
| `--scope` | Filter by rule scope: `user` or `project` | (all scopes) |
| `--format` | Output: json (default), table | json |

**Output (JSON):**
```json
[
  {
    "name": "claim-verification",
    "scope": "user",
    "description": "An 80% false claim rate occurred when grep results were trusted without reading files.",
    "path": "/Users/.../.claude/rules/claim-verification.md"
  }
]
```

## Typical Agent Workflow

An agent profiler building a `.agent.toml` would use the commands in this order:

1. **`pss stats`** — Understand what's in the index (9252 entries, 5577 skills, 1566 agents, etc.)
2. **`pss coverage --type skill`** — Check language/framework coverage. If 90% Python but agent needs Rust, warn user.
3. **`pss vocab frameworks --type skill`** — See all available frameworks to filter by
4. **`pss search "flutter" --type skill`** — Find candidate skills matching the agent's domain
5. **`pss list --type agent --language dart --framework flutter`** — Find complementary agents
6. **`pss compare <id1> <id2>`** — Compare top candidates to pick the best one
7. **`pss inspect <id>`** — Deep-dive into a candidate's full metadata
   - **`pss get-description <name>`** — Lightweight metadata lookup (faster than inspect, returns only key fields)
8. **`pss resolve <id1> <id2> <id3>`** — Get file paths to read actual skill/agent content for final selection

## ID System Details

| Property | Value |
|----------|-------|
| Length | 13 characters |
| Character set | 0-9, a-z (base36) |
| Hash algorithm | FNV-1a 64-bit |
| Input | Entry name + source (hashed together with separator) |
| Deterministic | Yes — same input always produces same ID |
| Collision-free | Effectively yes (64-bit hash space = 1.8×10¹⁹) |
| Example | `1o7bxu6yv8aj8` |

The hash input combines the entry name and its source field (e.g., `user`, `plugin:owner/name`, `marketplace:marketplace-name`) with a 0xFF separator byte. This ensures two entries named "debug" from different sources get different IDs.

## Environment Variables

| Variable | Description | Since |
|----------|-------------|-------|
| `CLAUDE_PLUGIN_DATA` | Persistent data directory for plugin state. PSS stores `skill-index.json` and `pss-skill-index.db` here. Set automatically by Claude Code v2.1.78+. Falls back to `~/.claude/cache/` on older CC versions. | CC v2.1.78+ |
| `CLAUDE_PLUGIN_ROOT` | Root directory of the installed plugin. Used by the Rust binary to locate the `VERSION` file and `bin/` directory at runtime. | CC v2.1.0+ |
| `PSS_NO_LOGGING` | Set to `1` to disable activation logging to `~/.claude/logs/pss-activations.jsonl`. | v1.0.0+ |

### `CLAUDE_PLUGIN_DATA` Details

Starting with Claude Code v2.1.78, plugins receive a dedicated persistent data directory via the `${CLAUDE_PLUGIN_DATA}` environment variable. PSS uses this directory to store:

- **`skill-index.json`** — The unified skill index generated by `/pss-reindex-skills`
- **`pss-skill-index.db`** — The CozoDB database backing CLI query commands (`search`, `list`, `inspect`, etc.)

**Fallback behavior:** When `CLAUDE_PLUGIN_DATA` is not set (Claude Code < v2.1.78), PSS falls back to `~/.claude/cache/` as the data directory. This ensures backward compatibility with older Claude Code versions.

**Migration:** No manual migration is needed. When PSS first runs under CC v2.1.78+ with `CLAUDE_PLUGIN_DATA` set, `/pss-reindex-skills` writes the index to the new location automatically.

## Output Formats

All commands support `--format json` (default) and `--format table`. JSON is intended for programmatic consumption by agents. Table format is for human inspection.
