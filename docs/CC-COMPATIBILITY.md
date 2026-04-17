# Claude Code Compatibility

PSS (Perfect Skill Suggester) is tested against Claude Code **2.1.69 → 2.1.112**. This
document tracks every CC release that has touched PSS's dependency surface since
v2.1.45, and records whether PSS is affected, adapted, or immune.

> **Scope note:** the project-root `CLAUDE.md` file is user-managed and gitignored
> (see `.gitignore`). This file is the authoritative, tracked record of PSS's CC
> compatibility posture.

## Declared hook events

As of **v2.9.35**, PSS declares the following hook events in `hooks/hooks.json`:

| Event | Matcher | Handler | Purpose |
|-------|---------|---------|---------|
| `UserPromptSubmit` | (none) | `scripts/pss_hook.py` | Primary — scores skill suggestions on every user prompt |
| `SessionStart` | `startup\|resume` | `scripts/pss_hook.py --warm-index &` | Silent lazy warmup — spawns a background reindex if the skill-index cache is missing, so the first prompt never blocks on index build |
| `PostCompact` | (none) | `scripts/pss_hook.py --post-compact` | Stub — reserves the event binding for future re-suggest-after-compaction logic |

All three hooks use `timeout` values in **seconds** (per hooks.md spec).
`UserPromptSubmit` uses 10s, `SessionStart` uses 5s, `PostCompact` uses 5s.

**Not declared (intentional):**
- `PreCompact` (CC v2.1.105+) — PSS has no reason to block compaction, so this
  event is not registered. The `PostCompact` stub is kept because PSS may
  re-suggest skills after a compaction cycle in the future.
- `StopFailure` (CC v2.1.78+) — PSS doesn't run as a subagent that the user
  would want to catch errors from.
- `FileChanged` / `CwdChanged` (CC v2.1.83+) — PSS re-suggests on every
  `UserPromptSubmit` which already covers directory-change scenarios.

## Hook input/output schema

- **Input from CC → Python hook**: `scripts/pss_hook.py` reads `transcript_path` (snake_case),
  matching the `hooks.md` "Common input fields" spec.
- **Input from Python → Rust binary**: `scripts/pss_hook.py` passes `{prompt, cwd, transcript_path}` to
  the Rust scorer as a JSON dictionary. Field names are snake_case. The Rust `HookInput`
  struct in `rust/skill-suggester/src/main.rs` deserializes with default serde naming (no
  `rename_all` applied).
- **Output from Rust binary → CC**: `HookOutput` and `HookSpecificOutput` structs keep
  `#[serde(rename_all = "camelCase")]` because CC expects hook-reply JSON keys in
  camelCase (`hookSpecificOutput`, `hookEventName`, `additionalContext`).

## PSS v3.0.0 — BREAKING CHANGE: JSON → CozoDB canonical migration

**PSS v3.0.0** (Phase C of the CozoDB unification migration,
TRDD-46ac514e) completes the single-store refactor:

- **`skill-index.json` is no longer auto-maintained.** Every write path in
  `pss_merge_queue.py` now targets CozoDB exclusively. Users who want a
  JSON snapshot for `git diff` run `pss export --json` on demand.
- **Rust `--build-db` flag is removed.** `pss --build-db` now exits with
  "unexpected argument" — CozoDB is populated by the Python merge writer,
  not by a separate Rust subcommand.
- **`pycozo[embedded]>=0.7.6` is a hard dependency.** The `pyproject.toml`
  lists it; a fresh install handles this automatically. Existing installs
  that skipped pycozo (legacy dev environments) must install it or the
  hook exits with an informational warning.
- **No user-facing behaviour change in the runtime hook.** The hook still
  reads CozoDB, latency and suggestion quality are unchanged.
- **Migration safety.** Upgrading from v2.10.x to v3.0.0 requires no user
  action: `pss_hook.py`'s health check detects a missing-or-empty CozoDB
  and auto-spawns a background reindex (same UX as first-install).

Affected scripts: `pss_hook.py`, `pss_merge_queue.py`, `pss_reindex.py`,
`pss_make_plugin.py`, `pss_verify_profile.py`, `pss_generate.py`, plus
Rust `src/main.rs` (`run_build_db` removed).

