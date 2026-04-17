# Execution Protocol

As of v3.0.0 the CozoDB store (`pss-skill-index.db`) is the single canonical
index. The legacy `skill-index.json` is written only on demand via
`pss export --json` and is never read by the runtime hook.

### Step 1: Verify Index Health

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
BINARY="${PLUGIN_ROOT}/bin/pss-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"

if ! "${BINARY}" health 2>/dev/null; then
    echo "CozoDB index not found or empty. Run /pss-reindex-skills first."
    exit 1
fi
```

### Step 2: Resolve Element(s)

**For single element (by name):**
```bash
# Search known locations for the element
ELEMENT_PATH=$(find ~/.claude/skills ~/.claude/agents ~/.claude/commands ~/.claude/rules ~/.claude/plugins/cache -name "<name>*" -type f 2>/dev/null | head -1)
```

**For single element (by path):**
```bash
ELEMENT_PATH="<user-provided-path>"
```

**For plugin mode:**
```bash
PLUGIN_DIR="<user-provided-plugin-path>"
# Discover all elements in the plugin
```

### Step 3: Check Duplicate

Use `pss get <name>` (exit 0 on hit, non-zero on miss) or
`pss find-by-name <substring>` to discover whether the target already exists.
- If EXISTS: Will be UPDATED (overwritten with fresh enrichment data; the
  original `first_indexed_at` is preserved, only `last_updated_at` advances)
- If NEW: Will be ADDED

### Step 4: Run the Enrichment + Merge Pipeline

For EACH element to process, pipe it through the discovery + Rust enrichment
pipeline. `pss_merge_queue.py` writes directly to CozoDB (the `--index` flag
accepts a seed path for compatibility but is no longer the canonical store):

```bash
uv run "${PLUGIN_ROOT}/scripts/pss_discover.py" --jsonl --name "<element-name>" \
  | "${BINARY}" --pass1-batch \
  | uv run "${PLUGIN_ROOT}/scripts/pss_merge_queue.py" --batch-stdin
```

**Discovery modes** — `pss_discover.py` supports several filtering flags:

| Flag | Purpose | Example |
|------|---------|---------|
| `--name "<name>"` | Discover a single element by name | `--name "my-skill"` |
| `--type "<types>"` | Comma-separated type filter | `--type "skill,agent"` |
| `--project-only` | Only scan current project elements | |
| `--user-only` | Only scan user-level elements | |
| `--all-projects` | Scan ALL registered projects | |
| `--exclude-inactive-plugins` | Skip disabled plugins | |

For plugin-wide indexing, omit `--name` and use `--type` or no filter to discover all elements, then pipe the full JSONL stream through the enrichment pipeline.

### Step 5: Verify

Confirm the element appears in the CozoDB index via the Rust binary:

```bash
"${BINARY}" get "<element-name>" --json
```

This prints a single JSON record with `name`, `type`, `source`, `path`,
`keywords`, `first_indexed_at`, and `last_updated_at`. Exit code 0 means the
element is indexed; non-zero means it was not merged.

For a Python-side sanity check use the CozoDB helper module instead of the
removed `skill-index.json` read:

```bash
uv run python -c "
from scripts.pss_cozodb import get_entry_by_name
entry = get_entry_by_name('<element-name>')
if entry:
    print(f\"{entry['name']} (type={entry.get('type','skill')}) - {len(entry.get('keywords',[]))} keywords\")
else:
    print('<element-name> not found in CozoDB')
"
```

### Step 6: Optional JSON Snapshot

If a human-readable snapshot is needed for `git diff` review, export on demand:

```bash
"${BINARY}" export --json --path ./skill-index.export.json
```

The Rust binary no longer exposes `--build-db`; CozoDB is populated by
`pss_merge_queue.py` during Step 4.
