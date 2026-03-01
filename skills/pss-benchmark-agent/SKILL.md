# PSS Benchmark Agent Documentation Protocol

You are an Opus agent competing to improve the PSS scoring engine. This skill defines the MANDATORY documentation standards for your work. Your report is the TRAINING DATA for future agents — its quality directly determines whether the next cycle succeeds or fails.

## REPORT FILE

Write your report to: `docs_dev/worktree-{YOUR_ID}-report.md`

## MANDATORY REPORT SECTIONS

### Section 1: Score Progression Table

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

### Section 2: Change Details (For EACH Change)

For every change (kept or reverted), document ALL of the following:

#### 2a. Exact Code Diff

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

#### 2b. Formula / Algorithm Description

If the change involves a formula, write it out explicitly with variable names:

```markdown
**Formula:** `final_score = raw_score * gate_penalty_factor`
- `raw_score` = sum of keyword + name + desc + use_case + intent bonuses
- `gate_penalty_factor` = 0.80 when skill fails domain gate check, 1.0 when it passes
- Effect: gated skills lose 20% of their score instead of 65% (old: 0.35) or 100% (hard block)
```

#### 2c. Why This Change (Hypothesis)

State the specific hypothesis you're testing:

```markdown
**Hypothesis:** Gold skills like `axiom-swiftdata` fail the iOS domain gate because the prompt
"migrate Core Data to SwiftData" doesn't contain "ios" or "swift" literally. At penalty=0.35,
these skills get raw_score * 0.35 ≈ 280 points, which is below the top-10 cutoff of ~400.
At penalty=0.80, they get raw_score * 0.80 ≈ 640 points, enough to enter top-10.
```

#### 2d. Per-Prompt Impact (Detailed)

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

#### 2e. Rejected Approach Details

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

### Section 3: Structural Analysis

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

### Section 4: Synonym Expansions Inventory

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

### Section 5: Near-Miss Analysis

Document skills that are JUST outside the top-10 boundary — these are the easiest wins for the next cycle:

```markdown
## Near-Miss Skills (positions 11-15)

| Prompt | Gold Skill | Position | Score | Gap to #10 | Blocker |
|--------|-----------|----------|-------|------------|---------|
| P37 | pr-review-and-fix | 20 | 0.500 | 0.224 | 15 skills tied at 0.500, no whole-name match |
| P52 | chrome-devtools | 13 | 0.762 | 0.012 | axiom-instruments at #10 (0.774), has framework=ios |
| P88 | eoa-experimenter | 12 | 0.730 | 0.008 | think-harder at #10 (0.738), has 3 kw matches |
```

### Section 6: Generalizability Self-Assessment

For EACH change, rate its overfit risk:

```markdown
| Change | Risk | Reasoning |
|--------|------|-----------|
| Gate penalty 0.80 | MEDIUM | Tuned on training set where many gold skills are iOS-gated. If test set has domain-aligned prompts, 0.80 might be too lenient. |
| Whole-name matching | LOW | Structural — detects skill names in prompt regardless of prompt content. Works for any skill/prompt pair. |
| Synonym "split view" + "ipad" | HIGH | Targets specific P19 prompt. If no test prompt mentions "split view" + "ipad", this adds zero value. |
```

## ANTI-PATTERNS (Things That Waste Future Agents' Time)

### DO NOT write vague descriptions:
- BAD: "Increased use-case weight for better matching"
- GOOD: "Changed `uc_bonus = uc_match_count * 65` to `uc_bonus = uc_match_count * 75` at line 6430. Score: 325→325 (net zero). Gold avg uc_match=2.37, non-gold avg=1.46. The 62% differential should help, but the absolute bonus increase (+10*2.37=+24 for gold, +10*1.46=+15 for non-gold) was too small to change any ranking boundary."

### DO NOT skip rejected approaches:
- BAD: "Also tried several other weight changes, none worked"
- GOOD: Table with exact values, scores, and explanations for EACH attempt

### DO NOT describe algorithms in prose only:
- BAD: "Added a penalty for skills with many keywords but no name match"
- GOOD: Show the exact Rust code block with the if-condition, the formula, the cap, and explain each variable

### DO NOT forget the baseline:
- BAD: "Final score: 333/500"
- GOOD: "Baseline: 314/500 (measured before any changes). Final score: 333/500 (+19). Score progression: 314→106→278→312→318→322→325→326→330→332→333"

## SACRED PARAMETERS (DO NOT CHANGE — PROVEN ACROSS 5 CYCLES)

These parameters have been independently validated by 3+ agents across multiple cycles. Changing them ALWAYS causes regression:

```rust
// Score floor formula — the #1 most important scoring innovation (Cycle 2, W5)
const ABSOLUTE_ANCHOR: f64 = 1000.0;  // DO NOT CHANGE (W16 tried 1600: -208 catastrophe)
let absolute_floor = ((score as f64) / ABSOLUTE_ANCHOR).min(0.5);  // DO NOT remove .min(0.5)

// Changing ANCHOR to 1100: -10 regressions (W17 Cycle 5)
// Changing ANCHOR to 800: crowding (W11 Cycle 4)
// Removing .min(0.5): absolute floor overwhelms relative scores (W16 Cycle 5)
```

**DF dampening on tools/frameworks:** Independently rejected 3 times (W6 Cycle 2, W16 Cycle 5 x2). DEFINITIVELY harmful. Do not attempt.

## BENCHMARK RESULTS TRACKING (SEPARATE FILE — MANDATORY)

