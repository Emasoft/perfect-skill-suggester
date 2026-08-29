---
name: benchmark-competition-methodology
description: "how to iteratively improve the PSS scorer via multi-agent worktree competition against a gold-standard benchmark — process phases, anti-overfitting train/test split"
ocd: 2026-07-16
lmd: 2026-07-23
metadata:
  node_type: memory
  type: project
  tier: component
publish-globally: false
---

# Benchmark-Driven Competition Methodology

**Purpose:** Iteratively improve a scoring/matching engine by running independent AI agents in competition, measuring results against a gold-standard benchmark, merging the winner, and repeating.

## Process Overview

### Phase 1: Benchmark Creation
^0W3NEZTV [desc:"How to build the gold-standard benchmark: realistic prompts targeting 5 gold items each, grouped by coherent domain, output as prompts JSONL + gold JSON.", keywords:"benchmark_creation realistic_prompts gold_standard domain_grouping prompts_jsonl", type:project, ocd:2026-07-16, lmd:2026-07-17]
1. Read the full data index (e.g., skill-index.json with 622 skills)
2. Create 100 realistic prompts, each targeting exactly 5 gold-standard items
3. **CRITICAL: Realistic, not random.** Random skill combos (e.g., "iOS profiling + data visualization + session memory") are useless — baseline scored 70/500 on random vs 94/500 on realistic
4. Group gold items by coherent domains (all-iOS, all-CI/CD, all-frontend, etc.)
5. Write natural language prompts (1-3 sentences, developer context)
6. Include variety: questions, commands, bug reports, feature requests
7. Output: prompts JSONL + gold answers JSON

### Phase 2: History Report
^0WTZWVNK [desc:"Maintain a full history report of every cycle (successes+failures+lessons+bottlenecks) since it is the agents' training data.", keywords:"history_report methodology_improvement_history key_insights remaining_bottlenecks training_data", type:project, ocd:2026-07-16, lmd:2026-07-17]
1. Maintain a comprehensive `methodology-improvement-history.md`
2. Include ALL past cycles — successes AND failures with detailed analysis
3. For each failed approach: what was tried, why it failed, quantified impact
4. For each successful approach: what worked, why, quantified impact
5. Include "Key Insights" section with actionable lessons (e.g., "IDF should boost, not penalize")
6. Include "Remaining Bottlenecks" section with analysis of zero-hit prompts
7. **This report is the agents' training data** — its quality directly affects next-cycle results

### Phase 3: Worktree Competition
^1CKAZT8S [desc:"Run 3 independent Opus agents in separate git worktrees, each given the history report and a target score to beat, running in background.", keywords:"worktree_competition independent_agents beat_current_best run_in_background opus_agents", type:project, ocd:2026-07-16, lmd:2026-07-17]
1. Create 3 git worktrees from the same commit (e.g., pss-w7, pss-w8, pss-w9)
2. Launch 3 independent Opus agents, each in its own worktree
3. Each agent receives:
   - The full history report (successes + failures)
   - The original methodology errors report
   - Goal: beat the current best score (e.g., "beat 156/500")
   - Freedom to choose which improvements to implement
4. Each agent must:
   - Read history and learn from past mistakes
   - Implement changes to the scorer
   - Run all tests (must pass)
   - Build release binary
   - Run the full benchmark
   - Write a detailed report
5. Agents run in background (`run_in_background: true`)

### Phase 4: Evaluation
^1GBZUS17 [desc:"Collect and verify each agent's benchmark score, re-running the benchmark independently if needed, and declare the highest-scoring winner.", keywords:"evaluation collect_scores verify_independently declare_winner", type:project, ocd:2026-07-16, lmd:2026-07-17]
1. Collect scores from all 3 agents
2. Read their reports for insights
3. Verify scores independently if needed (re-run benchmark)
4. Declare winner (highest total hits out of 500)

### Phase 5: Merge & Iterate
^32DVLP2C [desc:"Extract the winning worktree's patch, apply it to main, commit with the score delta, rebuild the release binary, remove worktrees, update the history report, and repeat.", keywords:"merge_winner git_diff_patch apply_patch rebuild_binary remove_worktrees iterate_cycle", type:project, ocd:2026-07-16, lmd:2026-07-17]
1. Extract patch from winning worktree: `git diff > patch.diff`
2. Apply patch to main: `git apply patch.diff`
3. Commit with descriptive message including score improvement
4. Build release binary, copy to bin/
5. Remove all 3 worktrees
6. Update history report with this cycle's results (ALL agents, winners and losers)
7. Create 3 new worktrees and repeat

## Benchmark Protocol

