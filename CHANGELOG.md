# Changelog

All notable changes to the Perfect Skill Suggester plugin will be documented in this file.

## [2.3.3] - 2026-03-07

### Bug Fixes

- Remove --no-verify from git_push(), enforce ship script for all pushes

### Features

- Read version from external VERSION file at runtime
- Show suggested skills to user as bright green stderr line

### Styling

- Highlight skill names in bold bright green in PSS stderr line
- Change PSS label to 'Pss...' whisper style
- Use parentheses instead of brackets for type labels
- Wrap PSS line in guillemets «« ... »»
- Move thunder emoji outside guillemets
- Single guillemets, no space after thunder
- Use 'Pss\!' instead of 'Pss...'
- Use 'Pss\!...' with both exclamation and ellipsis
- Make thunder and Pss!... bold bright green like skill names
- Make guillemets bold bright green
- Change label to 'Pss\!... use:' for clarity
- Dim green colon after 'use'

## [2.3.2] - 2026-03-07

### Bug Fixes

- Resolve 28 code errors from 4-review audit (sections A-E)
- Add required Nixtla sections to pss-benchmark-agent SKILL.md
- Agent-profile structural bugs — complementary_agents always empty, scarce type injection
- Co_usage deserialization dead code + stale type filter test
- Resolve 8 MAJOR CPV validation issues
- Add --quiet to pss_merge_queue.py calls in prompt templates and commands
- Comprehensive plugin audit — fix 25+ issues across all domains
- Resolve all CPV validation issues — 0 CRITICAL, 0 MAJOR, 0 MINOR
- Resolve all deep audit findings across docs and Rust schema

### Documentation

- Update documentation for v2.3.0 MCP indexing pipeline

### Features

- Merge W3 methodology improvements (+4.3% benchmark accuracy)
- Merge W5 cycle 2 winner (+57.6% benchmark accuracy)
- Merge W8 cycle 3 winner (312/500, +100% benchmark accuracy)
- Merge W11 cycle 4 winner (537/1000 on 200-prompt benchmark)
- Merge W18 cycle 5 winner (610/1000 on 200-prompt benchmark)
- Add pss-benchmark-agent documentation protocol skill
- Merge W20 cycle 6 winner (674/1000 on 200-prompt benchmark)
- Add /pss-add-to-index command for incremental single-element indexing
- Enhance Pass 1 MCP extraction template for deep inspection
- Auto-discover marketplace MCP servers in indexing pipeline
- Merge FM-W1 synonym expansion + add qualitative benchmark + text-categorization skill
- Add 8 CLI query/inspect subcommands + CozoDB integration + security hardening
- Add --agent flag with .agent.toml output + language-agnostic penalty + max-10 limits
- Add activity classification system + precision benchmark + plugin.json fixes
- Add language/framework conflict hard gates to hook mode scorer
- Add --index-file flag for single-file indexing
- Reduce token consumption across PSS plugin scripts and commands
- Add unified ship script (pss_ship.py) replacing separate release/hook scripts

### Miscellaneous Tasks

- Sync validation scripts from CPV v1.7.5
- Sync validation scripts from CPV v1.7.9, bump to v2.3.1
- Sync validation scripts from CPV v1.8.0
- Sync validation scripts from CPV v1.8.5

### Refactor

- Switch indexer agents from haiku to sonnet

### Bump

- Version 2.2.4 → 2.2.5

### Release

- V2.3.2

## [2.2.4] - 2026-03-01

### Features

- 4-tier logarithmic scoring system

### Miscellaneous Tasks

- Sync uv.lock to match pyproject.toml v2.2.3

### Bump

- Version 2.2.3 → 2.2.4

## [2.2.3] - 2026-03-01

### Bug Fixes

- Low-signal word scoring + 10x framework/tool name boost
- Phrase-focused scoring — penalize single common words, reward specific phrases

### Miscellaneous Tasks

- Snapshot before low-signal word scoring fix

### Bump

- Version 2.2.2 → 2.2.3

### Rebuild

- Update pss-darwin-arm64 binary for v2.2.2

## [2.2.2] - 2026-02-28

### Bug Fixes

