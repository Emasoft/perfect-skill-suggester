# PSS File Format Specification v1.0

## Perfect Skill Suggester - Per-Skill Matcher File Format

**Status**: Draft
**Version**: 1.0.0
**Date**: 2026-01-18

---

## 1. Overview

The `.pss` file format is a JSON-based specification for shipping skills with pre-generated matchers. This eliminates the need for costly AI-based keyword extraction at install time, enabling instant activation without regenerating the skill index.

### Benefits

- **Zero-cost installation**: No AI calls needed to index new skills
- **Consistent activation**: Skill authors define optimal trigger keywords
- **Portable**: Skills ship with their own matcher definitions
- **Standardizable**: Can become an ecosystem-wide standard for skill distribution
- **Version-controlled**: Matchers evolve with the skill in the same repository

---

## 2. File Naming Convention

```
<skill-name>.pss
```

The file MUST be placed in the skill's root directory, alongside `SKILL.md`.

**Examples**:
```
docker-helper/
├── SKILL.md
├── docker-helper.pss    # Matcher file
└── references/
    └── ...

git-workflow/
├── SKILL.md
├── git-workflow.pss     # Matcher file
└── scripts/
    └── ...
```

---

## 3. File Structure

```json
{
  "$schema": "https://agentskills.org/schemas/pss-v1.json",
  "version": "1.0",
  "skill": {
    "name": "skill-name",
    "type": "skill|agent|command",
    "source": "user|project|plugin",
    "path": "relative/path/to/SKILL.md"
  },
  "matchers": {
    "keywords": [],
    "intents": [],
    "patterns": [],
    "directories": [],
    "negative_keywords": []
  },
  "scoring": {
    "tier": "primary|secondary|utility",
    "category": "string",
    "boost": 0
  },
  "metadata": {
    "generated_by": "ai|manual|hybrid",
    "generated_at": "ISO-8601 timestamp",
    "generator_version": "string",
    "skill_hash": "sha256 of SKILL.md content"
  }
}
```

---

## 4. Field Definitions

### 4.1 Root Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `$schema` | string | No | Schema URL for validation |
| `version` | string | Yes | PSS format version (currently "1.0") |
| `skill` | object | Yes | Skill identification |
| `matchers` | object | Yes | Trigger keywords and patterns |
| `scoring` | object | No | Scoring hints for the suggester |
| `metadata` | object | Yes | Generation metadata |

### 4.2 Skill Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Skill name (kebab-case) |
| `type` | enum | Yes | One of: `skill`, `agent`, `command` |
| `source` | enum | No | One of: `user`, `project`, `plugin` |
| `path` | string | No | Relative path to SKILL.md |

### 4.3 Matchers Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `keywords` | string[] | Yes | Primary trigger keywords (lowercase) |
| `intents` | string[] | No | Intent phrases ("set up ci", "debug tests") |
| `patterns` | string[] | No | Regex patterns for complex matching |
| `directories` | string[] | No | Directory names that suggest this skill |
| `negative_keywords` | string[] | No | Keywords that should NOT trigger this skill |

### 4.4 Scoring Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tier` | enum | No | Skill importance: `primary`, `secondary`, `utility` |
| `category` | string | No | Skill category for grouping |
| `boost` | integer | No | Score boost (-10 to +10) |

**Tier Definitions**:
- `primary`: Core skills that should be suggested first when matched
- `secondary`: Important but not primary focus
- `utility`: Helper skills, suggested as alternatives

### 4.5 Metadata Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `generated_by` | enum | Yes | One of: `ai`, `manual`, `hybrid` |
| `generated_at` | string | Yes | ISO-8601 timestamp |
| `generator_version` | string | No | Version of the generator tool |
| `skill_hash` | string | No | SHA-256 hash of SKILL.md for staleness detection |

---

## 5. Keyword Guidelines

### 5.1 Keywords Array

- **All lowercase**: `["docker", "container"]` not `["Docker", "Container"]`
- **Single words preferred**: Better precision than phrases
- **Include common variations**: `["typescript", "ts"]`
- **Include tool names**: `["docker", "dockerfile", "docker-compose"]`
- **Include error patterns**: `["type error", "build failed"]`

**Recommended count**: 5-15 keywords

### 5.2 Intents Array

Multi-word phrases that capture user intent:

```json
{
  "intents": [
    "set up ci",
    "configure github actions",
    "create workflow file",
    "automate deployment"
  ]
}
```

**Recommended count**: 3-8 intents

### 5.3 Patterns Array

Regex patterns for complex matching (use sparingly):

```json
{
  "patterns": [
    "\\.(yml|yaml)$",
    "workflow.*file",
    "ci/?cd"
  ]
}
```

**Use cases**:
- File extension matching
- Flexible phrase variations
- Technical pattern recognition

