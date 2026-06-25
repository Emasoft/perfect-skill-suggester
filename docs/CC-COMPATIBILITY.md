# Claude Code Compatibility

PSS (Perfect Skill Suggester) is tested against Claude Code **2.1.69 → 2.1.191**. This
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
- `MessageDisplay` (CC v2.1.152+) — lets a hook transform or hide assistant
  message text as it's displayed. PSS suggests skills via `additionalContext`
  on `UserPromptSubmit`; it has no reason to rewrite Claude's rendered output,
  so this event is not registered.

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

### v2.1.191 (2026-06-24)
- **Fix: hooks with comma-separated matchers (e.g. `"Bash,PowerShell"`) silently never firing** — PSS is immune: its only matcher is `SessionStart: startup|resume` (regex alternation via a pipe `|`, which always fired); PSS declares no comma-separated matchers (verified in `hooks/hooks.json`).
- **MCP capability discovery (`tools/list` / `prompts/list` / `resources/list`) and OAuth now retry transient network errors, and HTTP 404 names the URL + points to the MCP config** — beneficial: `pss-agent-profiler`'s two `llm-externalizer` MCP tools connect more reliably; PSS already degrades to direct file reads when that MCP is absent, so no PSS change.
- Streaming CPU −37%, long-session memory reduction, `/rewind` after `/clear`, and permanent background-agent stop — no PSS impact.

### v2.1.187 (2026-06-23)
- **Fix: remote MCP tool calls that hang for 5 minutes now abort with an error (override `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT`)** — beneficial for the profiler's `llm-externalizer` MCP calls; no PSS change.
- **`Agent(type)` deny rules and `Agent(x,y)` allowed-types now enforced for named subagent spawns** — relevant: a host can now gate `pss-agent-profiler` by type/param; PSS ships no such rule and the profiler is a leaf agent.
- **Fix: `--json-schema` / Workflow `agent({schema})` structured output no longer lets the model re-call `StructuredOutput` indefinitely** — N/A to PSS (ships no Workflow scripts; the profiler uses plain tool calls, not StructuredOutput).
- `sandbox.credentials`, org-configured model restrictions on the picker / `--model` / `/model` / `ANTHROPIC_MODEL`, and optional `/install-github-app` workflow setup — no PSS impact (PSS pins no model; the profiler inherits the session model).

### v2.1.186 (2026-06-22)
- **Skill frontmatter `display-name` / `default-enabled` / `fallback` / `metadata.*` keys now accept kebab-case, snake_case, and camelCase** — PSS is immune: discovery reads only the standard lowercase `name`, `description`, and `metadata` keys (`pss_discover.py`), none of the case-flexible ones (verified).
- **Malformed `SKILL.md` YAML frontmatter now loads the body with empty metadata instead of failing silently** — PSS already matches this behavior: `parse_frontmatter` catches `yaml.YAMLError`, warns on stderr, and returns `{}` (the V-8 audit fix), so a broken-frontmatter skill indexes body-only instead of aborting discovery (verified). Such skills now load in CC, and PSS handles them the same way.
- **`!` bash output now auto-prompts a model response (set `respondToBashCommands: false` to opt out)** — no PSS behavior change: PSS's three hooks issue no `!` bash commands; the new default concerns interactive user `!` usage only.
- A "Skills" section in `/plugin`'s Installed tab; `/plugin` surfacing stale plugins; `CLAUDE_CODE_MAX_RETRIES` capped at 15; `/review <pr>` reusing the `/code-review medium` engine; named-subagent permission prompts now surfacing in the main session — informational; PSS contributes 6 skills + 1 agent to these surfaces.

### v2.1.185 (2026-06-20) — stream-stall hint wording/timing only; no plugin surface. No PSS impact.

### v2.1.184 / v2.1.188 / v2.1.189 / v2.1.190 — bug-fix / reliability-only releases with no plugin-ecosystem surface. No PSS impact.

### v2.1.183 (2026-06-19)
- **Fix: WebSearch returning empty results inside subagents** — directly relevant: `pss-agent-profiler` declares `WebSearch` in its `tools:` allowlist (used to research a skill/agent's domain during profiling), so this fix restores correct research in profiling runs; PSS needs no change to benefit.
- **Fix: `thinking.disabled.display: Extra inputs are not permitted` 400 errors on subagent spawns and session-title generation** — informational; this affected any subagent launch (including `pss-agent-profiler`) and is resolved entirely CC-side.
- **Fix: user-level skills appearing multiple times in slash-command autocomplete when several plugins are enabled** — cosmetic but relevant: PSS's `/pss-*` commands no longer risk duplicate autocomplete entries on multi-plugin hosts; no PSS-side change.
- Scheduled-task and webhook-trigger deliveries are now classified as task-notifications (not keyboard input) and can no longer approve a pending action or set the session title in auto mode — no PSS impact; PSS schedules no cron jobs (this concerns the separate ai-maestro-janitor heartbeat, not PSS).
- **Fix: MCP servers requiring auth exposing auth-stub tools to the model in headless/SDK mode** — informational; `pss-agent-profiler` references two `llm-externalizer` MCP tools and already degrades gracefully (direct file reads) when that MCP is absent.

### v2.1.181 (2026-06-17)
- Foreground subagents now respect the same 5-level depth limit as background subagents — informational: `pss-agent-profiler` is a leaf subagent that spawns none, so the cap never binds.
- **Fix: agent creation failing with `EEXIST: file already exists` when the agents directory already exists (Windows/OneDrive)** — beneficial for installing PSS (which ships `agents/pss-agent-profiler.md`) on Windows/OneDrive; no PSS-side change.
- New `/config key=value` prompt syntax, MCP `! Connected · tools fetch failed` status, and `~/.claude/settings.json` relative-symlink ENOENT fixes — no PSS impact.

### v2.1.179 (2026-06-16)
- **Improved plugin loading performance in remote sessions** — beneficial: PSS (its `UserPromptSubmit` hook, skills, `pss-agent-profiler` agent, and slash commands) loads faster in remote sessions; no PSS-side change.
- `Ctrl+O` not showing the subagent's transcript fix and assorted terminal/UI fixes — no PSS impact.

### v2.1.178 (2026-06-15)
- New `Tool(param:value)` permission-rule syntax (with `*` wildcard) matches a tool's input parameters, e.g. `Agent(model:opus)` to block Opus subagents — relevant: a user can now write a permission rule targeting PSS's `pss-agent-profiler` by parameter (e.g. allow only `Agent(subagent_type:pss-agent-profiler)`); PSS ships no such rule itself.
- Skills in nested `.claude/skills` directories now load when working on files there; on a name clash the nested skill is exposed as `<dir>:<name>` so both stay available — **PSS currently indexes the project-ROOT `.claude/skills` only** (`pss_discover.py` scans `cwd/.claude`), NOT per-subtree nested `.claude/skills`. This is a deliberate product decision, not an oversight: PSS's flat global index feeds a per-prompt suggester that has no working-file context, so globally indexing subtree-scoped skills would surface them on prompts *outside* their intended subtree and erode suggestion precision (PSS's core value). Context-aware nested-skill discovery (scoping a nested skill to prompts whose cwd is under its subtree) is a tracked future enhancement. *(Corrected 2026-06-25: a prior revision of this entry wrongly asserted PSS "already scans nested `.claude/skills`" — verified false against `pss_discover.py`, which scans only the root project `.claude`.)*
- Nested `.claude/` directories: the agent/workflow/output-style closest to the working directory now wins on a name collision — informational; aligns with PSS's most-specific-scope-wins discovery model.
- **Fix: MCP server-level specs (`mcp__server`, `mcp__server__*`, `mcp__*`) in a subagent's `disallowedTools` being silently ignored** — PSS's `pss-agent-profiler` uses an **allowlist** `tools:` (Bash/Read/Write/Edit/Glob/Grep/WebSearch/WebFetch + two `llm-externalizer` MCP tools), not `disallowedTools`, so the bug never applied to PSS.
- **Fix: nested `.claude/skills` skills with directory-qualified names blocked by permission prompts in non-interactive runs** — relevant to any project-scoped skill PSS indexes; no PSS-side change.
- Auto mode now evaluates subagent spawns with the classifier before launch, and the skill-listing truncation warning now reports how many skill descriptions are affected — informational; PSS contributes 6 skills to that listing.