**CRITICAL: Use a SEPARATE file for per-prompt benchmark results.** The per-prompt tracking can grow to thousands of lines. Your report file must stay concise. Write benchmark results to:

`docs_dev/worktree-{AGENT_ID}-benchmark-log.md`

### Benchmark Log Format

After EVERY benchmark run, append a section to the benchmark log:

```markdown
## Run #{N}: {description of change}
Timestamp: {ISO 8601}
Score: {score}/500 (delta: {+/-N} from previous)

### Per-Prompt Results (only changed prompts)
| Prompt | Before | After | Delta | Gold Skills Affected | Explanation |
|--------|--------|-------|-------|---------------------|-------------|
| P14 | 2/5 | 3/5 | +1 | axiom-swiftdata moved #14→#8 | whole-name match added 4000pts |
| P53 | 3/5 | 2/5 | -1 | ios-test-runner displaced gold test-simulator | gate penalty too lenient |

### Full Top-10 Dump (for prompts that changed)
#### P14 (before):
1. skill-a (0.85) 2. skill-b (0.77) ... 10. skill-j (0.52)
#### P14 (after):
1. skill-a (0.85) 2. skill-b (0.77) ... 8. axiom-swiftdata (0.64) ... 10. skill-k (0.50)
```

**Rules:**
- EVERY benchmark run gets logged, even if score didn't change (document "no change" with explanation)
- Only log prompts that CHANGED score — don't dump all 100 every time
- For regressions: ALWAYS dump the full before/after top-10 so the next agent can diagnose
- The benchmark log is append-only — never delete previous runs
- Your final REPORT references the benchmark log but doesn't duplicate it

### How to Run the Benchmark

```bash
# Run the benchmark and save per-prompt results
python3 -c "
import subprocess, json, sys
BINARY = './target/release/skill-suggester'
PROMPTS = 'docs_dev/benchmark-v2-prompts-100.jsonl'
GOLD = 'docs_dev/benchmark-v2-gold-100.json'
with open(GOLD) as f: gold = json.load(f)
with open(PROMPTS) as f: prompts = [l.strip() for l in f if l.strip()]
total_hits = 0
for i, line in enumerate(prompts, 1):
    proc = subprocess.run([BINARY, '--format', 'json', '--top', '10'],
        input=line, capture_output=True, text=True, timeout=30)
    try:
        results = json.loads(proc.stdout)
        suggested = [r.get('name','') for r in results] if isinstance(results, list) else []
    except: suggested = []
    hits = sum(1 for s in gold.get(str(i), []) if s in suggested)
    total_hits += hits
    print(f'P{i}: {hits}/5 | suggested: {suggested[:5]}...')
print(f'\\nTotal: {total_hits}/500')
"
```

Save the full output to the benchmark log, then update your work tracker.

---

## WORK TRACKING CHECKLIST

**COPY THIS ENTIRE BLOCK to the TOP of your report file immediately when you start working.** Update it as you go. This is your task tracker — it ensures you never skip documentation.

```markdown
# {AGENT_ID} Work Tracker

## Phase 1: Setup
- [ ] Read methodology-improvement-history.md (FULL file)
- [ ] Read baseline-per-prompt-results.txt (training set results)
- [ ] Read main.rs (FULL file, note line count)
- [ ] Run baseline benchmark (RECORD THE NUMBER before any changes)
- [ ] Baseline score: ___/500

## Phase 2: Implementation (update after EACH change)
- [ ] Change 1: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
- [ ] Change 2: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
- [ ] Change 3: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
- [ ] Change 4: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
- [ ] Change 5: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
- [ ] Change 6: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
- [ ] Change 7: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
- [ ] Change 8: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
(add more rows as needed)

## Phase 3: Testing & Build
- [ ] All cargo tests pass (record count: ___/___)
- [ ] cargo build --release succeeds
- [ ] Final benchmark score confirmed: ___/500

## Phase 4: Report Writing (MANDATORY — do NOT skip)
- [ ] Section 1: Score progression table (ALL changes, kept AND reverted)
- [ ] Section 2: Change details for EACH change:
  - [ ] 2a. Exact code diff (before/after with line numbers)
  - [ ] 2b. Formula/algorithm with variable names
  - [ ] 2c. Hypothesis (why you expected this to help)
  - [ ] 2d. Per-prompt impact table (every prompt that changed)
  - [ ] 2e. Regression explanations (if any prompt lost points)
- [ ] Section 3: Rejected approaches (SAME detail level as kept changes)
- [ ] Section 4: Final parameter summary table (all values, all line numbers)
- [ ] Section 5: Synonym expansion inventory (if any added)
- [ ] Section 6: Near-miss analysis (gold skills at positions 11-15)
- [ ] Section 7: Generalizability self-assessment per change
- [ ] Section 8: Remaining 0-hit and 1-hit prompts with blocker analysis

## Phase 5: Final Verification
- [ ] Report written to docs_dev/worktree-{AGENT_ID}-report.md
- [ ] Report contains ALL sections above
- [ ] No section says "also tried several things" without details
- [ ] Every rejected approach has: exact values, score, per-prompt delta, explanation
- [ ] Every code change shows actual Rust code (not just prose)
```

**WHY THIS MATTERS:** Your report becomes the training data for the next 3 agents. If you write "changed a weight, didn't work" without saying WHICH weight, WHAT value, and WHAT score, the next agent will waste time trying the exact same thing. Every detail you skip costs the next cycle ~30 minutes of redundant work.
