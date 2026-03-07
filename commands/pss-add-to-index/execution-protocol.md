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
- If EXISTS: Will be UPDATED (overwritten with fresh scan data)
- If NEW: Will be ADDED

### Step 4: Spawn Sonnet Agent for Metadata Extraction

For EACH element to process, spawn a sonnet agent with the Pass 1 template from `${CLAUDE_PLUGIN_ROOT}/prompts/pass1-sonnet.md`.

**IMPORTANT**: When spawning the sonnet agent:
- Use `model: sonnet` for accurate extraction
- Provide only ONE element per agent
- The agent writes a `.pss` file to `${PSS_TMPDIR}/pss-queue/`

### Step 5: Merge into Index

After the sonnet agent completes, merge the `.pss` file into the index:

```bash
PSS_TMPDIR=$(python3 -c "import tempfile; print(tempfile.gettempdir())")
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pss_merge_queue.py" "${PSS_TMPDIR}/pss-queue/${ELEMENT_NAME}.pss" --pass 1 --quiet
```

### Step 6: Verify

Confirm the element appears in the index:
```bash
python3 -c "
import json
with open('$HOME/.claude/cache/skill-index.json') as f:
    idx = json.load(f)
name = '<element-name>'
if name in idx['skills']:
    e = idx['skills'][name]
    print(f'✅ {name} ({e.get(\"type\",\"skill\")}) - {len(e.get(\"keywords\",[]))} keywords')
else:
    print(f'❌ {name} not found in index')
"
```

### Step 7 (Optional): Pass 2

If `--pass2` is specified, also run co-usage analysis:
1. Read the Pass 2 template from `${CLAUDE_PLUGIN_ROOT}/prompts/pass2-sonnet.md`
2. Spawn a sonnet agent to analyze co-usage relationships
3. Merge the co-usage data into the index