### v2.1.176 (2026-06-12)
- **Fix: hook `if` conditions for Read/Edit/Write tool paths (`Edit(src/**)`, `Read(~/.ssh/**)`, `Read(.env)`) now match correctly** — PSS's three hooks declare no `if` conditions, so this is informational for PSS.
- Remaining items (conversation-language session titles, `footerLinksRegexes`, Bedrock credential caching, `availableModels` enforcement, Linux-sandbox symlink, tmux `/copy`, Remote Control, `/cd` branch) — no PSS impact.

### v2.1.175 (2026-06-12)
- `enforceAvailableModels` managed setting constrains the Default model to the `availableModels` allowlist — no PSS impact (PSS pins no model; `pss-agent-profiler` inherits the session model).

### v2.1.174 (2026-06-12)
- **Fix: skill hot-reload re-sending the entire skill listing when a single skill changed — only changed skills are now re-announced** — relevant: when `/pss-reindex-skills` rewrites PSS's own skills, CC now re-announces just the changed entries instead of the whole listing, a small latency win at reindex time.
- [VSCode] `/usage` now attributes cost per-skill/agent/plugin/MCP over 24h/7d — informational: PSS's hook + `pss-agent-profiler` now surface as line items so users can see PSS's token footprint.
- `wheelScrollAccelerationEnabled`, `/model` picker fixes, Fable 5 banner, Bedrock GovCloud, Workflow `agent()` attribution — no PSS impact.

### v2.1.173 (2026-06-11)
- Fable 5 `[1m]`-suffix normalization and a Windows spurious-sandbox-warning fix — no PSS impact (model-name handling / Windows sandbox).

### v2.1.172 (2026-06-10)
- Sub-agents can now spawn their own sub-agents (up to 5 levels deep) — informational: `pss-agent-profiler` is a leaf subagent that spawns none, so PSS neither benefits nor regresses.
- Added a marketplace plugin search bar in `/plugin` — informational; eases discovery of the PSS marketplace listing.
- **Fix: `WebFetch(domain:*.example.com)` wildcard domain rules and file-permission rules with mid-pattern wildcards (`Read(secrets-*/config.json)`) being rejected at startup** — informational; `pss-agent-profiler` has `WebFetch` in its toolset but ships no such rules.
- **Fix: workflow validation rejecting scripts whose prompt strings merely mention `Date.now()`/`Math.random()`** — N/A (PSS ships no Workflow scripts).

### v2.1.170 (2026-06-09)
- **Claude Fable 5 introduced** (Mythos-class) — relevant: `pss-agent-profiler` omits a `model:` pin and inherits the session model, so Fable 5 is usable for profiling automatically with no PSS change.
- **Fix: sessions not saving transcripts (and not appearing in `--resume`) when launched from the VS Code integrated terminal or any shell that inherited Claude Code env vars** — directly relevant: PSS's hot path reads `transcript_path` via the Rust `--extract-prev-msg` mmap scan to recover the previous user message; before this fix a VS-Code-terminal session could have an unwritten transcript, leaving that scan empty. PSS already degrades gracefully (no prev-message augmentation) in that case, but the fix restores full behavior.

### v2.1.169 (2026-06-08)
- New `--safe-mode` flag and `CLAUDE_CODE_SAFE_MODE` env var start CC with all customizations (CLAUDE.md, plugins, skills, hooks, MCP) disabled — relevant as a **troubleshooting** lever: launching with `--safe-mode` disables PSS entirely, a clean way for a user to confirm whether PSS's `UserPromptSubmit` hook is implicated in a problem.
- **Fix: `claude -p` slow/hanging on Windows while waiting for the slash-command/skill scan (regression in 2.1.161)** — relevant: PSS contributes 6 skills + 8 commands to that scan, so headless PSS users on Windows are unblocked.
- **Fix: plugin `.in_use` PID lock files accumulating without bound — stale markers are now swept once per day** — informational; affects PSS's plugin-cache footprint, no PSS code change.
- `disableBundledSkills` / `CLAUDE_CODE_DISABLE_BUNDLED_SKILLS` hides bundled (built-in) skills — does not affect PSS, which is a marketplace plugin, not a bundled skill.
- "CLAUDE.md too long" warning threshold now scales with the model's context window — informational.

