---
trdd-id: BN5TKE0E
title: Optional semantic reranker over the lexical top-K — staged, kill-gated, off by default
column: refused
created: 2026-07-23T14:31:57+0200
updated: 2026-08-25T18:23:03+0200
current-owner: perfect-skill-suggester
task-type: feature
min-approval-requirement: user
relevant-rules: []
scope: project
---

# Optional semantic reranker over the lexical top-K

**Status: PROPOSAL — design only. No code, no dependency, no model artifact has been
added. Nothing here is authorized to execute until this TRDD is promoted to `planned`.**

Approval tier 2 rationale: the implementation would add (a) a third-party pretrained
model artifact distributed to users, (b) a new runtime dependency inside the
`UserPromptSubmit` hot path shipped in five prebuilt binaries. That is a supply-chain
and latency surface, not a local refactor. This project is standalone, so the USER is
the approver.

---

## 1. What exists today, and why it is good

PSS scoring is purely lexical/heuristic: weighted keyword, intent, name, description,
use-case, domain and framework matching, with synonym expansion
(`expand_synonyms()`, `rust/skill-suggester/src/main.rs:5100`), negation gating, domain
gates, and a large tuned penalty/bonus system. `find_matches()`
(`main.rs:8343`) returns `Vec<MatchedSkill>` sorted by an **integer** score, truncated to
`MAX_SUGGESTIONS = 50` (`main.rs:1439`, `main.rs:9949`).

Measured properties that are **virtues to preserve, not incidental**:

| Property | Evidence |
|---|---|
| Offline, zero network | no HTTP in the hot path |
| Deterministic | explicit tie-break ladder ending in `a.name.cmp(&b.name)` (W12 fix, `main.rs:9944`) |
| Constant time in prompt length | prompt words deduped + capped at 100 (`main.rs` prompt normalization) |
| Fast | measured 327–423 ms wall for the whole binary on this machine (5 runs, hook-JSON mode, 9 475 indexed entries) |
| No model, no weights, no versioned vector space | index is metadata only |
| Auditable | every suggestion carries an `evidence: Vec<String>` trail |

**Any proposal that damages one of those to buy accuracy is a bad trade.** The
zero-dependency fast path stays the default in every scenario below.

## 2. The actual weakness — and why "reranker" is the wrong word for half of it

Stated weakness: *a paraphrase that shares no tokens with a skill's keywords misses.*

That is a **recall** failure, not a **ranking** failure. If the right skill never enters
the lexical top-50, no reranker over the top-50 can surface it. Reranking and recall
expansion are two different instruments:

| Instrument | Fixes | Cost | Risk |
|---|---|---|---|
| **Rerank** — reorder the existing lexical top-K | gold present but at rank 6–10; improves MRR / recall@5 | 1 query encode + K dot products | low; bounded by the survivor set |
| **Recall expansion** — retrieve semantically-near candidates the lexical path never scored | gold absent from top-K entirely | ANN query over the whole corpus | **high**; injects candidates that passed no lexical evidence test |

The stated weakness needs the second. The second is where precision goes to die. So the
proposal is **staged**: rerank first (cheap, bounded, provable), recall expansion only if
rerank passes its gates, and only with a hard cap on injected candidates.

## 3. Prior intent in the repo

`docs/PSS_FILE_FORMAT_SPEC.md:502` already reserves `embedding: Pre-computed semantic
embedding for vector search` as a v2.0 extension. This TRDD is the design that field was
waiting for; whatever ships must keep that spec honest (same field name, documented
dimension and model id).

## 4. Precedent: `pss-nlp` is the template, including its cost

`rust/negation-detector/` builds a **separate** `pss-nlp` binary. `build.rs` calls
`nlprule_build::BinaryBuilder` which **downloads the English model at compile time and
bakes it into the binary** — which is why each `pss-nlp-*` artifact is ~14 MB
(`bin/pss-nlp-darwin-arm64` = 13 965 616 bytes).

It is invoked by `detect_prompt_negations()` (`main.rs:8263`) which:
1. locates the binary by a 3-step search (sibling dir → `$CLAUDE_PLUGIN_ROOT/bin` → `which`),
2. spawns it, writes one JSON line, reads one JSON line,
3. **returns an empty set on every failure path** — not found, spawn failed, non-zero
   exit, unparseable output — with a `debug!` line and nothing user-visible.

