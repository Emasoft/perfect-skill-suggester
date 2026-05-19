# Changelog

All notable changes to the Perfect Skill Suggester plugin will be documented in this file.

Format conforms to [Keep a Changelog](https://keepachangelog.com).

## [3.6.12] - 2026-05-16

### Miscellaneous Tasks

- **rust:** Bump submodule for F-12 version-history subcommand

## [3.6.11] - 2026-05-16

### Miscellaneous Tasks

- **rust:** Bump submodule for F-17/F-18/F-19 Tier B subcommands

## [3.6.10] - 2026-05-16

### Miscellaneous Tasks

- **rust:** Bump submodule for F-6 scope-diff + UX-6 similarity score

## [3.6.9] - 2026-05-16

### Miscellaneous Tasks

- **rust:** Bump submodule for F-2 by-marketplace subcommand

## [3.6.8] - 2026-05-16

### Miscellaneous Tasks

- **rust:** Bump submodule for UX-8 (find-by-{framework,tool,platform}) + UX-9 (--source-prefix)

## [3.6.7] - 2026-05-16

### Bug Fixes

- **discover:** DI-10 slugify project name to avoid cross-checkout collisions

## [3.6.6] - 2026-05-16

### Bug Fixes

- **hook:** HP-4 doc + HP-5 reindex crash-counter (max 3/h)

### Miscellaneous Tasks

- **rust:** Bump submodule for DI-1 wave 1 (description_changed)

## [3.6.5] - 2026-05-16

### Bug Fixes

- **fail-loud:** V-3/V-4/V-5/V-8 — surface DB and parser errors instead of returning empty

### Miscellaneous Tasks

- **rust:** Bump submodule for UX-5 (--regex) + COR-8 (pss reindex orchestrator)

## [3.6.4] - 2026-05-16

### Miscellaneous Tasks

- **rust:** Bump submodule for DI-2 override resolver wiring

## [3.6.3] - 2026-05-16

### Miscellaneous Tasks

- Rebuild binary + sync submodule for v3.6.3 (F-5 compare-snapshots)

## [3.6.2] - 2026-05-16

### Bug Fixes

- **audit-20260514:** DI-4 manifest emitter — Python half

## [3.6.1] - 2026-05-16

### Bug Fixes

- **audit-20260514:** DI-3 + Phase 3 Tier A — parent + Python

## [3.6.0] - 2026-05-15

### Bug Fixes

- **audit-20260514:** Phase 1.1-1.3 + PERF-1 — parent + Python + shim
- **cpv:** Satisfy 2 MINORs from publish.py validation gate

## [3.5.1] - 2026-05-14

### Bug Fixes

- **security:** Phase 0 release — SEC-1..SEC-5 + COR-3 (audit 20260514)

## [3.5.0] - 2026-05-13

### Bug Fixes

- **cozodb:** Non-blocking reindex via staging-file + atomic rename

### Features

- **plugins:** Plugin dependency objects + data_dir runtime install

### Miscellaneous Tasks

- **build:** Add build.sh wrapper for CPV plugin-validation compliance

## [3.4.1] - 2026-05-08

### Bug Fixes

- **scoring:** Rebuild binaries + restore e2e fixture cleanliness (TRDD-014bcc92)

### Miscellaneous Tasks

- **lint:** Fix I001 import sort errors + trailing whitespace
- **lint:** I001 import sort fix in test_pss_cozodb_phase_b.py
- **lint:** Add .markdownlint.json to suppress strict markdownlint rules

## [3.4.0] - 2026-05-08

### Features

- **temporal:** Phase-2 discovery + reindex pipeline wiring (TRDD-152e697f)

## [3.3.3] - 2026-05-08

### Bug Fixes

- **test:** Phase 3 e2e — assert on CozoDB, use batch-stdin ([#9](https://github.com/Emasoft/perfect-skill-suggester/issues/9))

## [3.3.2] - 2026-05-08

### Bug Fixes

- **test:** Isolate pss_test_e2e from production ~/.claude/cache/

## [3.3.1] - 2026-05-07

### Bug Fixes

- **build:** Use shutil.copy not copy2 so bin/ gets fresh mtimes
- **build:** Same shutil.copy fix in pss_build.py (4 call sites)

## [3.3.0] - 2026-05-07

### Bug Fixes

- **typing:** Annotate Popen | None to satisfy mypy strict mode

### Features

- **temporal:** Event-sourced history index — Phases 1-4

## [3.2.12] - 2026-04-25

### Bug Fixes

- **skill:** Align pss-usage setup-checklist TOC with actual H2

## [3.2.10] - 2026-04-22

### Documentation

- **trdd:** Mark TRDD-46ac514e cozodb-unification as Done

### Miscellaneous Tasks

- **gitignore:** Ignore .janitor/ runtime state dir

## [3.2.8] - 2026-04-22

### Bug Fixes

- Apply reviewed defect fixes from llm-externalizer scan-and-fix

## [3.2.7] - 2026-04-21

### Miscellaneous Tasks

- **reports:** Anchor .gitignore, default all outputs to $MAIN_ROOT

## [3.2.6] - 2026-04-21

### Features

- **reports:** Enforce $MAIN_ROOT/reports/<component>/<ts±tz>-slug

## [3.2.5] - 2026-04-20

### Refactor

- **reports:** Reports/ is gitignored + private-data rule

## [3.2.4] - 2026-04-17

### Bug Fixes

- **pycozo:** Provision via PEP 723 + pin dataframe=False on Client

## [3.2.3] - 2026-04-17

### Refactor

- **reports:** Rotate after 24h instead of 14 days

## [3.2.2] - 2026-04-17

### Features

- **reports:** Rotate stale reports/ entries into reports_dev/

## [3.2.1] - 2026-04-17

### Features

- **clean:** Add pss_clean.py + --clean flag to publish.py

## [3.2.0] - 2026-04-17

### Features

- V3.2.0 audit — CC 2.1.110-112 support, CozoDB docs cleanup, hardened escape

## [3.1.1] - 2026-04-17

### Fixed
- **Cross-platform hook invocation via `uv run --script`** — `hooks/hooks.json` now calls `uv run --script` against `scripts/pss_hook.py`. The script carries PEP 723 inline metadata declaring `pycozo[embedded]>=0.7.6` as a dependency; `uv` provisions and caches a venv with pycozo on first invocation (~2–5 s cold, <100 ms warm). Windows, macOS, and Linux use an identical hook configuration — uv handles the `.venv/Scripts/python.exe` vs `.venv/bin/python` split internally.
- Fixes the `ERROR: pycozo is required` hook failure from v3.0.x / v3.1.0 where the hook's `python3` interpreter fell back to the system Python (no pycozo) and aborted at module load.
- **`scripts/pss_cozodb.py` degrades gracefully on missing pycozo** — module load no longer calls `sys.exit`; `Client()` construction raises a clear `ImportError` at first use, which callers catch.

### Added
- New Requirements section in README — `uv` is now an explicit prerequisite alongside Python ≥ 3.10 and git.

## [3.1.0] - 2026-04-16

### Added
- **New `/pss-search` and `/pss-added-since` slash commands** — thin wrappers around Phase D's Rust CLI subcommands (`pss search <query>`, `pss list-added-since <datetime>`) for ad-hoc index queries without firing the `UserPromptSubmit` scoring pipeline.
- `skills/pss-usage/SKILL.md` updated with a new "Querying the Index Directly" section listing all `pss_cozodb.py` Python helpers and the Rust CLI subcommands with example invocations.
- `skills/pss-authoring/SKILL.md` notes the v3.0 CozoDB-canonical indexing pipeline in a concise "How PSS indexes your skills" subsection.

### Changed
- **Harmonise skills & commands for CozoDB-canonical index** (Phase E).

## [3.0.0] - 2026-04-16 — BREAKING

### Changed
- **CozoDB is now the single canonical store** (Phase C of the CozoDB unification migration). `skill-index.json` is demoted to an optional debug export (`bin/pss export --json`). `pss_merge_queue.py`, `pss_make_plugin.py`, `pss_verify_profile.py`, `pss_generate.py`, and `pss_hook.py` all read/write the CozoDB via `scripts/pss_cozodb.py` (a thin pycozo wrapper).
- Rust CLI gained query/management subcommands (Phase D): `pss count`, `pss stats`, `pss get`, `pss search`, `pss list`, `pss health`, `pss find-by-*`, `pss list-added-since`, `pss list-updated-since`, `pss export --json`. Human-readable tables by default; `--json` for scripting.

### Added
- `first_indexed_at` and `last_updated_at` timestamps on every row, preserved across reindexes. Powers "what did I install since 2026-04-01?" queries.
- `pycozo[embedded]>=0.7.6` added as a hard Python dependency. `uv` installs it automatically on first hook run (v3.1.1+).

### Removed
- Rust `pss --build-db` flag — Python writes CozoDB directly via `fcntl`-locked atomic transactions.

### Fixed
- **submodule:** Point rust/ at d0a15d7 (Phase C+D rebuild).

### Migration
- Upgrading from v2.x requires no user action — the hook detects missing/empty CozoDB and auto-reindexes.
- Full design record: `design/tasks/TRDD-46ac514e-3627-44a6-b916-f37a1504b969-cozodb-unification.md`.

## [2.10.0] - 2026-04-16

### Added
- **Phase B of the CozoDB unification migration**: Python merge queue writes CozoDB directly; JSON becomes a derived export (still auto-written for backward compatibility — removed in v3.0.0).
- `pss export --json` subcommand added to the Rust binary for ad-hoc JSON snapshots.

## [2.9.41] - 2026-04-16

### Added
- **Phase A of the CozoDB unification migration**: `scripts/pss_cozodb.py` query helpers + `first_indexed_at` / `last_updated_at` columns on the CozoDB `skills` relation. JSON still canonical, CozoDB derived. Preserves install timestamps across reindexes.

## [2.9.40] - 2026-04-16

### Fixed
- **Bandaid for the `$CLAUDE_PLUGIN_DATA` scope-leak bug** in `scripts/pss_paths.py::get_data_dir()` — PSS was silently writing the index to foreign plugins' data dirs when invoked from their session scope. Fix: only trust `$CLAUDE_PLUGIN_DATA` when its basename contains "perfect-skill-suggester".

### Added
- TRDD for CozoDB unification.

## [2.9.39] - 2026-04-15

### Documentation

- **readme:** Explain JSON + CozoDB dual-index architecture

## [2.9.38] - 2026-04-15

### Added
- **Claude Code v2.1.109 compatibility** — tested range extended from v2.1.101 to v2.1.109. See [`docs/CC-COMPATIBILITY.md`](docs/CC-COMPATIBILITY.md) for per-version impact notes.
- **`[monitors]` pass-through** (CC v2.1.105+) — `.agent.toml` `[monitors]` section propagates verbatim into the generated `plugin.json` by `/pss-make-plugin-from-profile`, alongside existing `[metadata]` and `[userConfig]` pass-throughs. Enables background-monitor plugins (auto-arm at session start or on skill invoke).

### Changed
- Skill description cap raised 250 → 1,536 chars (CC v2.1.105) — PSS's longest skill description is 60 chars, still well within the new cap.
- `PreCompact` hook event noted (CC v2.1.105) — not declared by PSS (no reason to block compaction), documented as intentional in the compat matrix.

## [2.9.37] - 2026-04-13

### Bug Fixes

- **audit:** Round-4 audit fixes — dead path_gates feature + broken changelog + stale binaries

## [2.9.36] - 2026-04-13

### Bug Fixes

- **build:** Ship all 5 platform binaries reliably (cross + Apple Silicon + path bug)

## [2.9.35] - 2026-04-12

### Miscellaneous Tasks

- **rust:** Bump submodule for round-2 hardening (c06483a)

### Refactor

- **cc-compat:** Round-2 hardening — snake_case HookInput, rule path_gates, userConfig, docs

## [2.9.34] - 2026-04-12

### Added (cumulative across 2.9.34 – 2.9.37)
- **Claude Code v2.1.69 → v2.1.101 compatibility** — full version-by-version matrix in [`docs/CC-COMPATIBILITY.md`](docs/CC-COMPATIBILITY.md), declared hook events, HookInput schema notes.
- New hook events — `SessionStart` (silent lazy index warmup via `--warm-index`, eliminates first-prompt cold-start) and `PostCompact` (reserved stub for future re-suggest-after-compaction).
- Rule `path_gates` — rules with `paths:` frontmatter filter by project file-type + language-to-extension alignment (Python project → rule with `paths: ["**/*.py"]` now matches; previously excluded).
- `[userConfig]` pass-through — `.agent.toml` `[userConfig]` section propagates verbatim into the generated `plugin.json` by `/pss-make-plugin-from-profile`.
- Profiler frontmatter upgrades — CC-official `skills:` subagent frontmatter (alongside PSS-internal `auto_skills`), `effort: high`, `maxTurns: 40`.

### Changed
- **snake_case HookInput boundary** — `pss_hook.py` and the Rust `HookInput` struct now use the spec-compliant `transcript_path` (was reading a non-existent camelCase key, silently breaking previous-message augmentation).
- Build pipeline reliability — all 5 platform binaries (darwin-arm64/x86_64, linux-arm64/x86_64, windows-x86_64) built via `cross` + Docker with `DOCKER_DEFAULT_PLATFORM=linux/amd64` for Apple Silicon hosts; `publish.py` build failures are now FATAL with post-build mtime verification.
- Conditional pss-nlp rebuild — `publish.py` tracks `rust/negation-detector/` changes and rebuilds pss-nlp-* binaries only when source changes.

## [2.9.33] - 2026-04-10

### Refactor

- **publish:** Replace env-var bypass with process ancestry check

## [2.9.32] - 2026-04-10

### Refactor

- **publish:** Enforce mandatory gates + git-cliff + GitHub release

## [2.9.31] - 2026-04-10

### Performance

- Kw_lookup pre-filtering + increased hook timeouts

### Bump

- Version 2.9.30 → 2.9.31

## [2.9.30] - 2026-04-07

### Refactor

- Rename pss_ship.py → publish.py, enforce pre-push quality gate

### Bump

- Version 2.9.29 → 2.9.30

## [2.9.29] - 2026-04-07

### Bug Fixes

- LLM Externalizer audit fixes + remove local CPV scripts

### Bump

- Version 2.9.28 → 2.9.29

## [2.9.28] - 2026-04-07

### Bug Fixes

- Comprehensive adversarial hardening across all scripts

### Bump

- Version 2.9.27 → 2.9.28

## [2.9.27] - 2026-04-07

### Bug Fixes

- Adversarial security hardening from LLM Externalizer audit

### Bump

- Version 2.9.26 → 2.9.27

## [2.9.26] - 2026-04-07

### Bug Fixes

- 8 HIGH findings from second LLM Externalizer scan

### Bump

- Version 2.9.25 → 2.9.26

## [2.9.25] - 2026-04-07

### Bug Fixes

- Avoid absolute path literals in pss_build.py (CPV MINOR)

### Bump

- Version 2.9.24 → 2.9.25

## [2.9.24] - 2026-04-07

### Bug Fixes

- All remaining HIGH findings from LLM Externalizer audit

### Bump

- Version 2.9.23 → 2.9.24

## [2.9.23] - 2026-04-07

### Bug Fixes

- Shell injection hardening, empty CLAUDE_PLUGIN_DATA, name filter case

### Bump

- Version 2.9.22 → 2.9.23

## [2.9.22] - 2026-04-07

### Bug Fixes

- Windows compat for PID check and debug mode, source filter bug

### Bump

- Version 2.9.21 → 2.9.22

## [2.9.21] - 2026-04-07

### Documentation

- Add cross-client discovery and AgentSkills support to README

### Bump

- Version 2.9.20 → 2.9.21

## [2.9.20] - 2026-04-07

### Added
- **Cross-client skill discovery** — scans `skills/` directories from 27 known AI clients (Codex, Copilot, Gemini, Kiro, Roo, Trae, Qwen, OpenHands, etc.) following the [AgentSkills](https://agentskills.io) open standard.
- AgentSkills metadata indexing — `metadata.language/framework/platform` fields used as authoritative domain gates; `metadata.tags` and `compatibility` extracted as keywords.
- `effort` frontmatter on all 8 commands (low/medium/high per complexity).
- Claude Code v2.1.92 compatibility — `disableSkillShellExecution` noted, CPV remote validation updated.

### Bump
- Version 2.9.19 → 2.9.20

## [2.9.19] - 2026-04-07

### Features

- Scan .agents/skills/ for cross-client skill discovery (AgentSkills spec)

### Bump

- Version 2.9.18 → 2.9.19

## [2.9.18] - 2026-04-07

### Features

- Support AgentSkills open standard metadata in indexing pipeline

### Bump

- Version 2.9.17 → 2.9.18

## [2.9.17] - 2026-04-07

### Features

- Add effort frontmatter to all commands per skills spec

### Bump

- Version 2.9.16 → 2.9.17

## [2.9.16] - 2026-04-07

### Documentation

- Update CC compatibility to v2.1.92, add disableSkillShellExecution note

### Bump

- Version 2.9.15 → 2.9.16

## [2.9.15] - 2026-04-02

### Bug Fixes

- Agent description >250 chars, duplicate tool, missing timeouts, stale path

### Bump

- Version 2.9.14 → 2.9.15

## [2.9.14] - 2026-04-02

### Bug Fixes

- UTF-8 truncation panic, stale Task tool refs, CC v2.1.90 compat
- Add 'Loaded/Used by' annotations to non-user-invocable skills
- Restore 'Use when' phrases in skill descriptions alongside 'Used by'

### Bump

- Version 2.9.13 → 2.9.14

## [2.9.13] - 2026-03-31

### Bug Fixes

- Remove outputStyles from plugin.json (auto-discovered by Claude Code)

### Bump

- Version 2.9.12 → 2.9.13

## [2.9.12] - 2026-03-28

### Bug Fixes

- Migrate batch_check references to code_task after deprecation
- Trim benchmark SKILL.md to under 4000 char limit

### Bump

- Version 2.9.11 → 2.9.12

## [2.9.11] - 2026-03-28

### Bug Fixes

- CPV remote execution migration - update ship script and add-element script

### Bump

- Version 2.9.10 → 2.9.11

## [2.9.10] - 2026-03-28

### Bug Fixes

- Spec compliance fixes for pss-add-element and README updates

### Bump

- Version 2.9.9 → 2.9.10

## [2.9.9] - 2026-03-28

### Added
- **`/pss-add-element` command** — add standalone elements (skills, agents, commands, hooks, rules, MCP servers, LSP servers, output styles) to existing plugins with duplicate detection and CPV validation.
- Claude Code v2.1.85 compatibility — transcript parser updated for new JSONL format (`toolUseResult` / `sourceToolAssistantUUID` entries skipped; `agentId` removal handled).
- Ship script hardening — submodule push verification, `Cargo.lock` staging, `uv.lock` sync, pre-push gate auto-pushes submodules.

### Miscellaneous Tasks
- Stage rust submodule lockfile and uv.lock updates.

### Bump
- Version 2.9.8 → 2.9.9

## [2.9.8] - 2026-03-28

### Features

- Add pss-add-element command and script for single-element indexing

### Bump

- Version 2.9.7 → 2.9.8

## [2.9.7] - 2026-03-28

### Miscellaneous Tasks

- Stage ship script and lockfile updates

### Bump

- Version 2.9.6 → 2.9.7

## [2.9.6] - 2026-03-28

### Miscellaneous Tasks

- Stage rust submodule lockfile and uv.lock updates
- Add submodule push guard to ship script gate pipeline

### Bump

- Version 2.9.5 → 2.9.6

## [2.9.5] - 2026-03-28

### Miscellaneous Tasks

- Stage binary, hook, rust submodule, and lockfile updates

### Bump

- Version 2.9.4 → 2.9.5

## [2.9.4] - 2026-03-26

### Bug Fixes

- Remove stale max_tokens/ensemble params from LLM Externalizer calls

### Bump

- Version 2.9.3 → 2.9.4

## [2.9.3] - 2026-03-26

### Miscellaneous Tasks

- Ruff format all Python scripts

### Bump

- Version 2.9.2 → 2.9.3

## [2.9.2] - 2026-03-25

### Features

- Compact skills-only hook output (5 lines max)

### Bump

- Version 2.9.1 → 2.9.2

## [2.9.1] - 2026-03-25

### Miscellaneous Tasks

- Remove .serena/ from gitignore
- Track .serena/ project config
- Update uv.lock and rust submodule

### Bump

- Version 2.9.0 → 2.9.1

## [2.9.0] - 2026-03-25

### Features

- Merge 3 worktree branches — scoring improvements, infrastructure queries, name affinity boost

### Miscellaneous Tasks

- Gitignore .serena/

### Bump

- Version 2.8.7 → 2.9.0

## [2.8.7] - 2026-03-23

### Bug Fixes

- Wrong binary path, missing allowed-tools, fragile PLUGIN_ROOT fallback

### Miscellaneous Tasks

- Update gitignore and uv.lock

### Bump

- Version 2.8.6 → 2.8.7

## [2.8.6] - 2026-03-22

### Miscellaneous Tasks

- Update changelog and uv.lock
- Gitignore .rechecker/

### Performance

- Strip system-reminders before should_skip_prompt, minimize binary stdin

### Bump

- Version 2.8.5 → 2.8.6

## [2.8.5] - 2026-03-22

### Miscellaneous Tasks

- Update uv.lock and rust submodule

### Performance

- Replace regex with str.find() for system-reminder stripping

### Bump

- Version 2.8.4 → 2.8.5

## [2.8.4] - 2026-03-21

### Features

- Add [description], [output_styles] sections and expand [dependencies] in .agent.toml schema

### Miscellaneous Tasks

- Update rust submodule (schema output changes)

### Bump

- Version 2.8.3 → 2.8.4

## [2.8.3] - 2026-03-20

### Bug Fixes

- Plugin rules via SessionStart/SessionEnd hook symlinks

### Bump

- Version 2.8.2 → 2.8.3

## [2.8.2] - 2026-03-20

### Bug Fixes

- Remaining audit issues — docs clarity, rules dir, profiler overlap

### Miscellaneous Tasks

- Update uv.lock

### Bump

- Version 2.8.1 → 2.8.2

## [2.8.1] - 2026-03-20

### Bug Fixes

- Audit fixes — perf regression hoisted, profiler 1.6s → 1.0s

### Miscellaneous Tasks

- Update uv.lock

### Bump

- Version 2.8.0 → 2.8.1

## [2.8.0] - 2026-03-20

### Added
- **Fast profiling mode** (`/pss-setup-agent --fast`) — Rust binary only, 2-5 seconds, no AI agent needed.
- 25+ mutual exclusivity groups — automatic conflict detection (React/Vue/Angular, Jest/Vitest, Prisma/TypeORM, etc.).
- Plugin generator (`/pss-make-plugin-from-profile`) — creates installable plugins from `.agent.toml` profiles.

### Fixed
- Lint fixes in `pss_make_plugin.py`.
- Remove tomli fallback (require Python 3.11+).

### Miscellaneous Tasks
- Update uv.lock.

### Bump
- Version 2.7.3 → 2.8.0

## [2.7.3] - 2026-03-20

### Bug Fixes

- Constant-time scoring regardless of prompt size

### Miscellaneous Tasks

- Update uv.lock

### Bump

- Version 2.7.2 → 2.7.3

## [2.7.2] - 2026-03-19

### Features

- Domain-aware scoring + sub-domain filtering for profiler

### Miscellaneous Tasks

- Update uv.lock

### Bump

- Version 2.7.1 → 2.7.2

## [2.7.1] - 2026-03-19

### Bug Fixes

- Punctuation-aware tokenization + smarter context augmentation

### Miscellaneous Tasks

- Update uv.lock

### Bump

- Version 2.7.0 → 2.7.1

## [2.7.0] - 2026-03-19

### Bug Fixes

- Enable domain gate filtering (was completely dead)

### Features

- Add --fast mode for agent profiling + Rust pre-optimizations
- LOC-based domain taxonomy for skill classification
- Add computer-graphics domain (LOC: Graphics processing units, WebGL, SVG, Rendering)
- Enrich taxonomy with LOC software headings (malware, agents, quality, containers)
- LOC-sourced languages (60) and platforms (30) for domain gates
- ACM CCS 2012 taxonomy enrichment for domain classification

### Refactor

- Shared domain taxonomy for enrichment + scoring

### Bump

- Version 2.5.3 → 2.6.0
- Version 2.6.0 → 2.7.0

## [2.5.3] - 2026-03-19

### Miscellaneous Tasks

- Remove redundant files, update .gitignore

### Bump

- Version 2.5.2 → 2.5.3

## [2.5.2] - 2026-03-19

### Miscellaneous Tasks

- Update all dependencies to latest versions

### Bump

- Version 2.5.1 → 2.5.2

## [2.5.1] - 2026-03-19

### Bug Fixes

- Correct Cargo workspace target paths after submodule migration

### Bump

- Version 2.5.0 → 2.5.1

## [2.5.0] - 2026-03-19

### Refactor

- Move Rust source to git submodule, binaries to top-level bin/
- Update all path references for bin/ and rust/ submodule structure

### Bump

- Version 2.4.11 → 2.5.0

## [2.4.11] - 2026-03-18

### Bug Fixes

- Audit fixes — error handling, dead code removal, documentation gaps

### Bump

- Version 2.4.10 → 2.4.11

## [2.4.10] - 2026-03-18

### Features

- Mmap-based backward transcript reader in Rust binary

### Bump

- Version 2.4.9 → 2.4.10

## [2.4.9] - 2026-03-18

### Bug Fixes

- Optimize transcript reading to prevent hook timeout on large sessions

### Bump

- Version 2.4.8 → 2.4.9

## [2.4.8] - 2026-03-18

### Bug Fixes

- Optimize transcript reading to prevent hook timeout on large sessions

### Bump

- Version 2.4.7 → 2.4.8

## [2.4.7] - 2026-03-18

### Bug Fixes

- Prevent hook timeout on long prompts (system-reminders, session continuations)

### Bump

- Version 2.4.6 → 2.4.7

## [2.4.6] - 2026-03-18

### Added
- **`${CLAUDE_PLUGIN_DATA}` integration** (CC v2.1.78+) — persistent state directory for `skill-index.json` and CozoDB database.
- New `.agent.toml` fields: `effort`, `maxTurns`, `disallowedTools` for fine-grained agent configuration.
- CC v2.1.76-2.1.78 compatibility update.

### Bump
- Version 2.4.5 → 2.4.6

## [2.4.5] - 2026-03-16

### Features

- Add Role-Plugin naming convention and triple-match rule to .agent.toml schema

### Bump

- Version 2.4.4 → 2.4.5

## [2.4.4] - 2026-03-16

### Bug Fixes

- Condense pss-usage SKILL.md references to pass 4000-char validation limit

### Features

- Add rule file indexing (index-rules, list-rules) for agent profiling

### Bump

- Version 2.4.3 → 2.4.4

## [2.4.3] - 2026-03-16

### Bug Fixes

- Audit fixes for composite key migration
- Prevent HashMap collision by keying SkillIndex on entry ID instead of name

### Bump

- Version 2.4.2 → 2.4.3

## [2.4.2] - 2026-03-16

### Bug Fixes

- Composite primary key (name, source) in CozoDB skills table

### Miscellaneous Tasks

- Update uv.lock

### Bump

- Version 2.4.1 → 2.4.2

## [2.4.1] - 2026-03-16

### Features

- Smart namespace-aware lookup for get-description
- Support plugin@marketplace:element namespace convention

### Bump

- Version 2.4.0 → 2.4.1

## [2.4.0] - 2026-03-16

### Features

- Add get-description command for element metadata retrieval

### Bump

- Version 2.3.60 → 2.4.0

## [2.3.60] - 2026-03-15

### Bug Fixes

- Merge chunk-reading and message-finding into single loop

### Miscellaneous Tasks

- Update uv.lock

### Bump

- Version 2.3.59 → 2.3.60

## [2.3.59] - 2026-03-15

### Bug Fixes

- Replace readlines() with seek-based tail for transcript reading

### Bump

- Version 2.3.58 → 2.3.59

## [2.3.58] - 2026-03-15

### Bug Fixes

- Update LLM Externalizer MCP tool prefix to plugin format

### Bump

- Version 2.3.57 → 2.3.58

## [2.3.57] - 2026-03-15

### Miscellaneous Tasks

- Update uv.lock

### Bump

- Version 2.3.56 → 2.3.57

## [2.3.56] - 2026-03-15

### Features

- Gate user-visible suggestions on --debug mode

### Bump

- Version 2.3.55 → 2.3.56

## [2.3.55] - 2026-03-14

### Features

- Integrate LLM Externalizer MCP for token-efficient agent profiling

### Miscellaneous Tasks

- Update uv.lock

### Bump

- Version 2.3.54 → 2.3.55

## [2.3.54] - 2026-03-11

### Documentation

- Document installed_plugins.json v2 format

### Miscellaneous Tasks

- Update uv.lock

### Bump

- Version 2.3.53 → 2.3.54

## [2.3.53] - 2026-03-11

### Bug Fixes

- Audit round 3 — pss_reindex.py hardening

### Miscellaneous Tasks

- Update uv.lock

### Bump

- Version 2.3.52 → 2.3.53

## [2.3.52] - 2026-03-10

### Miscellaneous Tasks

- Update uv.lock before refactor

### Refactor

- Remove 428 lines of redundant Python context detection

### Bump

- Version 2.3.51 → 2.3.52

## [2.3.51] - 2026-03-10

### Bug Fixes

- Remove redundant 13MB JSON parse from Python hook

### Miscellaneous Tasks

- Update uv.lock

### Bump

- Version 2.3.50 → 2.3.51

## [2.3.50] - 2026-03-10

### Bug Fixes

- Increase binary subprocess timeout from 2s to 4s

### Miscellaneous Tasks

- Update uv.lock

### Bump

- Version 2.3.49 → 2.3.50

## [2.3.49] - 2026-03-10

### Bug Fixes

- Remove last 2 phantom wasm32 platform references

### Bump

- Version 2.3.48 → 2.3.49

## [2.3.48] - 2026-03-10

### Bug Fixes

- Deep audit round 2 — obsolete AI refs, TOCTOU, path traversal, phantom wasm32, pipeline timeout

### Bump

- Version 2.3.47 → 2.3.48

## [2.3.47] - 2026-03-10

### Bug Fixes

- Audit fixes — TOCTOU race, platform detection, corrupt index handling, docs sync

### Bump

- Version 2.3.46 → 2.3.47

## [2.3.46] - 2026-03-10

### Bug Fixes

- Add --exclude-inactive-plugins flag to discovery and reindex

### Miscellaneous Tasks

- Sync uv.lock with current version 2.3.45

### Bump

- Version 2.3.45 → 2.3.46

## [2.3.45] - 2026-03-10

### Bug Fixes

- Add --index-only-this-project flag to pss-reindex-skills command

### Bump

- Version 2.3.44 → 2.3.45

## [2.3.44] - 2026-03-10

### Bug Fixes

- Crash-safe reindex with atomic index swap and corrupt detection

### Bump

- Version 2.3.43 → 2.3.44

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