### Running benchmarks
^52COHXS5 [desc:"The benchmark-running script and scoring rule: count gold-skill hits per prompt in the top-10 output, out of 500 total across 100 prompts.", keywords:"benchmark_protocol scoring_script top_10_hits total_hits_500 gold_skills_per_prompt", type:project, ocd:2026-07-16, lmd:2026-07-17]
```python
import subprocess, json

BINARY = 'path/to/pss'
PROMPTS = 'docs_dev/benchmark-v2-prompts-100.jsonl'
GOLD = 'docs_dev/benchmark-v2-gold-100.json'

with open(GOLD) as f:
    gold = json.load(f)
with open(PROMPTS) as f:
    prompts = [l.strip() for l in f if l.strip()]

total_hits = 0
for i, line in enumerate(prompts, 1):
    proc = subprocess.run([BINARY, '--format', 'json', '--top', '10'],
        input=line, capture_output=True, text=True, timeout=30)
    try:
        results = json.loads(proc.stdout)
        suggested = [r.get('name','') for r in results] if isinstance(results, list) else []
    except:
        suggested = []
    hits = sum(1 for s in gold.get(str(i), []) if s in suggested)
    total_hits += hits

print(f'Score: {total_hits}/500')
```

### Scoring
- Primary metric: total gold hits across 100 prompts (max 500)
- Each prompt has 5 gold skills; count how many appear in top-10 output
- Secondary: prompts with >=3/5 hits
- Tertiary: prompts with 0/5 hits (should decrease each cycle)

## Key Lessons Learned

^5GMAEEON [desc:"What works (independent competing agents, full history, realistic benchmarks, iteration, freedom) vs what doesn't (prescribing fixes, random benchmarks, hiding failures, multiplicative/quadratic scaling) and common agent mistakes to flag.", keywords:"what_works what_doesnt common_agent_mistakes idf_as_penalty multiplicative_penalty_stacking quadratic_scaling", type:project, ocd:2026-07-16, lmd:2026-07-17]

### What Works
- **Independent agents competing** — different agents find different solutions
- **Comprehensive history reports** — agents learn from each other's failures
- **Realistic benchmarks** — random skill combos are useless
- **Iterative cycles** — each cycle builds on merged winner, raising the floor
- **Freedom to choose** — don't prescribe which fixes; let agents decide

### What Doesn't Work
- **Prescribing specific fixes** — agents make better decisions when they read the full report
- **Random benchmarks** — random skill combos create impossible prompts
- **Skipping failure details** — agents MUST know what failed and why
- **Stacking multiplicative penalties** — compounds devastatingly
- **Quadratic scaling** — amplifies false positives more than true positives

### Common Agent Mistakes (include in prompts)
- Using IDF as a penalty multiplier instead of a bonus
- Stacking independent score reductions (IDF * BM25 * length_norm)
- Being too aggressive with normalization floors
- Not testing incrementally (combining multiple changes without measuring each)

## Score Progression
^A9D2HIH8 [desc:"The scored history of each competition cycle from 20/500 baseline up to 610/1000 by cycle 5, with the key innovation per cycle.", keywords:"score_progression cycle_history train_test_split innovation_per_cycle", type:project, ocd:2026-07-16, lmd:2026-07-17]
| Cycle | Winner | Score | Delta | Key Innovation |
|-------|--------|-------|-------|---------------|
| 1 R1 | none | 20-34/500 | -51% to -71% | ALL failed (IDF as penalty) |
| 1 R2 | W3 | 98/500 | +4.3% | IDF [0.85,1.5] as bonus, coherence bonus |
| 2 | W5 | 156/500 | +57.6% | Absolute score floor in relative normalization |
| 3 | W8 | 312/500 | +100% | 100+ synonym expansions, use_cases matching, tuned bonuses |
| 4 | W11 | 537/1000* | +1.3% | KW damping, use_case weight↑, anti-overfitting (200 prompts) |
| 5 | W18 | 610/1000* | +13.6% | Whole-name matching, gate penalty 0.80, 150+ synonyms, evidence tiebreak |

*Cycles 4-5 use train/test split (200 prompts). Cycle 5: Train 392, Test 218, Gap 174.

## Files Involved
^B0YV0FFY [desc:"The concrete file paths involved in the benchmark pipeline: the scorer source, the history doc, the prompt/gold JSON pairs, per-agent reports, the original errors doc.", keywords:"files_involved scorer_source_path benchmark_prompts_path gold_answers_path", type:project, ocd:2026-07-16, lmd:2026-07-17]
- `rust/skill-suggester/src/main.rs` — the scorer (9388 lines)
- `docs_dev/methodology-improvement-history.md` — comprehensive history
- `docs_dev/benchmark-v2-prompts-100.jsonl` — 100 realistic prompts
- `docs_dev/benchmark-v2-gold-100.json` — gold answers (5 skills per prompt)
- `docs_dev/worktree-wN-report.md` — per-agent reports
- `docs_dev/pss-methodology-errors-20260301.md` — original 15 methodology errors