That silent-no-op contract is exactly what the reranker must reproduce. But note the
cost the precedent also demonstrates: **five committed 14 MB binaries**. `.git` is
already 1.0 GB. Repeating that pattern for a second model is a real, measured tax.

## 5. Design

### 5.1 Where it runs — three options, one recommendation

| Option | Spawn cost | Model load cost | Binary/repo growth | Verdict |
|---|---|---|---|---|
| **A. Extend `pss-nlp`** with `mode:"embed"` | none extra (already spawned once per `find_matches`) | pays model load on **every** call, including negation-only calls | +model into 5 committed binaries | Rejected — couples two unrelated capabilities; makes today's negation path slower even when rerank is off. |
| **B. New `pss-embed` binary** | +1 process spawn (~10–30 ms on macOS, worse on Windows) | per-spawn model load | +5 more committed binaries | Rejected — a whole process spawn to compute one 256-float vector is absurd overhead. |
| **C. In-process module in `pss`, model as an mmap'd sidecar file** | none | mmap = lazy page-in of only the rows the query's tokens touch | binary grows only by decoder code (~tens of KB); **model is not committed** | **RECOMMENDED** |

Option C also gives a *better* absence contract than `pss-nlp`: no sidecar file ⇒ the
module never initializes ⇒ zero cost, not "spawn-and-fail" cost.

The code ships compiled-in (behind `#[cfg(feature = "rerank")]`, feature **on** in
release builds so all five prebuilt binaries have it); the **model** is the opt-in.

### 5.2 Model choice

Hot-path candidates, judged against the five cross-compiled targets
(`darwin-arm64`, `darwin-x86_64`, `linux-x86_64`, `linux-arm64`,
`windows-x86_64` — the last three built inside `cross` Docker containers):

| Backend | Runtime dep | On-disk | Query encode | 5-target `cross` build | Quality |
|---|---|---|---|---|---|
| **Static distilled embeddings** (model2vec / potion-class, 256-d) | pure Rust, table lookup + mean pool | ~8–30 MB (int8 / f32) | sub-millisecond | safe — no C/C++ | lowest of the three, but non-trivial |
| MiniLM-L6-v2 int8 ONNX (384-d) | `ort` → ONNX Runtime C++ | ~23 MB + runtime lib | ~5–20 ms encode **+ 20–80 ms session init per process** | **high risk** — a C++ runtime per target, `windows-gnu` worst | higher |
| `candle` pure-Rust transformer | pure Rust, heavy compile | ~23 MB | ~10–40 ms cold | moderate; large compile-time hit on 5 targets | higher |
| Hosted embedding API | network | 0 | 100–500 ms + network | n/a | highest |

**Decision: static distilled embeddings for the hot path. ONNX and any network API are
forbidden in the `UserPromptSubmit` path** — a per-process ONNX session init alone can
exceed the entire added-latency budget (§5.5), and the API option destroys the offline
guarantee outright.

`? INFERRED` — the encode-time and quality figures above are from general knowledge of
these model families, **not measured here**. Phase 0 (§7) must measure encode latency and
the accuracy delta on this corpus before a backend is fixed. If the measured static-model
gain is inside the noise band, the answer is "don't build it" (§8).

An ONNX backend MAY later be allowed for the **offline** paths only (`/pss-setup-agent`
AI mode already runs 2–5 minutes). That is out of scope here.

### 5.3 What is embedded, and when

- **Candidate vectors are precomputed at index time**, in the existing enrich stage
  (`pss --pass1-batch`), from `name + description + keywords + use-cases`. 9 475 entries
  × 256 dims × f32 = **~9.7 MB** (~2.4 MB at int8). Stored in the existing CozoDB.
- **Only the query is embedded at hook time** — one forward pass, once per prompt.

Storage needs **no new dependency**: the pinned `cozo-ce 0.7.12` already supports F32
vector columns (`VecElementType::F32`, `src/data/value.rs:329`) and HNSW indices
(`vec_idx_op = {"hnsw" ~ (index_create_adv | index_drop)}`, `src/cozoscript.pest:21`).
`✓ VERIFIED` by reading the vendored crate source at
`~/.cargo/registry/src/index.crates.io-*/cozo-ce-0.7.12/`.

New relation (sketch, not final DDL):

```
:create element_vectors {
    element_id: String
    =>
    model_id: String,      # e.g. "potion-base-8m"
    model_version: String, # bumped on any weight change
    dim: Int,
    vec: <F32; 256>,
    source_hash: String,   # hash of the text that was embedded
    embedded_at: String,
}
```

