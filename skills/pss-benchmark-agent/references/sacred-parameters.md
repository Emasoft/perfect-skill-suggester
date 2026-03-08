# Sacred Parameters (DO NOT CHANGE -- PROVEN ACROSS 5 CYCLES)

## Table of Contents

- (No subsections -- this file is a single reference block.)

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
