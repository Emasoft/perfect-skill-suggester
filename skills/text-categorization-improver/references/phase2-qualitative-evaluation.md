# Phase 2: Qualitative Evaluation (LLM-as-Judge)

## Step 2.1: Generate Evaluation Samples

Sample 15-25 random inputs from your dataset. For each:
1. Run the algorithm to produce its output
2. Write an evaluation task file containing:
   - The input (what was given to the algorithm)
   - The algorithm's output (what it produced)
   - Evaluation instructions (grade quality, identify errors, suggest fixes)

## Step 2.2: Spawn Evaluator Agents (Opus)

Launch 3-5 batch evaluator agents (Opus), each reviewing 5 samples:

Each evaluator grades each output on:
- **Quality grade** (A/B/C/D/F)
- **Irrelevant items** -- what doesn't belong
- **Missing items** -- what should be there but isn't
- **Ranking issues** -- are top items actually best?
- **Root cause hypothesis** -- WHY is the algorithm making this mistake?

## Step 2.3: Aggregate Findings (Opus)

Spawn an aggregation agent to synthesize all evaluator reports:
- Grade distribution across all samples
- Top 10 prioritized improvements with specific code changes
- Quick wins (implementable in <2 hours)
- Structural limitations that can't be fixed with parameter tuning
- Data quality issues in the training/index data

## Step 2.4: Update Progress Ledger

Record the qualitative findings, grade distribution, and identified improvements.