See `design/tasks/TRDD-46ac514e-3627-44a6-b916-f37a1504b969-cozodb-unification.md`
for the full design record.

## Version-by-version compatibility matrix

### v2.1.112 (2026-04-17)
- Maintenance release with no documented new features.
- **PSS impact**: none.

### v2.1.111 (2026-04-16)
- **New `xhigh` effort level** for Opus 4.7 (between `high` and `max`). Other models
  silently fall back to `high`. Configurable via `--effort`, `CLAUDE_CODE_DEFAULT_EFFORT`,
  the `/effort` interactive slider, or the `effort:` field in agent frontmatter.
- **Auto mode no longer requires `--enable-auto-mode`** — the switch is now always
  available by default.
- **PowerShell tool on Linux/macOS** — opt-in via `CLAUDE_CODE_USE_POWERSHELL_TOOL=1`
  env var; requires `pwsh` on PATH.
- New `/less-permission-prompts`, `/ultrareview`, `/effort` built-in commands/skills.
- `/skills` menu adds token-count sort.
- Headless `--output-format stream-json` now includes `plugin_errors` on the init event.
- `.claude/rules/` can be split from `CLAUDE.md`.
- Plan files are renamed after prompt content for later re-identification.
- `OTEL_LOG_RAW_API_BODIES` env var for telemetry.
- **PSS impact**: `.agent.toml` schema `effort` enum extended to include `xhigh`
  (`schemas/pss-agent-toml-schema.json` + `scripts/pss_validate_agent_toml.py`). The
  profiler can now emit `effort = "xhigh"` for Opus-targeted profiles; non-Opus-4.7
  models fall back to `high` automatically, so the field is backward-compatible. The
  built-in `/less-permission-prompts` and `/ultrareview` commands are automatically
  indexed via the existing commands-index scan. PSS's rule indexer already handles
  both `CLAUDE.md` and `.claude/rules/` so the split introduced in v2.1.111 is a
  no-op for PSS. PSS headless mode cleanly loads with no `plugin_errors` surfaced.

### v2.1.110 (2026-04-15)
- Maintenance release with no documented new features.
- **PSS impact**: none.

### v2.1.109 (2026-04-15)
- Improved extended-thinking indicator with a rotating progress hint.
- **PSS impact**: none (UI only).

### v2.1.108 (2026-04-14)
- Added `ENABLE_PROMPT_CACHING_1H` env var (1-hour prompt cache TTL) and
  `FORCE_PROMPT_CACHING_5M` (force 5-minute TTL). `ENABLE_PROMPT_CACHING_1H_BEDROCK`
  is deprecated but still honored.
- Added `/recap` slash command and "recap" feature for returning to a session.
  Configurable via `/config` and `CLAUDE_CODE_ENABLE_AWAY_SUMMARY` env var.
- **Model can now discover and invoke built-in slash commands via the Skill tool**
  (`/init`, `/review`, `/security-review`).
- `/undo` is now an alias for `/rewind`.
- `/model` warns before mid-conversation switches (next response re-reads full
  history uncached).
- `/resume` picker defaults to sessions from current directory; press `Ctrl+A` for
  all projects.
- Fixed policy-managed plugins never auto-updating when running from a different
  project than where first installed.
- **PSS impact**: none. PSS indexes built-in slash commands via the skill-index
  and already scores `/init`, `/review`, `/security-review` alongside plugin
  commands — now their Skill-tool-invocable status makes them more valuable
  candidates. The existing scoring is unaffected.

### v2.1.107 (2026-04-14)
- Thinking hints appear sooner during long operations.
- **PSS impact**: none (UI only).

### v2.1.105 (2026-04-13)
- **`PreCompact` hook event.** Hooks can now block compaction by exiting with
  code 2 or returning `{"decision":"block"}`.
- **Background monitor support via top-level `monitors` manifest key.** Auto-arms
  at session start or on skill invoke (new plugin.json top-level field).
- **Skill description listing cap raised from 250 to 1,536 characters.** A startup
  warning is shown when descriptions are truncated.
- Added `path` parameter to `EnterWorktree` tool (switch into an existing worktree).
- `/proactive` is now an alias for `/loop`.
- Improved stalled API stream handling: streams abort after 5 minutes of no data
  and retry non-streaming.