`model_id`/`model_version`/`dim` are stored **per row** so a mixed-vector-space state is
detectable and refusable rather than silently wrong.

### 5.4 How the score is combined — rank fusion, never score blending

The lexical score is an **integer** with tuned absolute thresholds
(`ConfidenceThresholds { high: 1000, medium: 100 }`, `main.rs:1577`) and a relative-score
floor (`calculate_relative_score`). `skills/pss-benchmark-agent/references/sacred-parameters.md`
exists precisely because these constants are load-bearing. Adding a float cosine into
that integer would silently re-tune every threshold and invalidate the whole benchmark
history.

Rules:

1. **Rerank runs strictly AFTER** all gates, penalties, negation, and domain filtering —
   on the survivor list only. It reorders; it never resurrects a gated-out candidate.
2. **Rank fusion, not score fusion.** Reciprocal-rank fusion over (lexical rank, semantic
   rank), with a **bounded displacement**: no candidate may move more than `D` positions
   (`D = 5` proposed). A bounded move is auditable and caps blast radius.
3. **Confidence labels keep deriving from the LEXICAL score only.** A semantic reorder
   must never be able to promote something to HIGH confidence.
4. **Evidence stays honest**: a reordered candidate gains an evidence token
   `semantic_rerank:+3` (positions moved) so the existing audit trail explains the move.
5. **Determinism**: cosine similarities are quantized to a fixed decimal (1e-4) before
   comparison, and the existing tie-break ladder (type → evidence richness → name)
   remains the final arbiter. Same input ⇒ byte-identical output, as today.

### 5.5 Latency budget

Measured baseline on this machine (hook-JSON mode, 5 runs): **327 / 342 / 360 / 363 /
423 ms**. `hooks.json` allows 10 s and `pss_hook.py` uses an 8 s subprocess timeout — but
the *hard* timeout is irrelevant. The felt cost of a hook that fires on **every**
`UserPromptSubmit` is the product.

