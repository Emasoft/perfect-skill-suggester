---
name: verify-shipped-status-against-the-tag
description: "did this fix already ship? / is F-N in the last release or the next one? / release notes list a fix that was already out / STATE says pending but git disagrees / which version shipped commit X — how to check a fix's shipped status for real"
ocd: 2026-07-17
lmd: 2026-07-23
metadata:
  node_type: memory
  type: feedback
  tier: component
---

^WJ922K80 [desc:"Verify a fix's shipped status against git, not a STATE note: for a submodule fix, check the release tag's recorded gitlink is a descendant of the fix commit via merge-base --is-ancestor; commit order in the log alone is not proof.", keywords:"verify_shipped_status git_ancestor_check submodule_gitlink_check commit_order_not_proof release_notes_verification", type:feedback, ocd:2026-07-17, lmd:2026-07-17]
Before writing release notes that claim "this release contains fix X", VERIFY X's
shipped status against the git TAG's actual recorded state — never against a STATE
note, changelog line, or your own summary, any of which can be a stale assumption
carried forward through a compaction.

Concretely, when a fix lives in a submodule (or any pinned dependency), the release
tag records a GITLINK, and the only truth is whether the fix commit is an ANCESTOR of
that gitlink:

```bash
TAG_LINK=$(git ls-tree <tag> <submodule-path> | awk '{print $3}')
git -C <submodule-path> merge-base --is-ancestor <fix-sha> "$TAG_LINK" \
  && echo "already shipped in <tag>" || echo "not yet shipped"
```

For a fix in the main repo, the equivalent is `git merge-base --is-ancestor <fix-sha>
<tag>`. Commit ORDER in the log is NOT proof: a fix committed before the release
commit is only shipped if the release tag's tree actually points at (a descendant of)
it — which in a submodule means checking the recorded gitlink, not the timeline.

^7JQFNGSF [desc:"F10 was listed 'pending' across compactions but was already an ancestor of v3.10.6's submodule gitlink by v3.10.7 ship time — a stale STATE note nearly mis-labeled it in release notes; always answer 'which release ships X' from git at ship time.", keywords:"F10_stale_state_example already_shipped_caught_at_ship_time trdd_1z8sgq7n_case answer_from_git_not_memory", type:feedback, ocd:2026-07-17, lmd:2026-07-17]
WHY it matters: PSS's TRDD STATE block listed F10 as "rides the next release" across
several compactions; at v3.10.7 ship time the one-line ancestry check showed F10
(`bbdfa8f`) was already an ancestor of the v3.10.6 tag's submodule gitlink (`79358ba`)
— it had shipped a release earlier. Trusting the STATE note would have put a
already-live fix in the v3.10.7 release notes. The check cost one command and ran
BEFORE the `publish.py` invocation, so the notes were correct on the first try.

**How to apply:** treat "which release contains commit X" as a question you ANSWER
from git at ship time, not a fact you carry in prose. Do the `--is-ancestor` check for
every fix you are about to name in a release, especially any that "has been waiting"
across sessions — waiting is exactly the state a compaction most easily gets wrong.
Pairs with [[publish-submodule-build-skip-stale-binaries]]: that one says verify the
shipped BINARY behaviorally; this one says verify the shipped COMMIT SET against the tag.
Also pairs with [[date-only-bound-needs-direction]] (same TRDD-1Z8SGQ7N temporal-index
sweep — both bugs were proven dead by running the freshly shipped artifact, not by
trusting the pipeline's exit).

## Governed by
- [[pss-knowledge-hub]] — entry point to PSS's PROJECT-scope memory corpus.

## Notes and lessons learned

[^1]: [id:ATOM-9T4K-SH1P, status:valid, keywords:"fix_already_shipped stale_STATE_note release_notes_wrong is_ancestor submodule_gitlink verify_at_ship_time", ocd:2026-07-17, lmd:2026-07-17]
  DO NOT trust a STATE note / summary that says a fix "rides the next release", BECAUSE
  that claim easily survives a compaction after the fix has actually shipped — F10 was
  listed as pending but was already an ancestor of the prior tag's submodule gitlink. DO
  answer "which release contains commit X" from git at ship time: `git ls-tree <tag>
  <sub>` → `merge-base --is-ancestor <sha> <gitlink>`.