### v2.1.168 (2026-06-06)
- Bug fixes and reliability improvements — no PSS-specific impact.

### v2.1.167 (2026-06-06)
- Bug fixes and reliability improvements — no PSS-specific impact.

### v2.1.166 (2026-06-06)
- `fallbackModel` setting (up to three fallbacks) and glob support in deny-rule tool-name position — informational; no PSS change.
- **Hardened cross-session messaging: `SendMessage`-relayed messages no longer carry user authority** — N/A (PSS uses no cross-session messaging).

### v2.1.165 (2026-06-05)
- Bug fixes and reliability improvements — no PSS-specific impact.

### v2.1.163 (2026-06-04)
- **Skills: added `\$` escape syntax to include a literal `$` before a digit in command bodies** — relevant to PSS's `/pss-*` command bodies if any ever need a literal `$1`/`$2`; current commands don't, so informational.
- **Hooks: Stop and SubagentStop hooks can now return `hookSpecificOutput.additionalContext`** — informational; PSS declares no Stop/SubagentStop hook.
- **Fix: hook `if: "Bash(...)"` conditions firing on every Bash command containing `$()` or `$VAR`** — PSS hooks use no `if` conditions, so informational.
- `/plugin list` (with `--enabled`/`--disabled`), `requiredMinimumVersion`/`requiredMaximumVersion`, stdio-MCP `CLAUDE_CODE_SESSION_ID` on `--resume` — informational / N/A (PSS ships no MCP server).

### v2.1.162 (2026-06-03)
- **`--tools`: explicitly listing `Grep`/`Glob` now provides the dedicated search tools on native builds with embedded search (previously these names were silently ignored)** — relevant: `pss-agent-profiler` lists `Grep` and `Glob` in its `tools:`, so on native builds those now resolve to the fast embedded search tools.
- **Fix: WebFetch permission rules not applied to built-in preapproved domains** — informational; the profiler uses `WebFetch`.
- `/effort` persist confirmation, `claude mcp` secret redaction, LSP `workspaceSymbol` — N/A.

### v2.1.161 (2026-06-02)
- **Parallel tool calls: a failed `Bash` command no longer cancels the other calls in the same batch — each returns its own result** — relevant: `pss-agent-profiler` issues parallel `Bash` calls (e.g. building the binary path + running queries); a single failure no longer aborts the siblings.
- **Fix: background subagent output corrupting `claude -p` stdout under `--output-format text`/`json`** — informational; affects how a backgrounded `pss-agent-profiler` would interleave with headless output.

### v2.1.160 (2026-06-02)
- **Edit no longer requires a separate Read after viewing a file with `grep` — single-file `grep`/`egrep`/`fgrep` now satisfies the read-before-edit check** — relevant: `pss-agent-profiler` reads-then-edits `.agent.toml` files; this removes a redundant Read in its workflow.
- Removed `CLAUDE_CODE_OPUS_4_6_FAST_MODE_OVERRIDE` (now a no-op) — informational; the v2.1.142 PSS note referenced this env var, which is now retired.
- Added prompts before writing shell-startup / build-tool config files (`.zshenv`, `.npmrc`, etc.) — N/A; PSS hooks write none of these.

### v2.1.159 (2026-05-31)
- Internal infrastructure improvements (no user-facing changes) — no PSS impact.

### v2.1.158 (2026-05-30)
- Auto mode available on Bedrock/Vertex/Foundry for Opus 4.7/4.8 (`CLAUDE_CODE_ENABLE_AUTO_MODE=1`) — no PSS impact.

### v2.1.157 (2026-05-29)
- **Plugins in `.claude/skills` directories are now auto-loaded, no marketplace required**, plus `claude plugin init <name>` to scaffold one there — relevant: PSS's discovery already scans `.claude/skills`, so newly auto-loaded local skills become indexable; remind users to `/pss-reindex-skills` after dropping a skill there.
- `EnterWorktree` mid-session switching, `/plugin` arg autocomplete, `tool_decision` telemetry `tool_parameters` — informational / N/A.

### v2.1.156 (2026-05-29)
- **Fix: Opus 4.8 thinking blocks being modified, causing API errors** — informational; stability fix for the model `pss-agent-profiler` may inherit.

### v2.1.154 (2026-05-28)
- **Opus 4.8 released** (defaults to high effort; `/effort xhigh` for the hardest tasks) — relevant: `pss-agent-profiler` inherits the session model, so AI-mode profiling now runs on Opus 4.8 by default; matches the project convention that PSS fix/profiling agents are Opus-class.
- **Plugins can now declare `defaultEnabled: false` in `plugin.json` or a marketplace entry** — relevant decision: PSS deliberately **does not** set `defaultEnabled: false` — it is a suggestion engine that must run on every `UserPromptSubmit`, so it stays enabled-by-default on install.
- The lean system prompt is now the default for all models except Haiku/Sonnet/Opus 4.7-and-earlier — informational.
- Stdio MCP subprocesses now receive `CLAUDE_CODE_SESSION_ID` and `CLAUDECODE=1`; dynamic workflows; `/plugin` Discover directory-relevance pinning — N/A / informational (PSS ships no MCP server and no Workflow scripts).

### v2.1.153 (2026-05-28)
- **Fix: subagent (Agent tool) frontmatter MCP servers ignoring `--strict-mcp-config`, `--bare`, remote mode, enterprise managed MCP config, and managed-settings MCP allow/deny policies** — relevant: `pss-agent-profiler` declares two `llm-externalizer` MCP tools in frontmatter, which now correctly respect `--strict-mcp-config` and managed policies. PSS already falls back to direct file reading when those MCP tools are unavailable, so a now-correctly-blocked MCP server degrades gracefully.
- **`--strict-mcp-config` no longer strips inline `mcpServers` from explicitly-passed agent definitions; blocked subagent MCP servers now surface a visible warning** — same area; the warning makes a blocked `llm-externalizer` visible instead of silent.
- `skipLfs` marketplace sources, status-line `COLUMNS`/`LINES` — informational / N/A.