- Add missing skill sections + sync CPV validation scripts
- Resolve all MINOR validation issues (TOC, SKILL.md metadata, mypy)
- Resolve remaining validation issues
- Use <agent-name>.md naming convention consistently across docs
- Make all PSS scripts and agent instructions cross-platform
- Address audit findings for multi-type indexing
- Correct bullet[0] bug in extract_intents_from_content
- Comprehensive audit fixes across 12 files
- Cross-platform fcntl, stale field names, wrong index paths
- Code quality improvements across Python scripts and Rust binary
- Resolve all clippy warnings in Rust binary
- Critical validator bugs, schema constraints, hook output format
- Resolve all remaining audit issues across 7 files
- Use full flag names in index search (--category, --language, --framework)
- Binary version 2.0.0 → 2.1.0, add reindex flags to README
- Resolve all validation issues, replace scripts from upstream CPV
- Resolve all MINOR validation issues, extract content to references
- Remove stale OUTPUT_SKILLS path references from 3 files
- Update CI build workflow for current GitHub runners
- Gracefully handle branch protection in CI binary commit

### Documentation

- Standardize validator references to universal CPV scripts
- Add marketplace installation instructions with --scope local
- Update README with --scope user installation instructions
- Enforce AI-mandatory principle across all plugin files
- Update all documentation for v2.1.0 release

### Features

- **pss:** V1.7.0 - Transient .pss files + atomic merge queue
- **pss:** V1.7.1 - Add end-to-end test script for runtime pipeline verification
- **pss:** V1.8.0 - Multi-platform binaries, WASM support, improved error messages
- **pss:** Enhanced matching pipeline with stemming, abbreviations, project context scanning
- **perfect-skill-suggester:** Bump version to 1.9.0
- Add .pss cleanup, /pss-setup-agent command, and --agent-profile Rust mode
- Add .agent.toml schema, validation script, and fail-fast error handling
- Extend PSS to multi-type indexing (skills, agents, commands, rules, MCP, LSP)
- Add universal agent TOML profile builder skill and standalone generator
- Add mandatory checklists to all phases + pipeline robustness fixes
- Add unified release script and update README

### Miscellaneous Tasks

- **pss:** Rebuild darwin-arm64 binary with --load-pss flag
- Sync validation scripts from CPV
- Sync validation scripts from CPV
- Sync validation scripts from CPV
- Bump version to 1.9.1
- Bump version to 1.9.2
- Bump version to 1.9.3
- Remove plugin-specific pss_validate_index.py, use CPV validator
- Bump version to 1.9.4
- Sync validation scripts, hooks, and workflows from CPV
- Bump version to 1.9.5
- Update lockfiles
- Sync CPV validation scripts and fix TOC embedding issues
- Sync 7 updated + 1 new validation scripts from CPV upstream
- Sync all 20 validation scripts from CPV upstream
- Add CLAUDE.md to gitignore

### Refactor

- Unify terminology skill→element across prompts, commands, and schemas
- Enforce AI-mandatory principle, remove standalone generator script

### Testing

- Add 5 Rust tests for multi-type functionality

### Build

- Rebuild darwin-arm64 binary with FNV-1a hash fix (v2.1.0)
- Rebuild all platform binaries for v2.2.1

### Bump

- Version 2.1.0 → 2.2.0
- Version 2.2.0 → 2.2.1
- Version 2.2.1 → 2.2.2

### Release

- Bump version to 2.1.0, update changelog and readme

## [1.6.1] - 2026-02-08

### Bug Fixes

- Simplify plugin.json to fix uninstall issue
- Update validator to match official Anthropic schema
- Timeout validator bug and bump to v1.2.0
- Correct marketplace repo name in notify workflow
- Remove duplicate hooks entry causing plugin load error

### Documentation

- Add marketplace installation notice to README
- Update CHANGELOG.md
- Add Update, Uninstall, and Troubleshooting sections to README

### Features

- Add marketplace validator and fix strict=false compliance
- **pss:** Bump version to 1.1.0
- Add notify-marketplace.yml workflow
- **reindex:** Enforce mandatory full regeneration from scratch [**BREAKING**]
- **pss:** Context-aware skill suggestion + reduced context flooding
- **v1.6.0:** Add Nixtla sections to pss-usage skill
- **pss:** Bump version to 1.6.1

### Miscellaneous Tasks

- Add git-cliff configuration and changelog
- Update CHANGELOG.md with latest changes
- Add requirements.txt and script improvements
- Regenerate CHANGELOG.md for v1.2.0
- Trigger notify-marketplace workflow
- Clean up test artifacts from plugin.json
- Gitignore all *_dev folders, untrack docs_dev

### Testing

- Trigger marketplace pipeline

### V1.5.0

- Dewey-like domain classification + dynamic tool catalog

---
*Generated by [git-cliff](https://git-cliff.org)*