## Phase 6: Anti-Overfitting (Train/Test Split) — Added in Cycle 4

^F30D5QDQ [desc:"Guard against agents overfitting the visible 100 benchmark prompts by holding out a second, unseen 100-prompt test set and scoring train vs test separately to reveal generalization gaps.", keywords:"anti_overfitting train_test_split held_out_test_set overfit_gap generalization_metric", type:project, ocd:2026-07-16, lmd:2026-07-17]

### Problem
After multiple cycles, agents may "overfit" — their synonym expansions and scoring tweaks increasingly target the specific 100 benchmark prompts rather than generalizing. This is exactly like overfitting in ML.

### Solution: Held-Out Test Set
1. **Create a second benchmark** (100 new prompts, IDs 101-200) with a different seed
2. The new prompts must:
   - Cover different scenarios from the first 100 (no duplicates)
   - Use the same realistic methodology (coherent domain combos, 5 gold skills)
   - Be created by a separate Opus agent that doesn't see the scorer
3. **Agents receive ONLY the first 100 prompts** + their results from the current baseline
   - They can analyze which prompts they're failing and why
   - They can add synonyms/features targeting those prompts
4. **Scoring uses ALL 200 prompts** (the agents never saw prompts 101-200)
   - Max score becomes 1000 (200 prompts * 5 gold skills)
   - Train score (prompts 1-100) vs Test score (prompts 101-200) reveals overfitting
   - If train >> test, the agent overfit; if train ≈ test, changes generalize

### What Agents Receive
- Full history report (all cycles, successes + failures)
- The first 100 prompts with gold answers (their "training set")
- The current baseline's results on those 100 prompts (so they can see what's failing)
- **NOT** the second 100 prompts (held-out test set)

### What the Orchestrator Does After Agents Complete
1. Run ALL 200 prompts through each agent's binary
2. Score separately: train (1-100) and test (101-200)
3. Report both scores — the test score is the TRUE performance
4. Merge the winner based on COMBINED score (train + test)

### Benchmark File Layout
```
docs_dev/benchmark-v2-prompts-100.jsonl        # IDs 1-100 (training set)
docs_dev/benchmark-v2-gold-100.json            # Gold for 1-100
docs_dev/benchmark-v2-prompts-101-200.jsonl    # IDs 101-200 (held-out test set)
docs_dev/benchmark-v2-gold-101-200.json        # Gold for 101-200
docs_dev/benchmark-v2-prompts-200.jsonl        # Combined (created by concatenation)
docs_dev/benchmark-v2-gold-200.json            # Combined gold
```

### Generalization Metrics
| Metric | Formula | Meaning |
|--------|---------|---------|
| Train score | hits on prompts 1-100 / 500 | How well agent fits known data |
| Test score | hits on prompts 101-200 / 500 | How well agent generalizes |
| Overfit gap | train - test | >50 points suggests overfitting |
| Combined | train + test / 1000 | Overall performance |

### Why This Matters for the Skill
The skill should:
- Support configurable train/test splits
- Always create held-out test sets in multi-cycle runs
- Report train vs test scores separately
- Flag overfitting when gap exceeds threshold
- Optionally rotate: after N cycles, swap train/test sets

---

## Skill Formalization Notes
^FRGNBKIX [desc:"Requirements for automating this methodology into a skill: worktree/agent/benchmark automation, enforced test+build+report gates, configurable cycles/agents, train/test support, machine-readable history.", keywords:"skill_formalization automate_worktrees enforce_tests_pass configurable_cycles machine_readable_history", type:project, ocd:2026-07-16, lmd:2026-07-17]
- The skill should automate: worktree creation, agent launching, benchmark running, result comparison, winner merging
- Input: path to binary source, path to benchmark prompts/gold, number of agents (default 3)
- Output: merged winning code, updated history report, score comparison table
- The skill should enforce: test passing, binary building, report writing
- Consider: configurable number of cycles, early stopping if no improvement
- Must support train/test split for anti-overfitting (see Phase 6)
- Should report per-prompt breakdown for debugging
- Should support "continue from cycle N" for interrupted sessions
- History report is the critical artifact — must be machine-readable enough for agents to parse

## Governed by
- [[pss-knowledge-hub]] — entry point to PSS's PROJECT-scope memory corpus.

## Notes and lessons learned
