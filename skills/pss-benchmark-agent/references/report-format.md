# Mandatory Report Sections

## Table of Contents

- [Section 1: Score Progression Table](#section-1-score-progression-table)
- [Section 2: Change Details](#section-2-change-details-for-each-change)
  - [2a. Exact Code Diff](#2a-exact-code-diff)
  - [2b. Formula / Algorithm Description](#2b-formula--algorithm-description)
  - [2c. Why This Change (Hypothesis)](#2c-why-this-change-hypothesis)
  - [2d. Per-Prompt Impact](#2d-per-prompt-impact-detailed)
  - [2e. Rejected Approach Details](#2e-rejected-approach-details)
- [Section 3: Structural Analysis](#section-3-structural-analysis)
- [Section 4: Synonym Expansions Inventory](#section-4-synonym-expansions-inventory)
- [Section 5: Near-Miss Analysis](#section-5-near-miss-analysis)
- [Section 6: Generalizability Self-Assessment](#section-6-generalizability-self-assessment)

## Section 1: Score Progression Table

Every change you make MUST be benchmarked BEFORE the next change. Record each measurement:

```markdown
| # | Change | Score | Delta | Reverted? |
|---|--------|-------|-------|-----------|
| 0 | Baseline (unmodified) | 314/500 | — | — |
| 1 | Changed ABSOLUTE_ANCHOR 1000→1600 | 106/500 | -208 | YES |
| 2 | Reverted ANCHOR, added soft gates 0.35 | 182/500 | +76 | NO |
| 3 | Gate penalty 0.35→0.50 | 189/500 | +7 | NO |
| 4 | Gate penalty 0.50→0.80 | 211/500 | +22 | NO |
| 5 | Gate penalty 0.80→0.85 | 208/500 | -3 | YES (back to 0.80) |
```

**CRITICAL RULE: ALWAYS measure baseline BEFORE making any changes.** If your first change causes a regression, you need the baseline number to detect it immediately.

## Section 2: Change Details (For EACH Change)

For every change (kept or reverted), document ALL of the following:

### 2a. Exact Code Diff

Show the BEFORE and AFTER code with line numbers. Not prose descriptions — actual code:

```markdown
**Change 3: Gate penalty 0.35→0.80**

BEFORE (line 6635):
```rust
let gate_penalty_factor = 0.35;  // W7 original
```

AFTER (line 6635):
```rust
let gate_penalty_factor = 0.80;  // W18: less aggressive, lets gated skills compete
```
```

### 2b. Formula / Algorithm Description

If the change involves a formula, write it out explicitly with variable names:

```markdown
**Formula:** `final_score = raw_score * gate_penalty_factor`
- `raw_score` = sum of keyword + name + desc + use_case + intent bonuses
- `gate_penalty_factor` = 0.80 when skill fails domain gate check, 1.0 when it passes
- Effect: gated skills lose 20% of their score instead of 65% (old: 0.35) or 100% (hard block)
```

### 2c. Why This Change (Hypothesis)

State the specific hypothesis you're testing:

```markdown
**Hypothesis:** Gold skills like `axiom-swiftdata` fail the iOS domain gate because the prompt
"migrate Core Data to SwiftData" doesn't contain "ios" or "swift" literally. At penalty=0.35,
these skills get raw_score * 0.35 ≈ 280 points, which is below the top-10 cutoff of ~400.
At penalty=0.80, they get raw_score * 0.80 ≈ 640 points, enough to enter top-10.
```

### 2d. Per-Prompt Impact (Detailed)

For EVERY prompt that changed score (up OR down), document:

```markdown
**Per-prompt impact of gate penalty 0.35→0.80:**
| Prompt | Before | After | Delta | Explanation |
|--------|--------|-------|-------|-------------|
| P14 | 2/5 | 3/5 | +1 | axiom-swiftdata: was #14 (score 0.35*800=280), now #8 (0.80*800=640) |
| P19 | 2/5 | 3/5 | +1 | axiom-swiftui-layout: was #18 (280), now #9 (640) |
| P53 | 3/5 | 2/5 | -1 | REGRESSION: ios-test-runner: was gated out, now at #7 pushing out gold test-simulator |
```

**ALWAYS explain regressions.** If a change caused ANY prompt to lose points, explain exactly which non-gold skill displaced which gold skill and why.

### 2e. Rejected Approach Details

For approaches you tried and reverted, document the SAME level of detail:

```markdown
**REJECTED: desc_match weight 60→75**
- Score: 325→325 (net zero: +5 on P12,P14,P29,P55,P67 / -5 on P3,P8,P19,P40,P94)
- Why it failed: Gold skill `axiom-memory-debugging` gained +15 desc points on P12,
  but non-gold `codebase-audit-and-fix` also gained +15 desc points on P3, displacing
  `js-code-fixer` (which had desc=0). The weight increase is not differential — it
  helps gold and non-gold equally when both have description matches.
- Lesson: Weight increases only work when gold skills have MORE of that signal than
  non-gold. For desc_match, the average is: gold=2.1, non-gold=1.8 — too close.
```

## Section 3: Structural Analysis

Document the scoring pipeline state AFTER all your changes:

```markdown
## Final Scoring Pipeline Parameters

| Parameter | Value | Location (line) | Changed from |
|-----------|-------|-----------------|--------------|
| ABSOLUTE_ANCHOR | 1000.0 | 6850 | unchanged |
| min_score filter | 0.5 | 6274 | unchanged |
| name_match bonus | 150/300+350n | 6380 | unchanged |
| desc_match cap/weight | 7 * 60 = 420 | 6410 | unchanged |
| use_case cap/weight | 5 * 65 = 325 | 6430 | unchanged |
| coherence bonus/cap | 50/kw, cap 400 | 6450 | was cap 200 |
| gate_penalty_factor | 0.80 | 6635 | was 0.35 |
| whole_name_bonus | 2000+1000*(parts-1) | 6500 | NEW |
| kw_damping L1 | -60/kw from 4th, cap 500 | 6475 | was -40/kw from 5th, cap 300 |
| kw_damping L2 | removed | — | was -25/kw from 7th, cap 200 |

### Relative Score Formula
```rust
fn calculate_relative_score(score: i32, max_score: i32) -> f64 {
    let relative = (score as f64) / (max_score as f64);
    let absolute_floor = ((score as f64) / 1000.0).min(0.5);  // SACRED: do not change
    relative.max(absolute_floor)
}
```
```

## Section 4: Synonym Expansions Inventory

If you added synonyms, list EVERY expansion with the exact trigger condition and added terms:

```markdown
## Synonym Expansions Added

| # | Trigger Condition | Terms Added | Prompts Targeted |
|---|-------------------|-------------|-----------------|
| 1 | msg.contains("split view") && msg.contains("ipad") | "swiftui layout adaptive multitasking sidebar navigation axiom-swiftui-layout" | P19 (iPad split view) |
| 2 | msg.contains("marketplace") \|\| msg.contains("publish plugin") | "github marketplace setup plugin registry distribution cpv-validate-marketplace setup-github-marketplace" | P83 (marketplace) |
| 3 | msg.contains("release") && (msg.contains("management") \|\| msg.contains("version")) | "version bump changelog tagging git workflow commit release-management" | P29 (release workflow) |

**Guard conditions that prevent false matches:**
- Expansion #1 requires BOTH "split view" AND "ipad" to avoid firing on web split-pane prompts
- Expansion #2 uses "publish plugin" as alternative trigger to avoid matching "marketplace" in unrelated contexts
```

## Section 5: Near-Miss Analysis

Document skills that are JUST outside the top-10 boundary — these are the easiest wins for the next cycle:

```markdown
## Near-Miss Skills (positions 11-15)

| Prompt | Gold Skill | Position | Score | Gap to #10 | Blocker |
|--------|-----------|----------|-------|------------|---------|
| P37 | pr-review-and-fix | 20 | 0.500 | 0.224 | 15 skills tied at 0.500, no whole-name match |
| P52 | chrome-devtools | 13 | 0.762 | 0.012 | axiom-instruments at #10 (0.774), has framework=ios |
| P88 | eoa-experimenter | 12 | 0.730 | 0.008 | think-harder at #10 (0.738), has 3 kw matches |
```

## Section 6: Generalizability Self-Assessment

For EACH change, rate its overfit risk:

```markdown
| Change | Risk | Reasoning |
|--------|------|-----------|
| Gate penalty 0.80 | MEDIUM | Tuned on training set where many gold skills are iOS-gated. If test set has domain-aligned prompts, 0.80 might be too lenient. |
| Whole-name matching | LOW | Structural — detects skill names in prompt regardless of prompt content. Works for any skill/prompt pair. |
| Synonym "split view" + "ipad" | HIGH | Targets specific P19 prompt. If no test prompt mentions "split view" + "ipad", this adds zero value. |
```
