# Verbose Mode and Cache Validity

## Verbose Mode

With `--verbose`, show additional details:

- Full list of skills by source
- Keyword distribution histogram
- Top 10 most-activated skills (if activation logs exist)
- Synonym expansion patterns count

## Cache Validity

The index is considered:
- **VALID**: Less than 24 hours old
- **STALE**: More than 24 hours old (recommend reindex)
- **MISSING**: No index file found (must reindex)
