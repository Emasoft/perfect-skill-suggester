# Execution Protocol

### Step 1: Load Existing Index

```bash
INDEX_PATH="$HOME/.claude/cache/skill-index.json"
if [ ! -f "$INDEX_PATH" ]; then
    echo "No existing index found. Run /pss-reindex-skills first."
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

Read `skill-index.json` and check if an entry with the same name already exists.
- If EXISTS: Will be UPDATED (overwritten with fresh enrichment data)
- If NEW: Will be ADDED

### Step 4: Run Rust Enrichment Pipeline

For EACH element to process, pipe it through the discovery and enrichment pipeline:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
BINARY="${PLUGIN_ROOT}/bin/pss-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"

# Discover the element and pipe through Rust enrichment
uv run "${PLUGIN_ROOT}/scripts/pss_discover.py" --jsonl --name "<element-name>" \
  | "${BINARY}" --pass1-batch \
  | uv run "${PLUGIN_ROOT}/scripts/pss_merge_queue.py" --batch-stdin --index "$HOME/.claude/cache/skill-index.json"
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

Confirm the element appears in the index:
```bash
uv run python3 -c "
import json
with open('$HOME/.claude/cache/skill-index.json') as f:
    idx = json.load(f)
name = '<element-name>'
# All element types (skill, agent, command, rule, mcp, lsp) are stored
# under the top-level 'skills' key in skill-index.json, distinguished
# by each entry's 'type' field.
if name in idx['skills']:
    e = idx['skills'][name]
    print(f'Added {name} (type={e.get(\"type\",\"skill\")}) - {len(e.get(\"keywords\",[]))} keywords')
else:
    print(f'{name} not found in index')
"
```

### Step 6: Rebuild CozoDB (Optional)

If the CozoDB index is used for pre-filtering, rebuild it:
```bash
"${BINARY}" --build-db
```
