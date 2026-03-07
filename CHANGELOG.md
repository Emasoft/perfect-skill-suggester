# Changelog

All notable changes to the Perfect Skill Suggester plugin will be documented in this file.

## [2.3.1] - 2026-03-07

### Features

- Add `--index-file` flag for single-file indexing without full reindex
- Add language/framework conflict hard gates to hook mode scorer
- Add activity classification system for prompt intent detection
- Add `--agent` flag with `.agent.toml` output generation
- Add 8 CLI query/inspect subcommands (search, list, inspect, compare, stats, vocab, coverage, resolve)
- CozoDB integration for fast indexed queries
- FM-W1 synonym expansion + qualitative benchmark + text-categorization skill
- Add `/pss-add-to-index` command for incremental single-element indexing

### Bug Fixes

- Fix co-usage deserialization dead code + stale type filter test
- Fix agent-profile structural bugs (complementary_agents always empty, scarce type injection)
- Fix co-usage injection confidence hardcoded to Medium (now derives from score thresholds)
- Fix UTF-8 panic in `truncate_prompt` on multi-byte characters
- Fix race condition in `--batch-stdin` mode missing file locking
- Fix wrong binary name in release fallback path
- Fix wrong field name `method` → `generator` in status check
- Fix schema property mismatch `subagents` → `agents`
- Fix duplicate `documentation` domain key in pss-domains.json
- Fix polyglot project detection (was breaking on first marker instead of collecting all)
- Resolve 8 MAJOR CPV validation issues

### Performance

- Reduce token consumption across PSS plugin scripts and commands
- Add `--quiet` flag to scripts for sub-agent invocations

### Maintenance

- Sync validation scripts from CPV v1.7.5 through v1.8.0
- Switch indexer agents from haiku to sonnet for better accuracy
- Sync domain lookup table in pass1-sonnet.md with pss-domains.json (31 → 59 entries)
- Update cross-compilation docs (musl targets, cross tool, Homebrew warning)

## [2.3.0] - 2026-03-03

### Features

- Auto-discover marketplace MCP servers in indexing pipeline
- Enhance Pass 1 MCP extraction template for deep inspection
- pss-benchmark-agent documentation protocol skill

### Benchmark Improvements

- Merge W20 cycle 6 winner (674/1000 on 200-prompt benchmark)
- Merge W18 cycle 5 winner (610/1000)
- Merge W11 cycle 4 winner (537/1000)
- Merge W8 cycle 3 winner (312/500, +100% benchmark accuracy)
- Merge W5 cycle 2 winner (+57.6% benchmark accuracy)

## [2.2.4] - 2026-03-01

### Features

- 4-tier logarithmic scoring system

### Miscellaneous Tasks

- Sync uv.lock to match pyproject.toml v2.2.3

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