### 5.4 Directories Array

Directory names that suggest this skill should activate:

```json
{
  "directories": [
    ".github/workflows",
    "ci",
    "pipelines"
  ]
}
```

### 5.5 Negative Keywords Array

Keywords that indicate this skill should NOT be suggested:

```json
{
  "negative_keywords": [
    "gitlab",
    "jenkins",
    "azure devops"
  ]
}
```

---

## 6. Complete Examples

### 6.1 Simple Skill

```json
{
  "version": "1.0",
  "skill": {
    "name": "docker-helper",
    "type": "skill"
  },
  "matchers": {
    "keywords": [
      "docker",
      "container",
      "dockerfile",
      "docker-compose",
      "image",
      "registry"
    ],
    "intents": [
      "build docker image",
      "run container",
      "write dockerfile"
    ]
  },
  "scoring": {
    "tier": "primary",
    "category": "devops"
  },
  "metadata": {
    "generated_by": "ai",
    "generated_at": "2026-01-18T10:00:00Z",
    "generator_version": "pss-reindex-skills/1.0"
  }
}
```

### 6.2 Agent with Negative Keywords

```json
{
  "version": "1.0",
  "skill": {
    "name": "python-test-writer",
    "type": "agent"
  },
  "matchers": {
    "keywords": [
      "python",
      "pytest",
      "unittest",
      "test",
      "coverage",
      "mock"
    ],
    "intents": [
      "write python tests",
      "create test file",
      "add unit tests"
    ],
    "negative_keywords": [
      "javascript",
      "typescript",
      "jest",
      "mocha"
    ]
  },
  "scoring": {
    "tier": "primary",
    "category": "testing"
  },
  "metadata": {
    "generated_by": "manual",
    "generated_at": "2026-01-18T10:00:00Z"
  }
}
```

### 6.3 Command with Patterns

```json
{
  "version": "1.0",
  "skill": {
    "name": "commit",
    "type": "command"
  },
  "matchers": {
    "keywords": [
      "commit",
      "git",
      "save",
      "checkpoint"
    ],
    "intents": [
      "commit changes",
      "save my work",
      "create commit"
    ],
    "patterns": [
      "git\\s+commit",
      "commit.*message"
    ],
    "directories": [
      ".git"
    ]
  },
  "scoring": {
    "tier": "primary",
    "category": "version-control",
    "boost": 2
  },
  "metadata": {
    "generated_by": "hybrid",
    "generated_at": "2026-01-18T10:00:00Z",
    "skill_hash": "abc123..."
  }
}
```

---

## 7. Integration with PSS

### 7.1 Discovery

PSS discovers `.pss` files during indexing:

```
1. Scan skill directories for SKILL.md files
2. Check for accompanying <skill-name>.pss file
3. If found: Load matchers from .pss file
4. If not found: Generate matchers via AI (expensive)
```

### 7.2 Index Merging

When building the global index, PSS merges data from `.pss` files:

```javascript
// Pseudocode
for (skill of skills) {
  const pssFile = `${skill.dir}/${skill.name}.pss`;
  if (exists(pssFile)) {
    const pss = loadJSON(pssFile);
    index.skills[skill.name] = {
      ...pss.skill,
      keywords: pss.matchers.keywords,
      intents: pss.matchers.intents,
      patterns: pss.matchers.patterns,
      directories: pss.matchers.directories,
      negative_keywords: pss.matchers.negative_keywords,
      tier: pss.scoring?.tier || "secondary",
      category: pss.scoring?.category || "general",
      boost: pss.scoring?.boost || 0
    };
  } else {
    // AI generation fallback
    index.skills[skill.name] = generateWithAI(skill);
  }
}
```

### 7.3 Staleness Detection

Use `skill_hash` to detect when SKILL.md has changed:

```javascript
if (pss.metadata.skill_hash !== sha256(readFile("SKILL.md"))) {
  console.warn(`${skill.name}.pss is stale - SKILL.md has changed`);
  // Optionally regenerate
}
```

---

## 8. Generation Tools

### 8.1 AI Generation via `/pss-reindex-skills`

The existing PSS command can generate `.pss` files:

```bash
# Generate .pss files for all skills without them
/pss-reindex-skills --generate-pss

# Regenerate all .pss files
/pss-reindex-skills --generate-pss --force
```

### 8.2 Manual Creation

Skill authors can manually create `.pss` files with domain expertise.

### 8.3 Validation

```bash
# Validate a .pss file
/pss-validate docker-helper.pss
```

---

## 9. Rio Compatibility

The `.pss` format is designed to be compatible with Claude-Rio matchers:

| PSS Field | Rio Equivalent |
|-----------|----------------|
| `matchers.keywords` | `keywords` array in matcher function |
| `scoring.tier` | Maps to match count boost |
| `skill.type` | `type` field in matcher result |

