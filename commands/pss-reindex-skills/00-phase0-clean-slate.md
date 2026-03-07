# Phase 0: Clean Slate (MANDATORY)

## Cross-Platform Temp Directory

Before executing any phase, determine the system temp directory:
```bash
PSS_TMPDIR=$(python3 -c "import tempfile; print(tempfile.gettempdir())")
```
All temporary paths below use `${PSS_TMPDIR}` as the base. This resolves to `/tmp` on Linux, a system temp dir on macOS, and the user's temp folder on Windows.

---

## AGENT TASK CHECKLIST (MANDATORY - CREATE BEFORE ANY WORK)

> **BEFORE EXECUTING ANY STEP, the agent MUST create a task list using TaskCreate.**
> **This checklist MUST be tracked and updated throughout the reindex process.**

**Create these tasks IN THIS EXACT ORDER using TaskCreate:**

```
1. [Phase 0] Create backup directory in system temp
2. [Phase 0] Backup and remove skill-index.json
3. [Phase 0] Backup and remove skill-checklist.md
4. [Phase 0] VERIFY clean slate - no index files remain
5. [Phase 0.5] Run pss_cleanup.py --all-projects to remove stale .pss files
6. [Phase 1] Run discovery script to generate element checklist
7. [Phase 1] Spawn Pass 1 batch agents for keyword analysis
8. [Phase 1] Validate Pass 1 index (run CPV plugin validator: uv run --with pyyaml python3 scripts/validate_plugin.py . --verbose)
9. [Phase 1] Check agent tracking files for missed elements, re-run if needed
10. [Phase 2] Spawn Pass 2 batch agents for co-usage analysis
11. [Phase 2] Validate final index (run CPV plugin validator: uv run --with pyyaml python3 scripts/validate_plugin.py . --verbose)
12. [Phase 2] Check agent tracking files for missed elements, re-run if needed
13. [Verify] Confirm index has pass:2 and all elements have co_usage
14. [Report] Report final statistics to user
```

**CRITICAL RULES:**
- Tasks 1-4 (Phase 0) MUST ALL be marked `completed` BEFORE starting task 5
- Task 5 (Phase 0.5 cleanup) MUST complete before starting task 6
- If task 4 verification FAILS, do NOT proceed - mark remaining tasks as blocked
- Update task status to `in_progress` when starting, `completed` when done
- If ANY Phase 0 task fails, STOP and report error to user

**Example TaskCreate call for first task:**
```
TaskCreate({
  subject: "[Phase 0] Create backup directory in system temp",
  description: "Create timestamped backup dir: ${PSS_TMPDIR}/pss-backup-YYYYMMDD_HHMMSS",
  activeForm: "Creating backup directory"
})
```

---

## PHASE 0: CLEAN SLATE (MANDATORY - NEVER SKIP - NON-NEGOTIABLE)

> **THIS PHASE IS MANDATORY AND NON-NEGOTIABLE.**
> **You MUST complete ALL steps before proceeding to Phase 1.**
> **If ANY step fails, STOP and report the error. Do NOT proceed.**

Before discovering or analyzing ANY elements, you MUST backup and delete ALL previous index data.
The backup ensures the old data is preserved for debugging, but moved out of the way so it can
NEVER interfere with the fresh reindex.

```bash
# Step 0.0: Create timestamped backup folder and ensure pss-queue dir exists
BACKUP_DIR="${PSS_TMPDIR}/pss-backup-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
mkdir -p ${PSS_TMPDIR}/pss-queue
echo "$BACKUP_DIR" > ${PSS_TMPDIR}/pss-queue/backup-dir.txt
echo "Backup directory: $BACKUP_DIR"

# Step 0.1: Backup and delete the main skill index
if [ -f ~/.claude/cache/skill-index.json ]; then
    mv ~/.claude/cache/skill-index.json "$BACKUP_DIR/"
    echo "skill-index.json moved to backup"
else
    echo "skill-index.json did not exist"
fi

# Step 0.2: Backup and delete the skill checklist
if [ -f ~/.claude/cache/skill-checklist.md ]; then
    mv ~/.claude/cache/skill-checklist.md "$BACKUP_DIR/"
    echo "skill-checklist.md moved to backup"
else
    echo "skill-checklist.md did not exist"
fi

# Step 0.3: VERIFY CLEAN SLATE (MANDATORY CHECK)
echo ""
echo "=== VERIFICATION ==="
if [ -f ~/.claude/cache/skill-index.json ]; then
    echo "FATAL ERROR: skill-index.json still exists!"
    echo "Phase 0 FAILED. Cannot proceed."
    exit 1
fi

echo "CLEAN SLATE VERIFIED"
echo "   - No skill-index.json"
echo "   - Backup at: $BACKUP_DIR"
echo ""
echo "Proceeding to Phase 1: Discovery..."
```

**IMPORTANT: PERSIST $BACKUP_DIR**
The orchestrator MUST remember the `$BACKUP_DIR` path for the rest of the reindex process.
The post-reindex validator needs this path to restore the backup if validation fails.
Store it in a variable or write it to `${PSS_TMPDIR}/pss-queue/backup-dir.txt`:
```bash
echo "$BACKUP_DIR" > ${PSS_TMPDIR}/pss-queue/backup-dir.txt
```

**CHECKLIST (ALL MUST BE CHECKED BEFORE PROCEEDING):**
- [ ] Backup directory created in `${PSS_TMPDIR}`
- [ ] `$BACKUP_DIR` path persisted to `${PSS_TMPDIR}/pss-queue/backup-dir.txt`
- [ ] `skill-index.json` moved to backup (or did not exist)
- [ ] `skill-checklist.md` moved to backup (or did not exist)
- [ ] **VERIFICATION PASSED**: No index files remain

**IF VERIFICATION FAILS, DO NOT PROCEED. Report the error and stop.**

**WHY THIS IS NON-NEGOTIABLE:**
1. Old index paths point to outdated plugin versions - skills not found
2. Renamed/moved elements create orphaned entries - phantom elements suggested
3. Elements with wrong names persist - matching fails silently
4. Deleted elements remain as phantom entries - broken suggestions
5. Co-usage data references non-existent elements - cascading errors
6. **ANY remnant of old data will corrupt the fresh index**

**The backup in `${PSS_TMPDIR}` ensures you can debug issues if needed, but the old data is GONE from the active paths.**

---

## PHASE 0.5: CLEAN STALE .PSS FILES (MANDATORY)

> **Run AFTER Phase 0 backup/deletion, BEFORE Phase 1 discovery.**
> This removes orphaned .pss files left by crashed agents or previous runs.

```bash
# Clean ALL stale .pss files system-wide (element dirs + ${PSS_TMPDIR}/pss-queue/)
# NOTE: CLAUDE_PLUGIN_ROOT is used here because PLUGIN_ROOT is not yet defined at this phase
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pss_cleanup.py" --all-projects --verbose
```

**What this does:**
- Scans ALL element locations (user, project, plugin cache, local plugins, all projects)
- Removes any `*.pss` files found in element directories (leftovers from pss_generate.py)
- Removes any `*.pss` files in `${PSS_TMPDIR}/pss-queue/` (leftovers from crashed agents)
- Reports count of files deleted per location

**If cleanup reports 0 files:** Good - no stale files existed. Proceed.
**If cleanup reports N files:** Files were cleaned. Proceed to Phase 1.
**If cleanup fails (exit code 1):** Non-fatal warning - log it and proceed to Phase 1.
