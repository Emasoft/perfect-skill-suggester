# Scoring Protocol — Requirements-Only Pass

## Table of Contents

- [Requirements Descriptor Format](#requirements-descriptor-format)
- [Binary Invocation](#binary-invocation)
- [Output Format](#output-format)
- [Scoring Checklist](#scoring-checklist)

---

## Requirements Descriptor Format

Build a descriptor from the requirements/design document ONLY. Do NOT include any agent-specific information (role, duties, tools). The goal is to discover what the PROJECT needs, not what the agent does.

```json
{
  "name": "<project-name or 'project-requirements'>",
  "description": "<condensed summary of the design document>",
  "role": "project",
  "duties": ["<key_feature_1>", "<key_feature_2>", "<key_feature_3>"],
  "tools": [],
  "domains": ["<project_domain_1>", "<project_domain_2>"],
  "requirements_summary": "<full requirements text — MAX 2000 characters>",
  "cwd": "<current working directory>"
}
```

**Field extraction from the design document:**

| Field | What to extract |
|-------|----------------|
| `name` | Project name from the document title/header, or `"project-requirements"` |
| `description` | One-paragraph summary of what the project does |
| `duties` | Key features/capabilities the project must deliver (these become scoring queries) |
| `domains` | Business domains: e-commerce, healthcare, fintech, media, education, etc. |
| `requirements_summary` | Condensed text covering: tech stack, key features, constraints, integrations |

**IMPORTANT**: `requirements_summary` must be 2000 characters or fewer. Priority order for truncation:
1. project_type and tech_stack (highest priority — keep)
2. key_features (keep)
3. constraints (keep if space)
4. domain_specifics (truncate first)

## Binary Invocation

Use a DIFFERENT temp file name from the agent-only pass to avoid overwriting:

```bash
PSS_TMPDIR=$(python3 -c "import tempfile; print(tempfile.gettempdir())")
PSS_REQS_INPUT="${PSS_TMPDIR}/pss-reqs-profile-input-$$.json"

cat > "${PSS_REQS_INPUT}" << 'ENDJSON'
<descriptor JSON here>
ENDJSON

"${BINARY_PATH}" --agent-profile "${PSS_REQS_INPUT}" --format json --top 30
```

## Output Format

The binary returns the same grouped format as the agent-only pass:

```json
{
  "agent": "project-requirements",
  "skills": {
    "primary": [{"name": "...", "score": 0.85, "confidence": "HIGH", "evidence": [...]}],
    "secondary": [...],
    "specialized": [...]
  },
  "complementary_agents": [...],
  "commands": [...],
  "rules": [...],
  "mcp": [...],
  "lsp": [...]
}
```

These are **project-level candidates**. They represent everything the project needs, across ALL agents. They must be filtered through the agent's specialization before adding to any individual agent's profile.

## Scoring Checklist

- [ ] Requirements document read in full
- [ ] project_type, tech_stack, key_features, constraints, domain_specifics extracted
- [ ] Descriptor written to unique temp file (`pss-reqs-profile-input-$$.json`)
- [ ] Descriptor uses `"role": "project"` (not the agent's role)
- [ ] `requirements_summary` is ≤ 2000 characters
- [ ] Binary invoked and returned exit code 0
- [ ] Output saved as `REQS_CANDIDATES` for cherry-picking
- [ ] Temp file path recorded for cleanup in Step 9