| Stage | Budget |
|---|---|
| Query encode (static model, mmap'd) | ≤ 5 ms |
| Fetch K ≤ 50 candidate vectors from Cozo | ≤ 5 ms |
| K × 256 dot products | < 0.1 ms |
| Fusion + reorder | < 0.1 ms |
| (Phase 2 only) HNSW ANN query over 9 475 vectors | ≤ 10 ms |
| **Total added, p95 target** | **≤ 25 ms (~7 % of the current ~350 ms)** |
| **Hard abort** | **50 ms — wall-clock checked; on breach, return the lexical order** |

`PSS_RERANK_MAX_MS` (default 25) is checked before the reorder is applied, so a slow
machine degrades to today's behavior instead of to a slow hook.

### 5.6 Degradation matrix — every branch is a silent no-op

| Condition | Behavior |
|---|---|
| Model sidecar absent (the default) | module never initializes; lexical order; one `debug!` line |
| `dim` mismatch (model vs stored vectors) | refuse to rerank entirely; `debug!`; lexical order |
| `model_version` mismatch | refuse — **never mix vector spaces**; suggest reindex in `/pss-status` |
| Vectors missing for some candidates | those keep their lexical rank; never penalized for missing data |
| Encode/lookup exceeds `PSS_RERANK_MAX_MS` | abort, lexical order |
| Corrupt/truncated model file | refuse at load (magic + length + checksum check); lexical order |
| Any error inside the module | returns `Result::Err`, caller discards and uses lexical order |

**Panic safety is not optional here.** The workspace release profile sets
`panic = "abort"` (`rust/Cargo.toml`), so `catch_unwind` cannot save the hook — a single
panic in the reranker kills the user's prompt submission. Therefore the module must be
**panic-free by construction**: no `unwrap`, no `expect`, no slice indexing, no integer
division without a guard; enforced with `#![deny(clippy::unwrap_used, clippy::expect_used,
clippy::indexing_slicing, clippy::panic)]` at the module boundary, and the deny list is
itself a CI gate.

### 5.7 Config surface

Follows the existing `PSS_*` env-var precedent (`PSS_INDEX_PATH`, `PSS_REGISTRY_PATH`,
`PSS_NO_LOGGING`):

| Var | Default | Meaning |
|---|---|---|
| `PSS_RERANK` | `off` | `off` \| `on` \| `auto` (`auto` = on iff a valid model is installed **and** vectors are current) |
| `PSS_RERANK_MODEL` | `$CLAUDE_PLUGIN_DATA/models/<model_id>.bin` | path override |
| `PSS_RERANK_MODE` | `rerank` | `rerank` \| `hybrid` (Phase 2 only) |
| `PSS_RERANK_MAX_MS` | `25` | wall-clock abort |
| `PSS_RERANK_MAX_SHIFT` | `5` | bounded displacement `D` |

Install/uninstall:
- `/pss-install-reranker` — downloads a **checksum-pinned** release asset into
  `$CLAUDE_PLUGIN_DATA/models/`, then triggers a re-embed. Explicit, user-initiated,
  never automatic, never at hook time. The model is **not** committed to `bin/`.
- Uninstall = delete the file. The next hook run is silently back to lexical.
- `/pss-status` gains: model present / id / version / dim, vectors current vs stale
  count, and the last-run added-latency p50/p95.

### 5.8 Relationship to TRDD-YC51I1C0

A sibling proposal — **TRDD-YC51I1C0, "Distribute platform binaries as GitHub release
assets instead of tracking them in `bin/`"** — proposes exactly the asset-fetch mechanism
this design needs for the model sidecar (checksum-pinned release asset, fetched on demand,
not committed). The two should share one mechanism, not grow two.

Sequencing: if YC51I1C0 is approved, the reranker's `/pss-install-reranker` becomes a thin
caller of its fetcher and kill criterion 7 (footprint) loses most of its force. If
YC51I1C0 is refused — i.e. the project decides everything ships in-repo — then criterion 7
fires immediately for the model too, and the honest answer for this TRDD is *control arm
only, no reranker* (§8.1, §9.1). **This proposal must not build a second, private asset
fetcher.**

## 6. Measurement — how the benefit is proven against the CI accuracy benchmark

This is the part the feature lives or dies on. **The gates below are pre-registered: they
are fixed in this document before any number is known, so the design cannot be retrofitted
to whatever the spike happens to produce.**

### 6.1 The existing harness

`skills/pss-benchmark-agent/` defines the protocol; the corpus lives in gitignored
`docs_dev/` (`benchmark-v3-gold-200.json` = 5 gold element names per prompt,
`benchmark-prompts-*.jsonl` = `{id, prompt, cwd}`), scored as hits-in-top-10 out of
5 per prompt (`Total: N/500` for the 100-prompt set). Another workstream is wiring this
into CI; this TRDD **adds an axis to that job, it does not fork it**.

That in-flight work (`.github/workflows/accuracy-gate.yml` +
`.github/accuracy-thresholds.json`, present in the working tree at the time of writing)
establishes a constraint this design must obey and a rule set it must inherit:

- Exactly one gate is currently `wired`: **`e2e_hook_match_rate`** (floor `1.0`, runner
  `uv run python scripts/pss_test_e2e.py`) — and its own description states *why* it is
  the only reproducible one: `pss_test_e2e.py` **builds a throwaway index from its own
  fixtures** and never reads the developer's installed elements.
- **`agent_profile_accuracy` is `UNWIRED` with `floor: null` precisely because the
  `docs_dev/` gold sets are not reproducible on a clean runner** — they score against
  whatever 9 475 elements happen to be installed on the author's machine.
- The threshold file's editing rules apply verbatim to any gate added here: never lower a
  floor to make CI green; raise a floor only with a re-recorded `baseline` naming commit,
  platform and date; never invent a baseline; `floor: null` on a `wired` gate is treated
  as tampering and hard-fails.

### 6.2 Why the existing gold set alone cannot prove this feature

The v2/v3 gold sets were built and iterated **against the lexical scorer**. They encode
the lexical scorer's own notion of a match, so they systematically under-represent exactly
the paraphrase case this feature targets. A win there would be suspicious; a null result
there would be uninformative. Three datasets are required:

| Set | Purpose | Construction |
|---|---|---|
| **D1** — existing gold (200 prompts) | **regression guard** | as-is |
| **D2** — paraphrase set (target ≥ 150 prompts) | the capability under test | for each D1 prompt, an LLM writes a paraphrase preserving intent; then a **programmatic filter** keeps only paraphrases whose token Jaccard overlap with the gold elements' `name + keywords + description` is **≤ 0.15**. The filter is the guarantee — not the LLM's promise. Gold labels are unchanged. 20 samples human-spot-checked. |
| **D3** — precision/negative set (≥ 60 prompts) | guards against semantic over-triggering | prompts whose correct answer is "suggest nothing" or which are adversarially near-miss (right domain, wrong tool). |

**D2 and D3 must be built against a self-contained fixture index, not the author's
installed elements.** This is not a nicety: `agent_profile_accuracy` sits `UNWIRED` in
`.github/accuracy-thresholds.json` for exactly this reason. Follow the
`scripts/pss_test_e2e.py` pattern — ship the fixture elements, build a throwaway index
from them, score against that. A D2 that only reproduces on one laptop can never become
a CI gate, and a benefit that cannot be gated in CI is a benefit nobody can defend at
review time.

Concretely: the fixture element set must be large enough that recall@5 is meaningful
(a few hundred elements, including deliberate near-miss distractors), and it is committed
(it is test data, not a report). The *prompt/gold* files may live in gitignored
`docs_dev/` during Phase 0, but must move into the committed fixture set before any gate
is wired. Generator script in `scripts_dev/`; the overlap filter (§6.2) is part of the
generator and its threshold is recorded in the dataset header.

### 6.3 Metrics

Per set: `recall@5`, `recall@10`, `MRR@10`, and — mandatory — the **per-prompt
win/loss/tie distribution**, because a positive mean routinely hides a fat regression
tail. Plus `p50/p95/p99` added milliseconds, and a displacement histogram (how far the
reranker actually moved things; a reranker that never moves anything is a no-op wearing a
costume).

### 6.4 Pre-registered CI gates

| # | Gate | Threshold |
|---|---|---|
| G1 | **No-op proof**: with `PSS_RERANK=off`, output is byte-identical to the pre-feature baseline on D1 | exact |
| G2 | D1 `recall@5` (ON) ≥ D1 `recall@5` (OFF) | zero tolerance |
| G3 | D2 `recall@5` (ON) ≥ D2 `recall@5` (OFF) **+ 5.0 absolute points** | the reason to exist |
| G4 | D3 false-suggestion rate (ON) ≤ (OFF) + 1.0 point | precision guard |
| G5 | added latency p95 ≤ 25 ms, p99 ≤ 50 ms, measured across the full D1 run | |
| G6 | on D1, ≤ 2 % of prompts may lose ≥ 1 gold hit, and **no** prompt may lose ≥ 2 | tail guard |
| G7 | all five targets build with the feature enabled, in the real `cross` CI containers | |
| G8 | determinism: 3 consecutive ON runs over D1 produce identical output | |

**Failing any gate ⇒ the feature does not ship enabled.** Failing G3 ⇒ the feature is
abandoned, not tuned until it passes (tuning against the eval set is how a benchmark
becomes a lie).

### 6.5 Mandatory ablation

The report must separate three arms so we learn *which half pays*:
`lexical only` · `rerank-only (reorder top-50)` · `hybrid (recall expansion)`.
Plus the control arm below, which is the whole point of Phase 0.

### 6.6 CI wiring

Add `rerank: [off, on]` to `accuracy-gate.yml`'s matrix, and register the reranker gates
in `.github/accuracy-thresholds.json` under its existing schema (`status`, `runner`,
`metric`, `parsed_from`, `floor`, `baseline`) — with `status: UNWIRED` / `floor: null`
until a baseline is genuinely measured on a CI runner, never a guessed floor.

The `on` leg needs the model asset present in the runner. **If the asset cannot be
cached/fetched in CI, the `on` leg is skipped — and then the feature must not merge in an
enabled state.** An un-gated hot-path feature is not acceptable; shipping it `off` with
no ON-leg evidence is the same as not shipping it.

G5 (latency) is measured on the runner but reported as advisory-with-a-ceiling: CI
hardware is noisy, so the gate is `p95 ≤ 50 ms` in CI while the 25 ms target is enforced
locally on the release machine and recorded in the baseline block.

## 7. Phases

**Phase 0 — spike + the cheap control arm (no shipping, no dependency added).**
Build D2 and D3. Then run the **control arm first**: index-time enrichment already runs
an LLM pass over every element (`--pass1-batch`); have it emit **paraphrase keywords** —
zero runtime cost, zero new dependency, zero new vector space, no model artifact.
Measure D2 with the control arm alone. **If the control closes ≥ 70 % of the achievable
gap, stop here and never build the reranker.** Also measure a static model's encode
latency and accuracy delta offline (a throwaway script, not a shipped dependency), and
measure the share of D1 prompts already solved by `name_match` evidence — if that share
is very high, semantics has little room to work with.

**Phase 1 — rerank only.** Option C module, static backend, precomputed vectors in Cozo,
bounded-displacement rank fusion, `PSS_RERANK` default `off`. Ship only if G1–G8 pass.

**Phase 2 — hybrid recall expansion.** Only if Phase 1 passed. Cozo HNSW ANN query, at
most **2** injected candidates, injected **only** when the lexical top-1 is below the
MEDIUM threshold, and every injected candidate must pass the same gates a lexical
candidate passes. Re-gate against G1–G8 with `PSS_RERANK_MODE=hybrid`.

**Phase 3 (optional, out of scope here).** Higher-quality ONNX backend for offline paths
only (`/pss-setup-agent`), never for the hook.

Each phase is its own TRDD when it is authorized; this one is the umbrella design.

## 8. When this is NOT worth it — explicit kill criteria

Any one of these ends the work. They are listed in the order they will actually fire.

1. **The cheap control arm wins.** Index-time paraphrase-keyword enrichment closes ≥ 70 %
   of the D2 gap. It has no runtime cost, no model, no vector space, no supply chain, and
   no cross-build risk. Then a reranker buys the remaining 30 % at all of that cost.
   *This is the single most likely outcome and the reason Phase 0 exists.*
2. **G3 fails** — D2 `recall@5` gain < +5 absolute points. The feature does not do the
   one thing it was proposed to do.
3. **Only MRR moves, recall@5 does not** — the gold was already visible at rank 6–10 in
   a list the user sees 5 of. Cosmetic; not worth a model.
4. **Any D1 regression (G2/G6)**. Trading paraphrase wins for literal-prompt losses is a
   net loss: literal prompts are the common case.
5. **p95 added latency > 25 ms.** The hook fires on every single prompt. Perceived speed
   *is* the product.
6. **The backend is not pure-Rust cross-buildable on all five targets.** A feature that
   silently doesn't exist on Windows is a support burden and a benchmark that lies.
7. **Footprint**: model > 40 MB on disk, or any proposal to commit weights into `bin/`.
   `.git` is already 1.0 GB with five 14–21 MB binaries per release.
8. **Operational cost exceeds the gain.** A stored vector space is a second
   representation that must be invalidated and rebuilt on every model bump. This project
   has already paid that bill once: TRDD-1Z8SGQ7N's F11 re-key forced a one-time sweep of
   ~91 elements through Removed + 156 through Install on the next reindex. A model bump
   would force a full 9 475-element re-embed and a stale-vector window. If the accuracy
   delta is small, that recurring cost is not repayable.
9. **D2/D3 cannot be made CI-reproducible** (§6.6). Then the claimed benefit is
   demonstrable on one machine, by hand, and will silently rot the first time someone
   touches the scorer — the same trap that left `agent_profile_accuracy` `UNWIRED`. An
   accuracy feature no gate can defend is not worth a hot-path runtime cost.

## 9. Open questions for the approver

1. Is a user-initiated model **download** acceptable at all, or must everything ship in
   the repo? (If it must ship in-repo, kill criterion 7 fires immediately and the answer
   is: control arm only.)
2. Is Phase 0's control arm (paraphrase keywords from the existing enrichment pass) worth
   doing **on its own merits**, independent of the reranker? It is cheap and it may be the
   entire answer.
3. Is `+5.0 absolute recall@5 points on D2` the right bar? It is a judgement call and it
   should be fixed **before** any number exists.

## Approval log

- 2026-08-25T18:23:03+0200 — REFUSED under explicit USER delegation (2026-08-25). Grounds,
  all from this document's own verified analysis: (a) no measured accuracy deficit exists —
  D2/D3 do not exist and `agent_profile_accuracy` sits UNWIRED precisely because the gold
  sets are not CI-reproducible, so the claimed benefit is currently ungateable (§6.6 /
  kill-criterion 9); (b) §8.1 names the cheap control arm as the single most likely outcome,
  making the reranker's hot-path, supply-chain and cross-build costs unjustified today;
  (c) the hook's felt latency IS the product (§5.5) and this adds risk to it. Re-propose
  only WITH Phase-0 control-arm numbers: if index-time paraphrase-keyword enrichment
  measurably fails to close the paraphrase gap on a CI-reproducible fixture set, that
  evidence reopens this design. (Field migrated `approval-tier: 2` →
  `min-approval-requirement: user` per the 2026-08-25 rename; standalone project.)

## Notes and lessons learned

_(none yet)_
