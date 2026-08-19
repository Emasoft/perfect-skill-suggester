---
trdd-id: S1HOYHV0
title: Decide the disposition of 3 dead scripts (cpv_network_resilience, pss_setup, smart_exec)
column: backburner
created: 2026-08-19T04:32:41+0200
updated: 2026-08-19T04:32:41+0200
current-owner: pss-maintainer-session
task-type: refactor
scope: project
labels: [scripts, dead-code, audit-S5]
---

# 3 scripts have zero references outside their own tests — wire them or remove them

Source: Phase-1 self-audit finding **S5**, CONFIRMED by the refutation pass with a positive
control (the method correctly surfaces the known-live `pss_hook.py`) and one false positive
ruled out (`pss-setup-agent` substring collision).
Report: reports/plugin-self-audit/20260816_190920+0200-refutation.md (gitignored).

## The facts (verified)

Whole-repo grep (incl. `.github/`, `pyproject.toml`, `hooks/`, `commands/`, `skills/`,
`agents/`, `docs/`): `scripts/cpv_network_resilience.py`, `scripts/pss_setup.py`,
`scripts/smart_exec.py` are referenced only by their own unit tests. Honest caveat (inherited,
unresolvable by grep): manual ad-hoc invocation can't be ruled out statically.

2026-08-19 addendum: `cpv_network_resilience.py`'s docstring falsely claimed publish.py
imports it; the docstring was corrected (states "no production script imports it yet").

## Acceptance (one decision per script, recorded here)

- [ ] For each script: WIRE it into a real consumer (e.g. publish.py adopting
      cpv_network_resilience's retry helpers), or DELETE it with its tests (RULE 0: commit
      first; move to a `_dev` folder if in doubt), or KEEP with a docstring explicitly
      declaring it a manual/ad-hoc tool.
- [ ] No script left in the ambiguous "dead but shipped" state; the no-legacy-code rule
      applies.

## Approval log
