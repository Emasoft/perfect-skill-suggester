# Anti-Patterns (Things That Waste Future Agents' Time)

## Table of Contents

- [DO NOT write vague descriptions](#do-not-write-vague-descriptions)
- [DO NOT skip rejected approaches](#do-not-skip-rejected-approaches)
- [DO NOT describe algorithms in prose only](#do-not-describe-algorithms-in-prose-only)
- [DO NOT forget the baseline](#do-not-forget-the-baseline)

## DO NOT write vague descriptions:
- BAD: "Increased use-case weight for better matching"
- GOOD: "Changed `uc_bonus = uc_match_count * 65` to `uc_bonus = uc_match_count * 75` at line 6430. Score: 325→325 (net zero). Gold avg uc_match=2.37, non-gold avg=1.46. The 62% differential should help, but the absolute bonus increase (+10*2.37=+24 for gold, +10*1.46=+15 for non-gold) was too small to change any ranking boundary."

## DO NOT skip rejected approaches:
- BAD: "Also tried several other weight changes, none worked"
- GOOD: Table with exact values, scores, and explanations for EACH attempt

## DO NOT describe algorithms in prose only:
- BAD: "Added a penalty for skills with many keywords but no name match"
- GOOD: Show the exact Rust code block with the if-condition, the formula, the cap, and explain each variable

## DO NOT forget the baseline:
- BAD: "Final score: 333/500"
- GOOD: "Baseline: 314/500 (measured before any changes). Final score: 333/500 (+19). Score progression: 314→106→278→312→318→322→325→326→330→332→333"
