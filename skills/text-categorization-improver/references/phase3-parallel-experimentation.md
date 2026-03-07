# Phase 3: Parallel Experimentation (3 Worktrees)

## Step 3.1: Create 3 Git Worktrees

```bash
git worktree add .claude/worktrees/exp-w1 -b improve/exp-w1
git worktree add .claude/worktrees/exp-w2 -b improve/exp-w2
git worktree add .claude/worktrees/exp-w3 -b improve/exp-w3
```

## Step 3.2: Assign Experiment Focus

Based on the qualitative evaluation findings, assign each worktree a different improvement strategy:

| Worktree | Focus | Example |
|----------|-------|---------|
| W1 | Quick wins / low-hanging fruit | Remove hard-coded biases, fix scoring bugs |
| W2 | Algorithmic improvements | Add name affinity boost, domain penalties |
| W3 | Structural changes | New scoring signals, different normalization |

**Important:** Each worktree targets DIFFERENT aspects of the algorithm. Changes must be non-conflicting so they can be merged later.

## Step 3.3: Launch Researcher Agents (Opus)

Spawn 3 background researcher agents (one per worktree). Each agent:
1. Reads the qualitative evaluation report for context
2. Reads the specific improvement tasks assigned to their worktree
3. Edits the algorithm source code
4. Builds and runs the benchmark
5. Iterates up to 5-7 times to maximize their score
6. Writes a report with: final score, all iterations tried, what worked and what didn't
7. Commits their changes

## Step 3.4: Collect Results

Wait for all 3 agents to complete. Record each worktree's score in the progress ledger.