- Improved `WebFetch` to strip `<style>` and `<script>` from fetched pages.
- Improved `/doctor` layout with status icons; press `f` to have Claude fix issues.
- Fixed marketplace plugins with `package.json` + lockfile not having dependencies
  installed after install/update.
- Fixed marketplace auto-update leaving the official marketplace in a broken state
  when a plugin process holds files open during update.
- **PSS impact**: `PreCompact` is a new hook event PSS could consume — currently
  PSS declares `UserPromptSubmit` / `SessionStart` / `PostCompact` only. No action
  needed: PSS has no reason to block compaction. Added as a future enhancement.
  Skill description cap raise is still inside PSS's safety margin (60 chars max,
  cap now 1,536). **`monitors` manifest key is now supported as a pass-through
  field** in `.agent.toml` (adopted in v2.9.38 alongside `userConfig`): users who
  want to generate plugins with background monitors can declare a `[monitors]`
  table in their profile and `/pss-make-plugin-from-profile` will copy it verbatim
  into the generated `plugin.json`.

### v2.1.102 (2026-04-10)
- Maintenance release; no specific changelog entries.
- **PSS impact**: none.

### v2.1.101 (2026-04-10)
- `/team-onboarding` command, OS CA store trust, brief/focus mode improvements.
- **PSS impact**: none.

### v2.1.98
- `/reload-plugins` command, Monitor tool, `CLAUDE_CODE_PERFORCE_MODE`, Vertex wizard.
- **PSS impact**: none. PSS is already stateless at the skill-index level — `/reload-plugins`
  picks up new skills without restart because PSS re-reads the skill-index.json cache on
  every `UserPromptSubmit`.

### v2.1.97
- NO_FLICKER rendering, focus view, status line `refreshInterval`.
- **PSS impact**: cosmetic, none.

### v2.1.94
- `hookSpecificOutput.sessionTitle` on `UserPromptSubmit`.
- `disallowedTools` agent frontmatter.
- `keep-coding-instructions` for output styles.
- **PSS impact**: none yet. The `sessionTitle` field is available as a future enhancement
  but PSS does not currently set it.

### v2.1.92
- Removed `/tag` and `/vim` commands.
- `forceRemoteSettingsRefresh` policy.
- **PSS impact**: none.

### v2.1.91
- **New `disableSkillShellExecution` setting**. When a user enables this, CC blocks
  skills from invoking shell via `!` blocks in SKILL.md.
- Plugin `bin/` executables officially supported.
- **PSS impact**: **immune**. Verified 2026-04-12: every `commands/*.md` in PSS is
  prompt-based with ZERO `!` bash invocations or `scripts/pss_*.py` calls. The primary
  data paths (pss_hook.py, pss_reindex.py) run via the hooks system, not the
  skill-shell-execution guard.

### v2.1.90
- `PermissionDenied` hook event.
- `defer` permission decision in PreToolUse.
- Named subagents in `@` typeahead.
- **Official `skills:` subagent frontmatter** — now used by `agents/pss-agent-profiler.md`
  for CC-native skill pre-loading (alongside the PSS-internal `auto_skills:` which has
  distinct pinning semantics for `.agent.toml` generation).

### v2.1.89
- Hook output >50K chars saved to disk.
- `file_path` now absolute in Pre/PostToolUse hooks.
- Autocompact thrash loop detection.
- **PSS impact**: PSS hook output is <5 lines so the spillover is unaffected. PSS does
  not use Pre/PostToolUse hooks.

### v2.1.86
- **Skill description capped at 250 chars.** (Raised to 1,536 in v2.1.105.)
- **PSS impact**: PSS's longest skill description is 60 chars — comfortably within
  both the old 250-char limit and the new 1,536-char limit. Verified 2026-04-12.

### v2.1.85
- JSONL transcript format change: `agentId` removed; `sourceToolAssistantUUID` and
  `toolUseResult` added to user messages.
- **PSS impact**: `pss_hook.py:_extract_prev_msg_python()` and the Rust
  `extract_prev_user_message` code both skip tool-result entries via a pre-filter.

### v2.1.84
- PowerShell tool, `TaskCreated` hook, `WorktreeCreate` hook, paths-list YAML.
- **PSS impact**: none.

