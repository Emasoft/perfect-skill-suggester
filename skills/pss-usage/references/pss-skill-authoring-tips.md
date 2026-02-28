# PSS Skill Authoring Tips

## Contents

- 1.0 Making your skills discoverable by PSS
  - 1.1 Essential frontmatter fields for PSS indexing
  - 1.2 Choosing effective keywords that match user prompts
  - 1.3 Selecting accurate categories from the 16 standard options
- 2.0 Improving suggestion quality for your skills
  - 2.1 Writing descriptions that help PSS match intent
  - 2.2 Including tool and action keywords
  - 2.3 Leveraging co-usage relationships automatically
- 3.0 Reference: Standard categories list

---

## 1.0 Making your skills discoverable by PSS

If you are developing skills and want PSS to suggest them effectively, you need to provide accurate metadata in the YAML frontmatter of your SKILL.md file.

### 1.1 Essential frontmatter fields for PSS indexing

PSS reads the following frontmatter fields when building the skill index:

```yaml
---
name: my-skill
description: "When and why to use this skill (be specific!)"
categories: ["testing", "debugging"]  # Pick from 16 standard categories
keywords: ["pytest", "unittest", "test-fixture", "mock"]
---
```

- **name**: The unique skill identifier. This is what users pass to `/skill activate <name>`.
- **description**: A sentence describing when and why to use this skill. PSS uses this for intent matching. Be specific about use cases rather than generic.
- **categories**: A list of one or more categories from the 16 standard options (see section 3.0). PSS uses these for intent-based evidence.
- **keywords**: A list of specific words and phrases that users naturally type when they need this skill. PSS uses these for keyword-based evidence.

### 1.2 Choosing effective keywords that match user prompts

Keywords should be words that users actually type in their prompts. Good keywords include:

- **Tool names**: pytest, docker, git, webpack, eslint
- **Action verbs**: debug, deploy, refactor, test, review
- **Domain terms**: authentication, database, API, frontend
- **Common abbreviations**: CI, CD, PR, DB (but also include full forms)

**Example for a testing skill:**
```yaml
keywords: ["pytest", "unittest", "test-fixture", "mock", "test", "tests", "unit-test", "integration-test"]
```

### 1.3 Selecting accurate categories from the 16 standard options

Choose one or two categories that best describe your skill's primary function. Avoid selecting too many categories, as this dilutes the intent signal.

See section 3.0 for the full list of standard categories.

---

## 2.0 Improving suggestion quality for your skills

### 2.1 Writing descriptions that help PSS match intent

PSS performs semantic analysis on descriptions. Write descriptions that clearly state:
- **What task** the skill helps with
- **When** to use it (specific scenarios)
- **What tools/technologies** are involved

**Good description:**
```
"Use when writing pytest unit tests, creating test fixtures, or setting up test infrastructure for Python projects"
```

**Poor description:**
```
"A testing skill for Python"
```

### 2.2 Including tool and action keywords

Include specific keywords that users naturally use:
- Tool names (pytest, docker, git, etc.)
- Action verbs (debug, deploy, refactor, etc.)
- Common use cases in the description text

### 2.3 Leveraging co-usage relationships automatically

PSS automatically detects co-usage relationships during indexing (Phase 2). You do not need to manually configure co-usage. However, you can improve detection by:

- Mentioning related skills in your SKILL.md content
- Referencing complementary skills in examples
- Describing workflows that involve multiple skills

PSS will detect these relationships and create co-usage links during reindexing.

---

## 3.0 Reference: Standard categories list

The 16 standard PSS categories are:

| Category | Description |
|----------|-------------|
| debugging | Finding and fixing bugs, error analysis |
| testing | Writing and running tests, test infrastructure |
| deployment | Deploying applications, release management |
| refactoring | Code restructuring, cleanup, optimization |
| documentation | Writing docs, API docs, README files |
| performance | Performance analysis, optimization, profiling |
| security | Security auditing, vulnerability scanning |
| database | Database design, queries, migrations |
| api | API design, REST/GraphQL, endpoint development |
| frontend | UI development, CSS, browser compatibility |
| backend | Server-side logic, services, middleware |
| devops | CI/CD, infrastructure, containerization |
| data-processing | ETL, data pipelines, data transformation |
| ml-ai | Machine learning, AI, model training |
| collaboration | Team workflows, code review, pair programming |
| other | Skills that do not fit other categories |

For PSS architecture and design details, see `docs/PSS-ARCHITECTURE.md` in the PSS plugin directory.
