# Index JSON Schema and Format

## Two-Pass Architecture Overview

PSS uses a sophisticated two-pass agent swarm to generate both keywords AND co-usage relationships:

### Pass 1: Discovery + Keyword Analysis
The Python script `pss_discover.py` scans ALL element locations (skills, agents, commands, rules, MCP servers, LSP servers). Parallel agents then read each element's definition file and formulate **rio-compatible keywords**. All element types produce the same output fields (keywords, intents, category, patterns, etc.):
- **Single keywords**: `docker`, `test`, `deploy`
- **Multi-word phrases**: `fix ci pipeline`, `review pull request`, `set up github actions`
- **Error patterns**: `build failed`, `type error`, `connection refused`

**Output**: `skill-index.json` with keywords (Pass 1 format - keywords only, merged incrementally via pss_merge_queue.py)

### Pass 2: Co-Usage Correlation (AI Intelligence)
For EACH element, a dedicated agent:
1. Reads the element's data from the skill-index.json (from Pass 1)
2. Calls `skill-suggester --incomplete-mode` to find CANDIDATE elements via keyword similarity + CxC matrix heuristics
3. Reads candidate data from skill-index.json to understand their use cases
4. **Uses its own AI intelligence** to determine which elements are logically co-used
5. Writes co-usage data to a temp .pss file and merges it into the global index via pss_merge_queue.py

**Why Pass 2 requires agents (not scripts)**:
- Only AI can understand that "docker-compose" and "microservices-architecture" are logically related
- Only AI can reason that "security-audit" typically FOLLOWS "code-review" but PRECEDES "deployment"
- Only AI can identify that "terraform" is an ALTERNATIVE to "pulumi" for infrastructure
- Scripts can only match keywords; agents understand semantic relationships between elements

**Rio Compatibility**: Keywords are stored in a flat array and matched using `.includes()` against the lowercase user prompt. The `matchCount` is simply the number of matching keywords.

## Pass 1 Index Format

```json
{
  "version": "3.0",
  "generated": "2026-01-18T06:00:00Z",
  "generator": "ai-analyzed",
  "skill_count": 216,
  "skills": {
    "devops-expert": {
      "source": "user",
      "path": "/path/to/SKILL.md",
      "type": "skill",
      "keywords": ["github", "actions", "ci", "cd", "pipeline", "deploy", "github actions", "ci pipeline", "workflow failed", "set up ci"],
      "intents": ["deploy", "build", "test", "release"],
      "patterns": ["workflow.*failed", "ci.*error", "deploy.*stuck"],
      "directories": ["workflows", ".github"],
      "description": "CI/CD pipeline configuration and GitHub Actions workflows",
      "platforms": ["universal"],
      "frameworks": [],
      "languages": ["any"],
      "domain_gates": {}
    }
  }
}
```

## Index Schema (PSS v3.0 - extends rio v2.0)

| Field | Type | Description |
|-------|------|-------------|
| `source` | string | Where element comes from: `user`, `project`, `plugin` |
| `path` | string | Full path to SKILL.md |
| `type` | string | `"skill"`, `"agent"`, `"command"`, `"rule"`, `"mcp"`, or `"lsp"` (rio type field) |
| `keywords` | string[] | Flat array of lowercase keywords/phrases (rio compatible) |
| `intents` | string[] | PSS: Action verbs for weighted scoring (+4 points) |
| `patterns` | string[] | PSS: Regex patterns for pattern matching (+3 points) |
| `directories` | string[] | PSS: Directory contexts for directory boost (+5 points) |
| `description` | string | One-line description |
| `platforms` | string[] | PSS: Target platforms (`ios`, `android`, `macos`, `windows`, `linux`, `web`, `universal`) |
| `frameworks` | string[] | PSS: EXACT framework names extracted from element (`react`, `django`, `swiftui`, etc.) |
| `languages` | string[] | PSS: Target languages (`swift`, `rust`, `python`, etc., or `any`) |
| `domains` | string[] | PSS: Dewey domain codes from `schemas/pss-domains.json` (`310`, `620`, `910`, etc.) |
| `tools` | string[] | PSS: EXACT tool/library names extracted from element (builds dynamic catalog) |
| `file_types` | string[] | PSS: EXACT file extensions handled (`pdf`, `xlsx`, `mp4`, `svg`, etc.) |
| `domain_gates` | object | PSS: Named keyword groups as hard prerequisite filters. Keys are gate names (`target_language`, `input_language`, `output_language`, `target_platform`, `target_framework`, `text_language`, `output_format`), values are arrays of lowercase keywords. ALL gates must have at least one keyword match in the user prompt or the element is never suggested. Empty `{}` for generic elements. |

## Pass 2 Complete Index Format

```json
{
  "version": "3.0",
  "generated": "2026-01-19T00:00:00Z",
  "generator": "ai-analyzed",
  "pass": 2,
  "skill_count": 216,
  "skills": {
    "devops-expert": {
      "source": "user",
      "path": "/path/to/SKILL.md",
      "type": "skill",
      "keywords": [
        "github actions workflow",
        "ci/cd pipeline configuration",
        "continuous integration setup",
        "set up github actions",
        "deployment automation"
      ],
      "intents": ["deploy", "configure", "automate"],
      "patterns": ["workflow.*failed", "github actions.*error"],
      "directories": [".github/workflows", "workflows"],
      "description": "CI/CD pipeline configuration and GitHub Actions workflows",
      "use_cases": ["Setting up GitHub Actions", "Troubleshooting pipelines"],
      "category": "devops-cicd",
      "platforms": ["universal"],
      "frameworks": [],
      "languages": ["any"],
      "domain_gates": {},
      "co_usage": {
        "usually_with": ["github-workflow", "container-security"],
        "precedes": ["deploy-to-production"],
        "follows": ["code-review"],
        "alternatives": ["gitlab-ci", "jenkins-pipeline"],
        "rationale": "DevOps skills form a CI/CD pipeline - code review triggers builds, which trigger deployments..."
      },
      "tier": "primary"
    }
  }
}
```

## Comprehensive Element Discovery

**By default**, the discovery script scans:
1. User-level skills: `~/.claude/skills/`
2. Current project skills: `.claude/skills/`
3. Plugin cache: `~/.claude/plugins/cache/*/`
4. Local plugins: `~/.claude/plugins/*/skills/`
5. Current project plugins: `.claude/plugins/*/skills/`
6. Agents: `~/.claude/agents/`, `.claude/agents/`, plugin agents/
7. Commands: `~/.claude/commands/`, `.claude/commands/`, plugin commands/
8. Rules: `~/.claude/rules/`, `.claude/rules/`
9. **Marketplace plugins**: `~/.claude/plugins/marketplaces/**/` -- recursive scan for ALL skills/, agents/, commands/, rules/ at any depth. This is critical for agent profiling which needs ALL available elements, not just active ones.
10. MCP servers: `~/.claude.json`, `.mcp.json`
11. Marketplace MCP servers: `~/.claude/plugins/marketplaces/**/` (`.mcp.json`, `plugin.json`, `mcp.json`)
12. LSP servers: `~/.claude/settings.json` enabled plugins

**With `--all-projects`**, it ALSO scans:
13. ALL projects registered in `~/.claude.json`:
    - `<project>/.claude/skills/`
    - `<project>/.claude/plugins/*/skills/`

This creates a **superset index** containing ALL elements across all your projects. At runtime, the agent filters suggestions against its context-injected available elements list (see `docs/PSS-ARCHITECTURE.md`).

**NOTE:** Deleted projects are automatically detected and skipped with a warning.