### v2.1.152 (2026-05-27)
- **Skills and slash commands can now set `disallowed-tools` in frontmatter to remove tools from the model while active** — a new capability PSS *could* adopt (e.g. restrict `pss-cli-reference` to `Bash`/`Read`); not adopted yet, noted as available.
- **`SessionStart` hooks can now return `reloadSkills: true` to re-scan skill directories**, and set the session title via `hookSpecificOutput.sessionTitle` — relevant context: PSS's `SessionStart` hook only **warms the index** (`--warm-index &`); it installs no skills mid-session and sets no title, so it returns neither field. If PSS ever installs a skill from a hook, `reloadSkills` is the right mechanism.
- **Added the `MessageDisplay` hook event** (transform/hide assistant text as displayed) — PSS does not register it (see "Not declared (intentional)" above).
- `/reload-skills` command, `pluginSuggestionMarketplaces` managed setting, `claude plugin marketplace remove --scope` — informational; `/reload-skills` lets users refresh after a `/pss-reindex-skills`.
- **Fix: plugin MCP servers with the same command but different env being incorrectly deduplicated; stale `enabledPlugins` `/doctor` warnings; git-branch-tracking plugins silently not updating** — informational; no PSS code change.

### v2.1.150 (2026-05-23)
- Internal infrastructure improvements (no user-facing changes) — no PSS impact.

### v2.1.149 (2026-05-22)
- **`/usage` now shows a per-category breakdown — skills, subagents, plugins, and per-MCP-server cost** — informational: PSS's hook-driven suggestions and `pss-agent-profiler` now appear as attributable usage line items.
- **Fix: argument-hint and progressive arg suggestions not appearing after Tab-completing a skill whose frontmatter `name:` differs from its directory basename** — verified non-issue for PSS: every PSS skill's `name:` equals its directory basename (e.g. `pss-cli-reference`).
- **Fix: status bar showing the baseline `/effort` instead of the effort applied by skill/agent `effort:` frontmatter** — informational; `pss-agent-profiler` sets no `effort:`, so it always reflected the baseline.

### v2.1.148 (2026-05-22)
- **Fix: the Bash tool returning exit code 127 on every command for some users (regression in 2.1.147)** — relevant: PSS's `UserPromptSubmit` hot path and `pss-agent-profiler` both shell out via Bash, so this regression could have broken PSS's hook dispatch on affected installs; the fix restores it.

### v2.1.147 (2026-05-21)
- **Fix: plugin component counts in `claude plugin details` and `/plugin` being doubled when a plugin's manifest listed paths overlapping its default directories** — validates a PSS design choice: PSS's `.claude-plugin/plugin.json` declares **no** explicit `skills:`/`agents:`/`commands:` keys (it relies on default `./skills/`, `./agents/`, `./commands/` discovery), so PSS never triggered the double-count.
- **Fix: plugin agents that declare multiple `Agent(...)` types in `tools:` frontmatter dropping all but the last** — N/A: `pss-agent-profiler` declares no `Agent(...)` entries in its `tools:`.
- **Fix: hook `if` conditions like `PowerShell(git push*)` never matching** — informational; PSS hooks use no `if` conditions.
- Renamed `/simplify` to `/code-review` — N/A.

### v2.1.145 (2026-05-19)
- **Fix: `context: fork` skills triggering infinite-loop re-invocation** — directly relevant; PSS ships `skills/pss-cli-reference/SKILL.md` with `context: fork` frontmatter. The skill is loaded by the `pss-agent-profiler` agent (not self-loading), so PSS was never at risk of the bug, but the fix removes a latent failure mode for any future PSS skill that opts into forked context.
- `claude agents --json` for scripting (informational; PSS ships its own `pss-agent-profiler` agent and never invoked `claude agents` programmatically).
- `/plugin` Discover/Browse pane now lists a plugin's skills/agents/commands/hooks **before install** — relevant: users browsing the PSS marketplace listing now see PSS's six skills, the `pss-agent-profiler` agent, and the eight `/pss-*` commands upfront without installing first.
- `claude plugin validate` now enforces that every entry in `plugin.json` `skills:` resolves to an existing directory — PSS's `.claude-plugin/plugin.json` declares no `skills:` key (verified 2026-05-19), uses default `./skills/` directory discovery, so the new strict validation never fails for PSS.
- `Stop` / `SubagentStop` hook input now includes `background_tasks` and `session_crons` arrays — PSS declares no `Stop` hook (only `UserPromptSubmit`, `SessionStart`, `PostCompact`), so the new fields are not consumed by PSS.

### v2.1.144 (2026-05-18)
- `/resume` background session support — sessions launched via `/bg` are now resumable through `/resume`, with a `[bg]` marker shown in the session list to distinguish background from interactive sessions. PSS's `SessionStart` hook fires on both `startup` and `resume` matchers, so resumed background sessions still warm the PSS index correctly.
- `/extra-usage` renamed to `/usage-credits` — cosmetic CC rename; PSS doesn't reference either slash command in its hooks, scripts, or docs (verified 2026-05-18).

