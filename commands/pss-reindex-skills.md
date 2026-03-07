---
name: pss-reindex-skills
description: "Rebuild the PSS skill index"
argument-hint: "[--batch-size N] [--pass1-only] [--pass2-only] [--all-projects]"
allowed-tools: ["Bash", "Read", "Write", "Glob", "Grep", "Task"]
---

# PSS Reindex Skills Command

> ## CRITICAL: FULL REGENERATION ONLY - NO INCREMENTAL UPDATES
>
> **This command ALWAYS performs a complete reindex from scratch.**
>
> **PHASE 0 (MANDATORY):** Before ANY discovery or analysis, the agent MUST:
> 1. Delete `~/.claude/cache/skill-index.json`
> 2. Delete `~/.claude/cache/skill-checklist.md`
> 3. Verify clean slate before proceeding
>
> **WHY?** Incremental indexing causes: stale version paths, orphaned entries, name mismatches, missing new elements.
> **The ONLY reliable approach is DELETE -> DISCOVER -> REINDEX from scratch.**

Generate an **AI-analyzed** keyword and phrase index for ALL elements available to Claude Code. This command has the agent **read and understand each element** to formulate optimal activation patterns.

This is the **MOST IMPORTANT** feature of Perfect Skill Suggester - AI-generated keywords ensure 88%+ accuracy in element matching.

> **Architecture Reference:** See [docs/PSS-ARCHITECTURE.md](../docs/PSS-ARCHITECTURE.md) for the complete design rationale.

## Usage

```
/pss-reindex-skills [--batch-size 20] [--pass1-only] [--pass2-only] [--all-projects]
```

| Flag | Description |
|------|-------------|
| `--batch-size N` | Elements per batch (default: 10) |
| `--pass1-only` | Run Pass 1 only (keywords, no co-usage) |
| `--pass2-only` | Run Pass 2 only (requires existing Pass 1 index) |
| `--all-projects` | Scan ALL projects registered in `~/.claude.json` |

**REMOVED FLAGS:**
- ~~`--force`~~ - No longer needed, full reindex is ALWAYS performed
- ~~`--skill NAME`~~ - Single-skill reindex removed to prevent partial updates

## Execution Summary

The reindex runs in 4 phases:

1. **Phase 0** - Back up and delete all previous index data, clean stale .pss files
2. **Phase 1** - Discover all elements, spawn parallel Sonnet agents to extract keywords/intents/categories
3. **Phase 2** - Spawn parallel Sonnet agents for co-usage correlation using Rust binary + AI reasoning
4. **Completion** - Validate final index, aggregate domain registry, report results

Each phase has mandatory validation gates. The reindex MUST NOT proceed to the next phase if validation fails.

## Reference Documentation

For detailed execution protocol, read these references in order:

1. [Phase 0: Clean Slate](commands/pss-reindex-skills/00-phase0-clean-slate.md) - Backup, deletion, .pss cleanup, task checklist setup
2. [Phase 1: Discovery + Keywords](commands/pss-reindex-skills/01-phase1-discovery.md) - Element discovery, batch agent spawning, prompt building, validation
3. [Phase 2: Co-Usage Correlation](commands/pss-reindex-skills/02-phase2-co-usage.md) - Pass 1->2 transition, binary check, co-usage agents, domain aggregation
4. [Completion + Reporting](commands/pss-reindex-skills/03-completion-and-reporting.md) - Completion checkpoint, success/failure reporting format
5. [Index Schema](commands/pss-reindex-skills/04-index-schema.md) - JSON schema, field reference, Pass 1 and Pass 2 formats, element discovery locations

## Reference Documentation (Other)

For keyword best practices, scoring algorithm details, binary platform info, and other reference material, see: `docs/pss-reindex-reference.md`

## Related Commands

- `/pss-status` - View current element index status and statistics
