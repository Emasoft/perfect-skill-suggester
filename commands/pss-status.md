---
name: pss-status
description: "Show PSS index status and test matching"
argument-hint: "[--verbose] [--test \"PROMPT\"] [--run-tests]"
effort: low
allowed-tools: ["Bash", "Read"]
---

# PSS Status Command

View the current status of Perfect Skill Suggester including:
- Skill index statistics
- Cache age and validity
- Recent skill activations
- Matching performance metrics

## Usage

```
/pss-status [--verbose] [--test "PROMPT"] [--run-tests]
```

## Options

| Option | Description |
|--------|-------------|
| `--verbose` | Show detailed breakdown by source and type |
| `--test "PROMPT"` | Test matching against a sample prompt |
| `--run-tests` | Run end-to-end pipeline tests to verify PSS works correctly |

## Reference

- [Execution Protocol](pss-status/execution-protocol.md)
- [Test Mode](pss-status/test-mode.md)
- [Verbose Mode and Cache Validity](pss-status/verbose-and-cache.md)
- [Binary Status](pss-status/binary-status.md)

## Related Commands

- `/pss-reindex-skills` - Rebuild the skill index using the Rust pipeline
- `/pss-search <query>` - Full-text search across the CozoDB index
- `/pss-added-since <when>` - List entries installed since a given time

## See Also (Rust CLI)

For more granular health and statistics checks against the CozoDB store:

- `"$CLAUDE_PLUGIN_ROOT/bin/pss-<platform>" health [--verbose]` - exit 0 / 1 / 2 probe (populated / empty / missing)
- `"$CLAUDE_PLUGIN_ROOT/bin/pss-<platform>" stats --format table` - per-type / per-source counts plus timestamp banner
- `"$CLAUDE_PLUGIN_ROOT/bin/pss-<platform>" count` - single-integer entry count for scripts