### v2.1.143 (2026-05-16)
- **Fix: `--agent <name>` not finding plugin-contributed agents without the `plugin:` prefix** — directly relevant; PSS ships the `pss-agent-profiler` agent and users invoking `claude --agent pss-agent-profiler` now resolve it without needing the explicit `plugin:perfect-skill-suggester:pss-agent-profiler` form.
- **Fix: background sessions on macOS getting "Operation not permitted" reading files under `~/Documents`, `~/Desktop`, or `~/Downloads`, even with Full Disk Access granted** — relevant for users with project-scoped skills under those macOS-protected directories; PSS `_safe_read_text` discovery now succeeds on those paths from background sessions without code changes.
- Added plugin dependency enforcement (`claude plugin disable` refuses when another enabled plugin depends on the target; `enable` force-enables transitive deps) — PSS's `plugin.json` declares no `dependencies` field (verified 2026-05-16), so PSS is neither a holder nor a target of dependency chains and the new behavior never fires.
- Added projected context cost (per-turn and per-invocation token estimates) to the `/plugin` marketplace browse pane — PSS's marketplace listing now shows users an upfront cost estimate before install.
- New `worktree.bgIsolation: "none"` setting lets background sessions edit the working copy directly without `EnterWorktree` — PSS hooks operate inside whatever worktree CC creates, no PSS-side change.
- PowerShell tool now passes `-ExecutionPolicy Bypass` by default on Windows for Bedrock/Vertex/Foundry users (PSS hook spawns the native Rust binary via the dispatch shim, not PowerShell — N/A).
- **Fix: stop hooks that block repeatedly looping forever (turn now ends with a warning after 8 consecutive blocks, override via `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`)** — PSS declares no Stop hook (only `UserPromptSubmit`, `SessionStart`, `PostCompact`), so this doesn't apply to PSS.
- **Fix: `NO_COLOR`/`FORCE_COLOR` in settings.json env stripping Claude Code's own UI colors (they now apply to subprocesses only)** — PSS hook output is JSON, not color-formatted; informational.
- **Fix: worktree cleanup no longer falls back to `rm -rf` when `git worktree remove` fails** — defensive; no PSS impact.
- **Fix: `/bg` preserves `--mcp-config` / `--settings` / `--add-dir` / `--plugin-dir` / `--strict-mcp-config` / `--allow-dangerously-skip-permissions` / `--fallback-model` across respawn** — PSS doesn't depend on bg-session config preservation; informational.
- Numerous other `claude agents` / background-daemon fixes (Shift+Tab auto cycle, Esc/Ctrl+C cancellation of `/loop` wakeup, `←` in attached sessions, repeated PowerShell processes, stale-fragment rendering, false-positive stall detection storm, 5xx gateway naming, corrupt `.credentials.json` startup hang, Windows right-click paste, agent-view session-delete transcript cleanup, `~/.local/bin/claude` launcher fallback) — none affect PSS.

### v2.1.142 (2026-05-15)
- **Fix: plugin cache cleanup deleting the active plugin version directory when no installation metadata is present** — highly relevant; the PSS hook fires on every `UserPromptSubmit`, and a mid-session cleanup that removed the running version's directory would break it. This extends the v2.1.136 fix to also cover the case where install metadata is entirely absent.
- **Fix: configuring a prompt- or agent-type hook for `SessionStart`/`Setup`/`SubagentStart` now shows a clear "use a command-type hook instead" error** — PSS's `SessionStart` warm-index hook, plus its `UserPromptSubmit` and `PostCompact` hooks, are all `type: "command"` (verified 2026-05-15 in `hooks/hooks.json`), so the new error never fires for PSS.
- **Fix: redundant `set_model` requests from remote clients injecting duplicate `/model` breadcrumbs into the transcript** — relevant: PSS's transcript backward-scan (`pss_hook.py` → Rust `--extract-prev-msg`) walks JSONL entries for the previous user message, so a transcript with fewer spurious breadcrumb entries scans cleaner.
- **Fix: plugins using `skills: ["./"]` showing a false "path escapes plugin directory" error** — PSS's `plugin.json` declares no `skills` key (verified 2026-05-15), so PSS was never affected.
- **Fix: plugin advisories not naming every `plugin.json` key that shadows a default folder** — extends the v2.1.140 advisory to be exhaustive; PSS's `plugin.json` declares no folder-shadowing keys, so no advisory fires.
- Plugins with a root-level `SKILL.md` and no `skills/` subdirectory are now surfaced as a skill — PSS keeps all six skills under `skills/` and ships no root-level `SKILL.md` (verified 2026-05-15), so skill discovery is unchanged.
- `/plugin` details pane and `claude plugin details` now list a plugin's LSP servers — PSS ships none.
- **Fix: `/plugin` browse pane showing "0 installs" for newly published plugins** — cosmetic, corrects PSS's marketplace browse listing.
- Fast mode now defaults to Opus 4.7 (`CLAUDE_CODE_OPUS_4_6_FAST_MODE_OVERRIDE=1` pins 4.6).
- `MCP_TOOL_TIMEOUT` now correctly raises the per-request fetch timeout for remote HTTP/SSE MCP servers (PSS ships no MCP server — N/A).
- New `claude agents` background-session flags (`--add-dir`, `--settings`, `--mcp-config`, `--plugin-dir`, `--permission-mode`, `--model`, `--effort`, `--dangerously-skip-permissions`), a reactive-compaction seeding improvement, and numerous `claude agents` / background-daemon fixes (macOS sleep/wake reconnect, binary-upgrade crash-loop, Windows network-drive deadlock) — none affect PSS.

