# Test Mode

With `--test "PROMPT"`, simulate matching against the provided prompt:

```
/pss-status --test "help me set up github actions for ci"
```

Output:

```
╔══════════════════════════════════════════════════════════════╗
║                     TEST RESULTS                             ║
╠══════════════════════════════════════════════════════════════╣
║ Input Prompt:                                                ║
║   "help me set up github actions for ci"                    ║
║                                                              ║
║ Expanded Prompt (after synonym expansion):                   ║
║   "help me set up github actions for ci cicd deployment     ║
║    automation"                                               ║
╠══════════════════════════════════════════════════════════════╣
║                   MATCHED SKILLS                             ║
╠══════════════════════════════════════════════════════════════╣
║ Rank │ Skill             │ Score │ Conf.  │ Matches         ║
╠══════════════════════════════════════════════════════════════╣
║  1   │ devops-expert     │  18   │ HIGH   │ github, actions,║
║      │                   │       │        │ ci, set up ci   ║
║  2   │ github-workflow   │  14   │ HIGH   │ github, actions ║
║  3   │ ci-pipeline       │   9   │ MEDIUM │ ci, deployment  ║
║  4   │ automation-expert │   6   │ MEDIUM │ automation      ║
╚══════════════════════════════════════════════════════════════╝

Recommendation: devops-expert (HIGH confidence)
Commitment: "Before implementing: Evaluate YES/NO - Will this skill solve the user's actual problem?"
```