### v2.1.83
- `CwdChanged` / `FileChanged` hooks.
- `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`.
- `TaskOutput` deprecation.
- `managed-settings.d/` drop-in directory.
- **PSS impact**: PSS doesn't use `TaskOutput`. `managed-settings.d/` support is
  available as a future enterprise feature.

### v2.1.78
- **`${CLAUDE_PLUGIN_DATA}` for persistent plugin state**.
- `effort` / `maxTurns` / `disallowedTools` agent frontmatter.
- `StopFailure` hook event.
- **PSS impact**: `scripts/pss_paths.py:get_data_dir()` prefers `$CLAUDE_PLUGIN_DATA`
  when set, falling back to `~/.claude/cache/`. The profiler uses `effort: high` +
  `maxTurns: 40` for reasoning quality and runaway-loop guards.

### v2.1.77
- `claude plugin validate` checks frontmatter + hooks.json.
- `--keep-data` on uninstall.
- `SendMessage` auto-resumes agents.
- **PSS impact**: none.

### v2.1.76
- `PostCompact` hook.
- MCP elicitation support, `Elicitation` / `ElicitationResult` hooks.
- **PSS impact**: PSS's `PostCompact` hook (currently a no-op stub) uses this event.

### v2.1.72
- `/reload-plugins` command.
- **PSS impact**: users can reload PSS without restarting CC.

### v2.1.71
- `agent_id` / `agent_type` fields in hook events.
- `${CLAUDE_SKILL_DIR}` variable for skills.
- **PSS impact**: none (PSS skills don't use the variable yet).

### v2.1.69
- **installed_plugins.json v2 format.** Root `"version": 2`; each plugin key maps to a
  **list** of `{scope, installPath, version, installedAt, lastUpdated, gitCommitSha}`.
- HTTP hooks support.
- **PSS impact**: `scripts/pss_make_plugin.py` writes plugin metadata in v2 format.
  The v2 schema is not currently documented in the public `plugins-reference.md` — this
  is a reverse-engineered schema from CC source. Confirmed working as of CC v2.1.101.

### v2.1.50
- `context: fork` in skill frontmatter.
- `agent` field in skills.
- Auto skill hot-reload.
- **PSS impact**: PSS does not currently use `context: fork` on any skill. A previous
  attempt to enable it on `skills/pss-agent-toml/SKILL.md` was reverted in v2.9.35
  because pss-agent-toml is pre-loaded into pss-agent-profiler's context via `skills:`
  frontmatter — the fork semantics don't apply to pre-loading, so the field was inert.

### v2.1.45
- `memory` frontmatter for agents.
- **PSS impact**: `agents/pss-agent-profiler.md` uses `memory: user` for persistent
  learnings across profiling sessions.

## Rule path-scoping (`paths:` frontmatter)

As of **v2.9.35**, PSS supports the CC rules spec's `paths:` frontmatter field on rule
files under `~/.claude/rules/*.md` and `.claude/rules/*.md`. When a rule declares:

```yaml
---
paths:
  - "**/*.py"
  - "src/**"
---
```

PSS extracts the extension component of each glob (e.g. `py`) and compares it against
the project's detected file types (`context_file_types` in the hook input). A rule is
suggested only when at least one of its declared extensions matches. Non-extension
globs (e.g. `src/**`, `Dockerfile*`) pass permissively because full cwd glob matching
is not yet implemented.

**Migration**: existing rule entries in the skill-index will have empty `path_gates`
and behave as before until the user runs `/pss-reindex-skills` to re-enrich them.

## How to verify PSS compatibility with a new CC release

1. Read the release notes at https://code.claude.com/docs/en/changelog.md
2. Check the version's notes for any of:
   - hook events (new/renamed/removed)
   - hook input/output schema changes
   - agent or skill frontmatter changes
   - plugin.json or marketplace.json schema changes
   - env var renames (especially `$CLAUDE_PLUGIN_*`)
3. Grep the PSS codebase for anything referencing changed fields: `grep -r transcriptPath
   scripts/ hooks/ rust/` etc.
4. Run `uv run python scripts/publish.py --gate` to run the full lint + test + plugin
   validation suite.
5. If anything changed, update this file and the CC test matrix in `tests/`.