### v2.1.141 (2026-05-14)
- Hooks can emit terminal escape sequences (notifications, bells, window titles) via a new `terminalSequence` field in hook JSON output — PSS hook output stays informational (`<pss-skills>` block), no adoption planned.
- `CLAUDE_CODE_PLUGIN_PREFER_HTTPS` env var lets users clone GitHub plugin sources over HTTPS when no SSH key is available — PSS is listed via a `source: github` marketplace entry, so consumers on this env var get HTTPS transparently, no PSS-side change required.
- **Fix: hooks receiving non-existent `transcript_path` after `EnterWorktree` switches the working directory** — directly relevant because the PSS hook reads `transcript_path` and passes it to the Rust binary's `--extract-prev-msg` mmap scan; worktree-launched sessions now receive the corrected path automatically, no PSS code change needed.
- **Fix: a hook writing to the terminal could corrupt an on-screen interactive prompt** — hooks now run without terminal access. PSS hook writes JSON to stdout only and never touches `/dev/tty`, so the change is transparent.
- **Fix: `claude plugin install` failing for plugins whose marketplace `ref` no longer exists upstream when a `sha` is also pinned** — improves install-time fallback for PSS consumers pinned to specific SHAs.
- **Fix: background side-queries sending an unavailable Haiku model ID on Bedrock/Vertex/Foundry/gateway when no `ANTHROPIC_SMALL_FAST_MODEL` override is set** — auto-namer now falls back to the main-loop model; no PSS code path uses background side-queries, informational only.
- Agent panel adds `claude agents --cwd <path>` to scope the session list.
- Background agents launched via `/bg` / `←←` now preserve the current permission mode (PSS doesn't depend on this).
- `/feedback` can attach recent sessions (24 h or 7 d) for cross-session issue reports.

### v2.1.140 (2026-05-11)
- Plugins now warn when a default component folder (e.g. `commands/`) is silently ignored because `plugin.json` sets the matching key — PSS `plugin.json` declares only `name`/`version`/`description`/`author`/`homepage`/`repository`/`license`/`keywords` (verified 2026-05-11), so default folder discovery is preserved and no warning fires in `/doctor` or `claude plugin list`.
- Agent tool `subagent_type` now accepts case/separator-insensitive values (e.g. `"PSS Agent Profiler"` → `pss-agent-profiler`).
- `/goal` hang fix when `disableAllHooks` or `allowManagedHooksOnly` is set.
- `claude --bg` connection-drop fix.
- `/loop` redundant-wakeup elimination.
- Read tool `offset` validation now tolerates whitespace-padded / `+`-prefixed strings.

### v2.1.139 (2026-05-10)
- `claude agents` agent view + `/goal` command — users can now monitor PSS-suggested skill chains in a unified session list and pin a completion condition that survives multiple turns.
- `claude plugin details perfect-skill-suggester` reveals PSS's component inventory and projected per-session token cost.
- Hook `args: string[]` exec form (no-shell spawn) added — PSS hooks intentionally stay on the `command` string form because the SessionStart warm-index hook needs shell-level `&` backgrounding.
- Hook `continueOnBlock` is `PostToolUse`-only (PSS uses `UserPromptSubmit` — N/A).
- MCP stdio servers now receive `CLAUDE_PROJECT_DIR` (PSS ships no MCP server — N/A).
- **Fix: subagents now reliably discover project/user/plugin skills via the Skill tool** — `pss-agent-profiler` previously could miss skills mid-profiling; now safe.
- **Fix: `Skill(name *)` wildcard permission rules work as prefix match** — users writing rules for PSS-suggested skills get the expected matching semantics.
- `/context` shows the providing plugin's name for plugin-sourced skills — PSS skills (`pss-usage`, `pss-agent-toml`, etc.) now show `perfect-skill-suggester` attribution.
- Subagent API requests carry `x-claude-code-agent-id` / `x-claude-code-parent-agent-id` headers, and `claude_code.llm_request` OTel spans include matching attributes — useful for tracing `pss-agent-profiler` invocations.
- Compaction prompt now asks the model to preserve sensitive user instructions.

### v2.1.136 (2026-05-08)
- Added `settings.autoMode.hard_deny` for block-unconditionally rules.
- **Fix: plugin `Stop`/`UserPromptSubmit` hooks failing when cache cleanup deletes a version still in use by a running session** — highly relevant for PSS because the hook fires on every prompt; previously a mid-session PSS update could break the running hook, now resilient.
- **Fix: a `skills` entry in `plugin.json` hiding the plugin's default `skills/` directory** — PSS's `plugin.json` does NOT declare `skills`, so default discovery works correctly; verified no change needed.
- `--resume`/`--continue` underscore-in-path fix.
- Plugin slash commands with spaces (e.g. `/myplugin review`) resolve to namespaced form.
- `CronList` output now includes qualifiers and the scheduled prompt.

### v2.1.133 (2026-05-05)
- `worktree.baseRef` setting (`fresh` | `head`) — default reverts to `fresh` (`origin/<default>`); affects `--worktree` / `EnterWorktree` / agent-isolation worktrees (set `worktree.baseRef: "head"` to keep unpushed commits).
- Hooks now receive `effort.level` in JSON input and `$CLAUDE_EFFORT` env var; Bash tool commands can read `$CLAUDE_EFFORT`. PSS hook could theoretically scale max-suggestions by effort but Rust scoring is already constant-time and cheap, so no adoption planned.
- **Fix: subagents not discovering project/user/plugin skills** — same fix rolled forward at v2.1.139.
- Reduced memory by releasing warm-spare background workers under memory pressure.

### v2.1.132 (2026-05-04)
- `CLAUDE_CODE_SESSION_ID` env var on Bash subprocesses (matches the `session_id` already in PSS's hook stdin payload — no change required).
- `CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN`.
- Stdio MCP non-protocol-stdout memory leak fixed (PSS ships no MCP server — N/A).

### v2.1.129 (2026-05-01)
- Plugin manifests should declare `themes`/`monitors` under `"experimental": { ... }` — PSS plugin.json declares neither, so no migration needed.
- `skillOverrides` setting now functional (`off` / `user-invocable-only` / `name-only`); when a user sets it to `name-only` PSS suggestions still surface because they're injected via `additionalContext`, not via skill descriptions.

### v2.1.128 (2026-04-30)
- Subprocesses (Bash, hooks, MCP, LSP) no longer inherit `OTEL_*` env vars. PSS hook does not depend on inherited OTLP config — no impact.
- Sub-agent progress summary now uses prompt cache (~3× `cache_creation` reduction) — benefits the `pss-agent-profiler` agent transparently.
- `--plugin-dir` accepts `.zip` archives.

### v2.1.126 (2026-04-28)
- `claude_code.skill_activated` OTel event now carries `invocation_trigger` attribute (`"user-slash"` / `"claude-proactive"` / `"nested-skill"`) — useful for downstream PSS effectiveness analytics.
- `claude project purge [path]` to wipe a project's CC state.
- Read tool malware-assessment reminder removed (no PSS impact).

### v2.1.122 (2026-04-24)
- ToolSearch missing-MCP-tools fix means LLM Externalizer tools used by `pss-agent-profiler` are now reliably available even when the MCP server connects late.
- Malformed `hooks` entry in settings.json no longer invalidates the entire file.

### v2.1.121 (2026-04-23)
- PostToolUse hooks can replace tool output via `hookSpecificOutput.updatedToolOutput` (PSS uses UserPromptSubmit only — N/A).
- `alwaysLoad` MCP server config (PSS ships no MCP server — N/A).
- `--dangerously-skip-permissions` no longer prompts for writes to `.claude/skills|agents|commands/` — informational for users running `/pss-make-plugin-from-profile`.
- `claude plugin prune` and `plugin uninstall --prune` for orphaned auto-installed deps.

### v2.1.120 (2026-04-22)
- Skills can reference `${CLAUDE_EFFORT}` in their content — opportunity for future PSS skills to scale advice with effort (not adopted yet).
- `claude ultrareview [target]` subcommand.
- Native PowerShell shell on Windows when Git Bash absent (PSS hook runs via `uv run`, shell-agnostic).

### v2.1.119 (2026-04-21)
- PostToolUse hook inputs now carry `duration_ms` (PSS doesn't use PostToolUse).
- `--print` mode honors agent's `tools:`/`disallowedTools:` frontmatter — `pss-agent-profiler` declares both.
- `--agent <name>` honors agent's `permissionMode`.
- Fix for skills invoked before auto-compaction being re-executed against the next user message — PSS suggests via `additionalContext` not Skill calls, so PSS was unaffected; downstream skills surfaced by PSS now behave correctly.
- `TaskList` returns sorted by ID.
- Status line stdin now includes `effort.level` and `thinking.enabled`.

### v2.1.118 (2026-04-20)
- Hooks can invoke MCP tools directly via `type: "mcp_tool"` (PSS uses `type: "command"` — no change planned, but available if a future PSS hook needs MCP).
- `claude plugin tag` to create release git tags — PSS already tags via `scripts/publish.py`.
- Custom themes via `~/.claude/themes/` and plugin `themes/` dir.
- `--continue`/`--resume` find sessions that added the cwd via `/add-dir`.
- `/cost` and `/stats` merged into `/usage`.
- `DISABLE_UPDATES` env var.

### v2.1.117 (2026-04-19)
- `CLAUDE_CODE_FORK_SUBAGENT=1` enables forked subagents on external builds — `skills/pss-agent-toml/SKILL.md` already uses `context: fork` and benefits transparently.
- Agent frontmatter `mcpServers` loaded for main-thread agent sessions via `--agent`.
- `/model` selections persist across restarts.
- Default effort for Pro/Max on Opus 4.6 / Sonnet 4.6 is now `high`.
- Native macOS/Linux builds replace Glob/Grep with embedded `bfs`/`ugrep` (PSS doesn't call those tools from the hook).
- **Opus 4.7 sessions now correctly compute `/context` against the native 1M window** instead of 200K — relevant because PSS scoring is constant time regardless of prompt length and was already cheap; users on Opus 4.7 1M now get the full window before autocompact.

### v2.1.116 (2026-04-18)
- `/resume` 67% faster on 40MB+ sessions; MCP startup faster.
- `/reload-plugins` and background plugin auto-update auto-install missing plugin deps from already-added marketplaces.
- Bash tool surfaces a hint when `gh` hits the GitHub rate limit.

### v2.1.113 (2026-04-17)
- CLI now spawns a native Claude Code binary (per-platform optional dep).
- `sandbox.network.deniedDomains` setting.
- macOS dangerous-path checks for `rm` under `/private/{etc,var,tmp,home}`.
- Bash deny rules now match `env`/`sudo`/`watch`/`ionice`/`setsid` wrappers.
- `Bash(find:*)` no longer auto-approves `find -exec`/`-delete`.
- None affect PSS (the hook spawns the Rust binary directly via `subprocess.run`, not via Bash tool allow rules).

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
  every `UserPromptSubmit`. PSS hot-reloads on every `UserPromptSubmit`.

### v2.1.97
- NO_FLICKER rendering, focus view, status line `refreshInterval`.
- **PSS impact**: cosmetic, none.

### v2.1.94
- `hookSpecificOutput.sessionTitle` on `UserPromptSubmit`.
- `disallowedTools` agent frontmatter.
- `keep-coding-instructions` for output styles.
- **PSS impact**: none yet. The `sessionTitle` field is available as a future enhancement
  but PSS does not currently set it. PSS currently adopts none of these (optional).

### v2.1.92
- Removed `/tag` and `/vim` commands.
- `forceRemoteSettingsRefresh` policy.
- **PSS impact**: none. No PSS-breaking changes.

### v2.1.91
- **New `disableSkillShellExecution` setting**. When a user enables this, CC blocks
  skills from invoking shell via `!` blocks in SKILL.md.
- Plugin `bin/` executables officially supported (PSS ships them).
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
  Note: per project memory the skill currently uses `context: fork` to isolate the
  7-phase profiling pipeline in a forked subagent context — re-verify against the
  live SKILL.md before relying on either claim.

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

## Plugin Compliance with Anthropic Specs

This section records PSS's compliance posture against the official Anthropic plugin
specification, originally captured as a standalone audit (verification date
2026-02-27, reflecting PSS v2.1.0 / emasoft-plugins v2.1.0). Current source of
truth: https://code.claude.com/docs/en/plugins-reference

### Compliance summary

| Component | Status | Issues |
|-----------|--------|--------|
| Plugin Structure | COMPLIANT | None |
| Plugin Manifest | COMPLIANT | None |
| Commands | COMPLIANT | None |
| Skills | COMPLIANT | None |
| Hooks | COMPLIANT | None |
| Marketplace | COMPLIANT | None |

**Overall Status**: FULLY COMPLIANT with the Anthropic Plugin Specification.

### Plugin Directory Structure

**Requirement**: Components (`commands/`, `skills/`, `agents/`, `hooks/`) live at the
plugin root, NOT inside `.claude-plugin/`.

PSS layout:

```
perfect-skill-suggester/
├── .claude-plugin/
│   └── plugin.json          (manifest in correct location)
├── commands/                 (at root)
│   ├── pss-reindex-skills.md
│   └── pss-status.md
├── skills/                   (at root)
│   └── pss-usage/
│       ├── SKILL.md
│       └── references/
├── hooks/                    (at root)
│   └── hooks.json
├── scripts/                  (utility scripts)
├── schemas/                  (JSON schemas)
├── docs/                     (documentation)
├── src/                      (native binary sources)
├── README.md
└── LICENSE
```

Result: COMPLIANT.

### Plugin Manifest (`plugin.json`)

Location: `.claude-plugin/plugin.json`.

| Field | Required | PSS Status |
|-------|----------|------------|
| `name` | Yes | `"perfect-skill-suggester"` (kebab-case) |
| `version` | No | Tracked by `VERSION` file + `plugin.json` |
| `description` | No | Present (detailed) |
| `author` | No | Object with `name`, `email` |
| `skills` | No | `"./skills/"` (directory form) |
| `agents` | No | `[]` (empty array — PSS originally shipped no agents) |
| `repository` | No | GitHub URL |
| `keywords` | No | Array of tags |
| `license` | No | `"MIT"` |

Notes:
- `name` uses kebab-case (required format).
- `skills` accepts either a directory path or an array of `.md` files — PSS uses the
  directory form.
- `agents` was originally an empty array in the audit snapshot; the current PSS ships
  the `pss-agent-profiler` agent under `agents/` (default folder discovery handles it
  without needing an explicit `agents:` key, per the v2.1.140 advisory above).
- No invalid fields present.

Result: COMPLIANT.

### Commands

Requirement: `.md` files with YAML frontmatter containing `name`, `description`, and
(optionally) `argument-hint` plus `allowed-tools`.

Representative snapshots:

```yaml
---
name: pss-status
description: "View Perfect Skill Suggester status..."
argument-hint: "[--verbose] [--test PROMPT]"
allowed-tools: ["Bash", "Read"]
---
```

```yaml
---
name: pss-reindex-skills
description: "Scan ALL skills and generate AI-analyzed..."
argument-hint: "[--force] [--skill SKILL_NAME] [--batch-size N]"
allowed-tools: ["Bash", "Read", "Write", "Glob", "Grep", "Task"]
---
```

All required frontmatter fields present. Result: COMPLIANT.

### Skills

Requirement: `SKILL.md` with YAML frontmatter (`description` required).

Representative snapshot for `skills/pss-usage/SKILL.md`:

```yaml
---
name: pss-usage
description: "How to use Perfect Skill Suggester commands..."
argument-hint: ""
user-invocable: false
---
```

- `SKILL.md` present in the skill directory.
- YAML frontmatter with the required `description` field.
- `name` matches the directory name.
- References subdirectory present (e.g. `pss-commands.md`).
- Progressive disclosure pattern followed.

Result: COMPLIANT.

### Hooks Configuration

Requirement: `hooks.json` with events, matchers, and command definitions. Original
audit snapshot:

```json
{
  "description": "Perfect Skill Suggester - AI-powered skill activation",
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pss_hook.py",
            "timeout": 5000,
            "statusMessage": "Analyzing skill triggers..."
          }
        ]
      }
    ]
  }
}
```

Validation:
- Valid JSON structure.
- `UserPromptSubmit` is a valid hook event per the Anthropic spec.
- Uses `${CLAUDE_PLUGIN_ROOT}` variable correctly.
- `type: "command"` is a valid hook type.
- `timeout` specified in milliseconds in the snapshot above; the current PSS
  `hooks.json` uses **seconds** per the post-audit hooks.md spec change (10 s on
  `UserPromptSubmit`, 5 s on `SessionStart`, 5 s on `PostCompact` — see "Declared
  hook events" near the top of this document).
- Script path exists and is executable.

Result: COMPLIANT.

### Marketplace

Location: `emasoft-plugins-marketplace/.claude-plugin/marketplace.json`.

| Field | Required | Status |
|-------|----------|--------|
| `name` | Yes | `"emasoft-plugins"` |
| `owner` | Yes | Object with `name`, `email`, `url` |
| `plugins` | Yes | Array with at least one entry |

Reserved-name check: `official`, `anthropic`, and `claude` are reserved;
`emasoft-plugins` is NOT reserved.

Plugin entry validation (representative snapshot):

```json
{
  "name": "perfect-skill-suggester",
  "source": "../perfect-skill-suggester",
  "version": "1.0.0",
  "description": "...",
  "author": {...},
  "homepage": "...",
  "repository": "...",
  "license": "MIT",
  "keywords": [...],
  "category": "workflow",
  "strict": false,
  "commands": ["./commands/..."],
  "skills": ["./skills/..."],
  "agents": []
}
```

Result: COMPLIANT.

### Cross-Platform Compatibility

| Platform | Binary | Status |
|----------|--------|--------|
| macOS Apple Silicon | `pss-darwin-arm64` | Present |
| macOS Intel | `pss-darwin-x86_64` | Present |
| Linux x86_64 | `pss-linux-x86_64` | Present |
| Linux ARM64 | `pss-linux-arm64` | Present |
| Windows x86_64 | `pss-windows-x86_64.exe` | Present |

Hook script characteristics:
- Python 3.8+ (cross-platform).
- Uses `pathlib` for path handling.
- Auto-detects platform and architecture.
- Selects the correct binary automatically.

Result: FULLY CROSS-PLATFORM.

### Validation Results

Audit snapshot:

```
PSS Plugin Validation Report
============================================================
Summary:
  CRITICAL: 0
  MAJOR:    0
  MINOR:    0
  INFO:     2 (optional directories)
  PASSED:   39

All checks passed
```

The live equivalent now runs through `scripts/publish.py --gate` plus the CPV remote
validator (`uvx --from git+https://github.com/Emasoft/claude-plugins-validation --with
pyyaml cpv-remote-validate plugin .`).

### Installation Commands

#### Method 1: Marketplace Installation

```bash
# Add marketplace
claude plugin marketplace add ./emasoft-plugins-marketplace

# Install plugin
claude plugin install perfect-skill-suggester@emasoft-plugins
```

#### Method 2: Direct Plugin Loading

```bash
claude --plugin-dir ./perfect-skill-suggester
```

#### Method 3: GitHub

```bash
claude plugin marketplace add https://github.com/Emasoft/emasoft-plugins
claude plugin install perfect-skill-suggester@emasoft-plugins
```

### Specification References

| Document | URL |
|----------|-----|
| Plugin Reference | https://code.claude.com/docs/en/plugins-reference |
| Marketplace Spec | https://code.claude.com/docs/en/plugin-marketplaces |
| Plugin Discovery | https://code.claude.com/docs/en/discover-plugins |
| Hook Events | https://code.claude.com/docs/en/hooks |

### Compliance conclusion

Perfect Skill Suggester and the emasoft-plugins marketplace remain **fully compliant**
with the official Anthropic Claude Code plugin specifications. All required fields are
present, the directory structure follows the specification, and all validation checks
pass under the current release pipeline (`publish.py --gate` + CPV remote validate).

*Plugin compliance audit content merged from docs/ANTHROPIC-COMPLIANCE-REPORT.md (removed 2026-05-17).*
