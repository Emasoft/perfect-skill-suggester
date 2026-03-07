# Phase 6: Write and Validate

**6.1 Write the `.agent.toml` file**

Use the template from [toml-format.md](toml-format.md). Every field must be populated from the evaluation results. The `[skills.excluded]` section must document WHY each rejected candidate was excluded.

**6.2 Validate**

Run the validator:
```bash
uv run scripts/pss_validate_agent_toml.py <output-path> --check-index --verbose
```

Exit codes: 0 = valid, 1 = errors found, 2 = TOML parse error.

If validation fails, fix the errors and re-validate. Common issues:
- Missing required sections (`[agent]`, `[skills]`)
- Duplicate skill across tiers (same name in primary AND secondary)
- Tier size exceeded (primary > 7, secondary > 12, specialized > 8)
- Agent name not kebab-case

**6.3 Clean up**

Delete the temporary JSON descriptor file.

**Phase 6 Completion Checklist** (profile is ONLY complete when ALL items are checked):

- [ ] `.agent.toml` file written to the correct output path
- [ ] `[agent]` section has `name`, `source`, `path` — all correct
- [ ] `[requirements]` section present if requirements were provided; omitted if none
- [ ] `[skills]` section: `primary` has 1-7 items, `secondary` has 0-12, `specialized` has 0-8
- [ ] `[skills.excluded]` has a comment for every rejected candidate with the rejection reason
- [ ] ALL optional sections present: `[agents]`, `[commands]`, `[rules]`, `[mcp]`, `[hooks]`, `[lsp]` (even if `recommended = []`)
- [ ] Validator run: `uv run "$CLAUDE_PLUGIN_ROOT/scripts/pss_validate_agent_toml.py" <file> --check-index --verbose`
- [ ] Validator exited with code 0 (if code 1: fix errors, re-validate; if code 2: fix TOML syntax, re-validate)
- [ ] No validation errors remain — validator returned exit code 0
- [ ] Temporary descriptor file deleted
- [ ] Summary reported: X primary + Y secondary + Z specialized skills; N excluded candidates

**Do NOT report success until the validator returns exit code 0.**
