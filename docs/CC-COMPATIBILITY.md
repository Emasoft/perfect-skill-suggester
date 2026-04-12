# Claude Code Compatibility

PSS (Perfect Skill Suggester) is tested against Claude Code **2.1.69 → 2.1.101**. This
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

## Version-by-version compatibility matrix

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
- **Skill description capped at 250 chars.**
- **PSS impact**: PSS's longest skill description is 60 chars — all 6 skills comply.
  Verified 2026-04-12 (see `docs_dev/20260412-edit-sites-exploration.md`).

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
