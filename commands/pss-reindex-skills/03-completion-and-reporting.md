# Completion Checkpoint + Reporting

## COMPLETION CHECKPOINT (MANDATORY)

**The reindex operation is ONLY COMPLETE when ALL of these are true:**

1. Pass 1 completed - All elements have keywords, categories, and intents
2. Pass 1 validated - CPV plugin validator returned exit code 0
3. Pass 1 tracking verified - All batch tracking files show DONE+YES for all elements
4. Pass 2 completed - All elements have co_usage relationships (usually_with, precedes, follows, alternatives)
5. Pass 2 validated - CPV plugin validator returned exit code 0
6. Pass 2 tracking verified - All batch tracking files show DONE+YES for all elements
7. Global index updated - `~/.claude/cache/skill-index.json` contains `"pass": 2`
8. Domain registry generated - `~/.claude/cache/domain-registry.json` exists with aggregated domains
9. Temporary files cleaned up - No .pss files or tracking files remain in ${PSS_TMPDIR}/pss-queue/

## FAILURE CONDITIONS

- If index shows `"pass": 1`, Pass 2 was NOT executed
- If only some elements have `co_usage`, Pass 2 agents only partially completed
- If validator fails with `--restore-on-failure`, the OLD index was restored and reindex FAILED
- If tracking files show PENDING elements, some agents forgot to process them

## REPORT TO USER

After successful completion, report:
```
PSS Reindex Complete
====================
Pass 1: {N} elements with keywords/categories (validated)
Pass 2: {M} elements with co-usage relationships (validated)
Domains: {D} canonical domains aggregated (registry)
Index: ~/.claude/cache/skill-index.json (pass: 2)
Registry: ~/.claude/cache/domain-registry.json
Backup: {BACKUP_DIR} (preserved for safety)
```

After failed completion (validator restored backup), report:
```
PSS Reindex FAILED
==================
Validation errors detected - old index restored from backup.
Backup restored from: {BACKUP_DIR}
Errors: {validator error summary}
```
