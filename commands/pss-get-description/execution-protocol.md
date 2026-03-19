# Execution Protocol

## Step 1: Locate PSS Binary

Find the PSS binary using the standard discovery order:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$0")")}"
PSS_BIN="${PLUGIN_ROOT}/bin/pss-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m | sed 's/arm64/arm64/;s/x86_64/x86_64/')"
if [ ! -x "$PSS_BIN" ]; then
    PSS_BIN="${PLUGIN_ROOT}/rust/target/release/pss"
fi
```

## Step 2: Parse Arguments

Extract from the user's `/pss-get-description` invocation:
- **name(s)**: The element name(s) to look up (required)
- **--batch**: If multiple names are comma-separated
- **--format**: Output format (default: json)

## Step 3: Execute Query

### Single element:
```bash
"$PSS_BIN" get-description "<name>" --format json
```

### Batch (multiple elements):
```bash
"$PSS_BIN" get-description "<name1>,<name2>,<name3>" --batch --format json
```

## Step 4: Present Results

Parse the JSON output and present to the user:

### Single result:
```
Element: <name> [<type>]
Plugin:  <plugin or "user-owned">
Description: <description>
Triggers: <keyword1>, <keyword2>, ...
Path: <source_path>
```

### Batch results:
Present as a formatted table with columns: NAME, TYPE, DESCRIPTION, PLUGIN.
Mark not-found entries as `null` in the output.

## Ambiguous Results

When multiple entries share the same name (from different sources/plugins), the binary returns:
- **Single mode**: JSON object with `"ambiguous": true`, `"query"`, and `"matches"` array
- **Batch mode**: The ambiguous entry appears as the full ambiguity object in the array position

Present ambiguous results clearly to the user and suggest using:
- Namespace prefix: `plugin-name:element-name`
- 13-char ID: from `pss search` or `pss list` output

## Error Handling

- If the binary is not found, instruct the user to run `/pss-reindex-skills`
- If an entry is not found in single mode, report the error and suggest checking the name
- If an entry is not found in batch mode, return `null` for that position in the array
