# Changelog

All notable changes to the Perfect Skill Suggester plugin will be documented in this file.

## [2.3.44] - 2026-03-10

### Bug Fixes

- Crash-safe reindex with atomic index swap and corrupt detection

## [2.3.43] - 2026-03-10

### Bug Fixes

- Revert CLAUDE_CONFIG_DIR/XDG_CONFIG_HOME env var support

### Bump

- Version 2.3.42 → 2.3.43

## [2.3.42] - 2026-03-10

### Bug Fixes

- Remove unused variable `home` in pss_discover.py (lint fix)
- Add missing shebang to pss_paths.py (plugin validation fix)

### Features

- Add CLAUDE_CONFIG_DIR and XDG_CONFIG_HOME support for portable config paths

### Bump

- Version 2.3.41 → 2.3.42

## [2.3.41] - 2026-03-10

### Features

- Auto-reindex when skill-index.json missing, use systemMessage for warnings

### Bump

- Version 2.3.40 → 2.3.41

## [2.3.40] - 2026-03-10

### Features

- Add README header image, rebuild binaries with expanded vocabulary, clean stale bins

### Bump

- Version 2.3.39 → 2.3.40

## [2.3.39] - 2026-03-10

### Features

- Add orchestration/queue framework vocabulary expansion

### Bump

- Version 2.3.38 → 2.3.39

## [2.3.38] - 2026-03-10

### Documentation

- Update README and architecture documentation

### Bump

- Version 2.3.37 → 2.3.38

## [2.3.37] - 2026-03-10

### Features

- Expand framework vocabulary from 61 to 108+ frameworks

### Bump

- Version 2.3.36 → 2.3.37

## [2.3.36] - 2026-03-10

### Bug Fixes

- Correct mypy type-ignore code no-redefine -> no-redef

### Miscellaneous Tasks

- Stage pending changes before release

### Bump

- Version 2.3.35 → 2.3.36

## [2.3.35] - 2026-03-10

### Bug Fixes

- Embed TOC headings in profiler refs, add Use when/Trigger with to design-alignment
- Match workflow-phases TOC headings exactly, trim SKILL.md under 4000 chars
- Add numbered workflow steps, trim to 3872 chars
- Restore required Resources section (3965 chars)

### Features

- Two-pass scoring architecture + pss-design-alignment skill

### Bump

- Version 2.3.34 → 2.3.35

## [2.3.34] - 2026-03-10

### Bug Fixes

- Embed complete TOC headings in SKILL.md references and trim to <4000 chars
- Restore required SKILL.md sections and fix description for validator
- Add checklist back to SKILL.md, compact review-protocol TOC to stay under 4000 chars
- Expand all TOC entries in SKILL.md references, add checklist phrase
- Restore required ## Output section in SKILL.md (3984 chars)

### Miscellaneous Tasks

- Add agent profile change command, verify script, and update profiler docs

### Bump

- Version 2.3.33 → 2.3.34

## [2.3.33] - 2026-03-10

### Bug Fixes

- Remove 80-char gate, always concatenate both messages in full

### Miscellaneous Tasks

- Sync uv.lock

### Bump

- Version 2.3.32 → 2.3.33

## [2.3.32] - 2026-03-10

### Bug Fixes

- Skip current message in transcript, return actual previous user message

### Miscellaneous Tasks

- Sync uv.lock

### Bump

- Version 2.3.31 → 2.3.32

## [2.3.31] - 2026-03-10

### Bug Fixes

- Use full previous message, no truncation

### Miscellaneous Tasks

- Sync uv.lock

### Bump

- Version 2.3.30 → 2.3.31

## [2.3.30] - 2026-03-10

### Bug Fixes

- Stop transcript pollution in skill suggestions

### Miscellaneous Tasks

- Sync uv.lock

### Bump

- Version 2.3.29 → 2.3.30

## [2.3.29] - 2026-03-10

### Bug Fixes

- Version-aware sorting in plugin cache resolution

### Miscellaneous Tasks

- Sync uv.lock

### Bump

- Version 2.3.28 → 2.3.29

## [2.3.28] - 2026-03-10

### Miscellaneous Tasks

- Sync uv.lock

### Styling

- Ruff format pss_reindex.py

### Bump

- Version 2.3.27 → 2.3.28

## [2.3.27] - 2026-03-10

### Bug Fixes

- Remove pipefail from reindex script — discover stderr warnings killed pipeline
- Resolve mypy type error in pss_reindex.py (int/float assignment)

### Miscellaneous Tasks

- Sync lock files (Cargo.lock, uv.lock)

### Refactor

- Convert reindex command from bash to Python script

### Bump

- Version 2.3.26 → 2.3.27

## [2.3.26] - 2026-03-10

### Bug Fixes

- Use word-boundary matching for negation gate, not substring

### Miscellaneous Tasks

- Sync lock files (Cargo.lock, uv.lock)

### Build

- Rebuild PSS binaries for all platforms

### Bump

- Version 2.3.25 → 2.3.26

## [2.3.25] - 2026-03-10

### Features

- Add unified build script for PSS + pss-nlp with log-only output

### Miscellaneous Tasks

- Sync lock files and rebuilt binaries with version 2.3.22

### Bump

- Version 2.3.24 → 2.3.25

## [2.3.24] - 2026-03-10

