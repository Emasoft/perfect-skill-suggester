---
name: pss-status
description: "Show PSS index status and test matching"
argument-hint: "[--verbose] [--test PROMPT] [--run-tests]"
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

- `/pss-reindex-skills` - Regenerate the skill index with AI analysis
