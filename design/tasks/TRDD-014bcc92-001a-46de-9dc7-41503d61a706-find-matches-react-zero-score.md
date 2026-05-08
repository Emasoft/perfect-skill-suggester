# TRDD-014bcc92 — find_matches returns zero matches for "build react ... with hooks"

**TRDD ID:** `014bcc92-001a-46de-9dc7-41503d61a706`
**Filename:** `design/tasks/TRDD-014bcc92-001a-46de-9dc7-41503d61a706-find-matches-react-zero-score.md`
**Tracked in:** this repo (design/tasks/ is git-tracked)
**Status:** Not started — investigation needed
**Created:** 2026-05-08

## Symptom

`pss_test_e2e.py` Phase 6 has been failing on the `build react component
with hooks` prompt since at least 3.3.0. Verified empirically on 3.3.3
and on the in-progress 3.4.0 work (commit 15e8f55 plus current
working-tree edits). Two related unit tests also fail:
`tests::test_find_matches_with_synonyms` and `tests::test_confidence_levels`.
Both panic on `assert!(!matches.is_empty())`, i.e. the same root cause:
`find_matches` returns an empty Vec.

## Reproduction

1. Build the binary: `(cd rust/skill-suggester && cargo build --release)`
2. Run e2e with `--keep-temp` to preserve the test fixture:
   `uv run python scripts/pss_test_e2e.py --keep-temp`
3. Locate the test home dir from the output: e.g.
   `/var/folders/.../pss-test-<timestamp>-<rand>`
4. Send the prompt:
   ```
   echo '{"prompt": "build react frontend component with hooks"}' | \
     HOME=$LATEST_DIR/home CLAUDE_PLUGIN_DATA="" \
     bin/pss-darwin-arm64 --format hook --top 4 --min-score 0.0
   ```
5. Observed: `{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit"}}`
   (no skill suggestions)

The same test fixture matches `lint python code with ruff` →
test-python-linter and `deploy docker container to production` →
test-docker-deploy. Only the react prompt fails.

## Diagnosis (so far)

With `RUST_LOG=debug`:
- kw_lookup pre-filters 2 candidates (test-docker-deploy and
  test-react-frontend pass).
- Prompt domains are inferred as `{"frontend"}`.
- test-docker-deploy is correctly excluded by domain inference
  (skill domains: `["devops"]`).
- test-react-frontend's processing produces no debug log AND no match —
  it passes the domain filter but its score collapses to 0 (or it's
  silently filtered by a downstream gate without a debug print).

Adding `"react", "react component", "react hooks", "build react",
"build react component", "build react component with hooks"` to the
fixture's keywords[] did NOT fix the issue. Changing the fixture's
domains[] from `["110"]` to `["web-frontend"]` did NOT fix the issue.

## Hypothesis

There is a second filter in `find_matches` (between the kw_lookup
pre-filter and the per-skill scoring loop) that drops test-react-frontend
silently. Likely candidates (need verification by reading
`rust/skill-suggester/src/main.rs::find_matches`):
- A post-kw-lookup "minimum keyword overlap" gate
- A "must-have-non-zero-score-after-relative-normalisation" gate that
  zeros out skills below a hard floor
- A framework-presence gate that requires the prompt's project context
  to declare a matching framework (project context is empty in the test
  harness)

The DOMAIN_TAXONOMY at `main.rs:7285` doesn't include `"react"` /
`"vue"` / `"angular"` as synonyms for the `frontend` domain. Adding them
might also help but probably isn't the only fix — the prompt
"build react frontend component with hooks" already includes the
literal word "frontend" yet the skill still scores zero.

## Plan

1. Read `find_matches` top-to-bottom; add detailed `RUST_LOG=trace`
   logging at every early-return / score-zeroing branch.
2. Re-run with the failing prompt; identify the exact filter that
   drops test-react-frontend.
3. Either (a) fix the filter logic, (b) add `react`/`vue`/`angular` to
   DOMAIN_TAXONOMY frontend synonyms, or (c) add a new "framework name
   in prompt → keep skill" override.
4. Restore the original test prompt (`build react component with hooks`)
   and the original keywords list — the fixture should be the
   canonical short form once the scorer is fixed.
5. Re-run `cargo test --release` and confirm
   `test_find_matches_with_synonyms` + `test_confidence_levels` go
   green.

## Out of scope

- Refactoring the entire scoring algorithm
- Renaming or restructuring DOMAIN_TAXONOMY
- Changing the test fixture's overall shape