### Miscellaneous Tasks

- Add llm_externalizer_output/ to .gitignore

### Build

- Rebuild all PSS + pss-nlp binaries for 5 platforms

### Bump

- Version 2.3.23 → 2.3.24

## [2.3.23] - 2026-03-10

### Miscellaneous Tasks

- Sync uv.lock with version 2.3.22

### Bump

- Version 2.3.22 → 2.3.23

## [2.3.22] - 2026-03-09

### Bug Fixes

- Prevent temp directory leak in MCP descriptor discovery

### Miscellaneous Tasks

- Sync uv.lock with version 2.3.21

### Bump

- Version 2.3.21 → 2.3.22

## [2.3.21] - 2026-03-09

### Features

- Comprehensive audit — add profiler args, dependencies section, synonym fixes, debug output

### Bump

- Version 2.3.20 → 2.3.21

## [2.3.20] - 2026-03-09

### Features

- Add interactive review & refinement to agent profiler (Step 8b)
- Add interactive review & refinement to agent profiler
- Add interactive review & refinement to agent profiler

### Bump

- Version 2.3.19 → 2.3.20

## [2.3.19] - 2026-03-09

### Bug Fixes

- Profiler name preservation, auto_skills pinning, non-coding agent detection
- Restore 'Use when' and 'Trigger with' phrases in SKILL.md description

### Miscellaneous Tasks

- Trim SKILL.md under 4000 char validation limit
- Condense SKILL.md to pass validation (add Error Handling, checklist, trim refs TOC)
- Trim SKILL.md to 3868 chars (under 4000 limit) while keeping full refs TOC

### Bump

- Version 2.3.18 → 2.3.19

## [2.3.18] - 2026-03-09

### Features

- Add NLP-based negation detection via pss-nlp binary

### Bump

- Version 2.3.17 → 2.3.18

## [2.3.17] - 2026-03-08

### Miscellaneous Tasks

- Update lock files

### Refactor

- Hoist domain inference out of per-skill loop + add word-boundary matching

### Bump

- Version 2.3.16 → 2.3.17

## [2.3.16] - 2026-03-08

### Features

- Replace blocklist domain filter with bidirectional domain taxonomy

### Miscellaneous Tasks

- Sync uv.lock with v2.3.15 version bump

### Bump

- Version 2.3.15 → 2.3.16

## [2.3.15] - 2026-03-08

### Features

- Add host OS detection and non-programming domain inference filter

### Miscellaneous Tasks

- Update lockfiles (Cargo.lock, uv.lock)

### Bump

- Version 2.3.14 → 2.3.15

## [2.3.14] - 2026-03-08

### Features

- Add binary platform gate and strict language gate for skill filtering

### Bump

- Version 2.3.13 → 2.3.14

## [2.3.13] - 2026-03-08

### Bug Fixes

- **tests:** Add missing services field to 11 SkillEntry test initializers

### Miscellaneous Tasks

- Commit updated Cargo.lock, cross-compiled binaries, and uv.lock

### Bump

- Version 2.3.12 → 2.3.13

## [2.3.12] - 2026-03-08

### Bug Fixes

- Resolve all CPV validation issues and restructure directories
- **ship:** Update Cargo.toml path from rust/ to src/

### Miscellaneous Tasks

- Add cpv_token_cost.py synced from upstream CPV

### Bump

- Version 2.3.11 → 2.3.12

## [2.3.11] - 2026-03-08

### Bug Fixes

- **skills:** Embed reference TOCs inline for progressive discovery

### Bump

- Version 2.3.10 → 2.3.11

## [2.3.10] - 2026-03-08

### Bug Fixes

- **skills:** Resolve all CPV validation issues (MAJOR+MINOR+NIT → 0)

### Bump

- Version 2.3.9 → 2.3.10

## [2.3.9] - 2026-03-08

### Bug Fixes

- **security:** Harden scripts against path traversal, DoS, and symlink attacks

### Miscellaneous Tasks

- Remove obsolete shell/PowerShell hook wrappers

### Bump

- Version 2.3.8 → 2.3.9

## [2.3.8] - 2026-03-07

### Features

- Implement 5-tier logarithmic scoring system with binary filters

### Miscellaneous Tasks

- Backup v2.3.7 binary before tier system rewrite

### Bump

- Version 2.3.7 → 2.3.8

## [2.3.7] - 2026-03-07

### Miscellaneous Tasks

- Move obsolete agent-swarm reindex docs to docs_dev
- Update lock files

### Refactor

- Rewrite pss-reindex-skills to use Rust pipeline

### Bump

- Version 2.3.6 → 2.3.7

## [2.3.6] - 2026-03-07

### Bug Fixes

- Add required section headers to refactored SKILL.md files
- Add missing required sections to pass validation
- Resolve all MINOR validation issues in skill files

### Refactor

- Externalize skill/command docs into reference files

### Bump

- Version 2.3.5 → 2.3.6

## [2.3.5] - 2026-03-07

### Bug Fixes

- Use systemMessage for user notification, remove WASM target

### Bump

- Version 2.3.4 → 2.3.5

## [2.3.4] - 2026-03-07

### Bug Fixes

- Unset VIRTUAL_ENV before hook execution

### Bump

- Version 2.3.3 → 2.3.4

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

### Bump

- Version 2.3.2 → 2.3.3

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