**Conversion**:
```javascript
// PSS to Rio matcher
module.exports = function(context) {
  const prompt = context.prompt.toLowerCase();
  const keywords = ${JSON.stringify(pss.matchers.keywords)};
  const matchCount = keywords.filter(kw => prompt.includes(kw)).length;

  return {
    version: '2.0',
    matchCount: matchCount,
    type: '${pss.skill.type}'
  };
};
```

---

## 10. Best Practices

### 10.1 For Skill Authors

1. **Ship .pss with your skill**: Include it in your repository
2. **Update when skill changes**: Keep matchers synchronized
3. **Use hybrid generation**: AI + manual review
4. **Test activation**: Verify your keywords trigger correctly
5. **Include negative keywords**: Prevent false positives

### 10.2 For Distributors

1. **Validate before publishing**: Use `/pss-validate`
2. **Version your .pss files**: Track changes alongside SKILL.md
3. **Document your keywords**: Explain why each keyword was chosen

### 10.3 For PSS Implementers

1. **Prefer .pss over AI generation**: Lower latency, predictable results
2. **Merge scoring hints**: Apply tier and boost to ranking
3. **Handle missing fields gracefully**: Use defaults
4. **Warn on staleness**: Check skill_hash

---

## 11. Schema Validation

JSON Schema for validation is available at:
```
https://agentskills.org/schemas/pss-v1.json
```

Local validation:
```bash
# Using ajv-cli
ajv validate -s pss-v1.schema.json -d docker-helper.pss
```

---

## 12. Future Extensions

### Planned for v1.1

- `synonyms`: Custom synonym mappings per skill
- `exclusivity`: Mark skills as mutually exclusive
- `dependencies`: Specify skill dependencies
- `examples`: Sample prompts that should trigger this skill

### Planned for v2.0

- `embedding`: Pre-computed semantic embedding for vector search
- `context_rules`: Advanced context-aware activation rules
- `multi_language`: Localized keywords for international users

---

## Appendix A: JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://agentskills.org/schemas/pss-v1.json",
  "title": "PSS File Format",
  "description": "Perfect Skill Suggester per-skill matcher file",
  "type": "object",
  "required": ["version", "skill", "matchers", "metadata"],
  "properties": {
    "version": {
      "type": "string",
      "const": "1.0"
    },
    "skill": {
      "type": "object",
      "required": ["name", "type"],
      "properties": {
        "name": {
          "type": "string",
          "pattern": "^[a-z0-9-]+$"
        },
        "type": {
          "type": "string",
          "enum": ["skill", "agent", "command"]
        },
        "source": {
          "type": "string",
          "enum": ["user", "project", "plugin"]
        },
        "path": {
          "type": "string"
        }
      }
    },
    "matchers": {
      "type": "object",
      "required": ["keywords"],
      "properties": {
        "keywords": {
          "type": "array",
          "items": { "type": "string" },
          "minItems": 1
        },
        "intents": {
          "type": "array",
          "items": { "type": "string" }
        },
        "patterns": {
          "type": "array",
          "items": { "type": "string" }
        },
        "directories": {
          "type": "array",
          "items": { "type": "string" }
        },
        "negative_keywords": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },
    "scoring": {
      "type": "object",
      "properties": {
        "tier": {
          "type": "string",
          "enum": ["primary", "secondary", "utility"]
        },
        "category": {
          "type": "string"
        },
        "boost": {
          "type": "integer",
          "minimum": -10,
          "maximum": 10
        }
      }
    },
    "metadata": {
      "type": "object",
      "required": ["generated_by", "generated_at"],
      "properties": {
        "generated_by": {
          "type": "string",
          "enum": ["ai", "manual", "hybrid"]
        },
        "generated_at": {
          "type": "string",
          "format": "date-time"
        },
        "generator_version": {
          "type": "string"
        },
        "skill_hash": {
          "type": "string"
        }
      }
    }
  }
}
```

---

## Appendix B: Migration from Rio

For Claude-Rio users, convert existing matchers:

```javascript
// rio-to-pss.js
const fs = require('fs');

function convertRioToPss(matcherPath, skillName, skillType) {
  const matcher = require(matcherPath);

  // Extract keywords from matcher source
  const source = fs.readFileSync(matcherPath, 'utf8');
  const keywordsMatch = source.match(/keywords\s*=\s*\[(.*?)\]/s);
  const keywords = keywordsMatch
    ? JSON.parse(`[${keywordsMatch[1]}]`)
    : [];

  return {
    version: "1.0",
    skill: {
      name: skillName,
      type: skillType
    },
    matchers: {
      keywords: keywords
    },
    metadata: {
      generated_by: "manual",
      generated_at: new Date().toISOString()
    }
  };
}
```
