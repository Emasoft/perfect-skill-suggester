---
trdd-id: YC51I1C0
title: Distribute platform binaries as GitHub release assets instead of tracking them in bin/
column: dev
created: 2026-07-23T14:29:55+0200
updated: 2026-09-28T22:29:33+0200
current-owner: perfect-skill-suggester-6a
task-type: infra
min-approval-requirement: user
scope: project
release-via: publish
labels: [distribution, ci, supply-chain, repo-size]
---

# Distribute platform binaries as GitHub release assets instead of tracking them in `bin/`

Forward-looking change only. It stops the repo from *growing* by ~154 MiB of
binaries per binary-touching release. It deliberately does **not** touch the
~1 GB already in history — see §11.

---

## 1. Problem (measured, not estimated)

`bin/` currently tracks 12 binary artifacts plus one shell script. Every
release that rebuilds them adds a fresh full copy to git history *and* to
every consumer's plugin cache.

### 1.1 What is in `bin/` today

| File | bytes | MiB | needed on |
|---|---:|---:|---|
| `pss-darwin-arm64` | 15,644,720 | 14.92 | macOS Apple Silicon |
| `pss-darwin-x86_64` | 17,278,608 | 16.48 | macOS Intel |
| `pss-linux-arm64` | 16,231,768 | 15.48 | Linux aarch64 |
| `pss-linux-x86_64` | 21,073,808 | 20.10 | Linux x86_64 |
| `pss-windows-x86_64.exe` | 18,088,448 | 17.25 | Windows |
| `pss-nlp-darwin-arm64` | 13,965,616 | 13.32 | macOS Apple Silicon |
| `pss-nlp-darwin-x86_64` | 14,193,400 | 13.54 | macOS Intel |
| `pss-nlp-linux-arm64` | 14,010,880 | 13.36 | Linux aarch64 |
| `pss-nlp-linux-x86_64` | 14,376,272 | 13.71 | Linux x86_64 |
| `pss-nlp-windows-x86_64.exe` | 14,281,216 | 13.62 | Windows |
| `pss-wasm32.wasm` | 2,258,726 | 2.15 | **nobody — orphan, see §1.4** |
| **total binaries** | **161,403,462** | **153.93** | |
| `pss-hook-dispatch.sh` | 4,691 | — | every platform (stays tracked) |

### 1.2 Every machine runs exactly 2 of the 12 files

| platform | bytes it can execute | share of shipped bytes | dead weight |
|---|---:|---:|---:|
| darwin-arm64 | 28.24 MiB | 18.3 % | **81.7 %** |
| darwin-x86_64 | 30.01 MiB | 19.5 % | 80.5 % |
| linux-arm64 | 28.84 MiB | 18.7 % | 81.3 % |
| linux-x86_64 | 33.81 MiB | 22.0 % | 78.0 % |
| windows-x86_64 | 30.87 MiB | 20.1 % | 79.9 % |

Best case, **78 % of the bytes we ship can never run on the machine that
received them.**

### 1.3 The consumer cost is multiplied, not one-off

Claude Code keeps **every installed version side by side** under
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, and each version
directory carries its own complete copy of `bin/`. Measured on the authoring
machine:

```
~/.claude/plugins/cache/emasoft-plugins/perfect-skill-suggester/
  3.9.0 3.10.0 3.10.1 3.10.2 3.10.3 3.10.4 3.10.5 3.10.6 3.10.7 3.10.8
  → 10 version dirs × ~160 MiB = 1.6 GB
  → of which 154 MiB × 10 = 1.54 GB is bin/
```

So the user does not pay 154 MiB once. They pay it **per version they have
ever installed**, and PSS releases often. A user who tracks PSS for a year
accumulates tens of GB.

Note the counterweight that makes this a *forward*-only problem: Claude Code
clones marketplaces **shallow** (verified: `git rev-parse
--is-shallow-repository` → `true` on every marketplace clone on this machine).
End users therefore never download the 1 GB of history — they download the
*working tree*, once per version. This is exactly why §11 argues the history
purge is low value and high risk.

### 1.4 `pss-wasm32.wasm` is an orphan

2.15 MiB, referenced by **zero** code. The only two hits across the whole tree
are historical CHANGELOG lines recording the removal of "phantom wasm32
references" (`CHANGELOG.md:1370`, `:1380`). The file itself was never deleted.
It is shipped to every user of every version for no reason.

### 1.5 Dev-side cost

`.git` is **1007 MiB**; 387 objects are reachable under `bin/`. Full (non
shallow) clones — CI checkouts, contributor clones, `cross` Docker
build contexts — pay this every time.

### 1.6 The assets we already build are already thrown away

`.github/workflows/build-binaries.yml` builds all 5 `pss-*` targets on every
release tag, uploads them as `actions/upload-artifact`, then a
`commit-binaries` job **commits them back into the repo**. Workflow artifacts
expire; the git blobs are forever. Meanwhile every GitHub release we publish
has **zero assets** (verified: `gh release view v3.10.10 --json assets` →
empty). We already do the expensive part (cross-compiling 5 targets in CI) and
then discard the cheap, correct delivery channel.

That `commit-binaries` job is also already known-fragile: its push step ends in
`|| echo "::warning::Push blocked by branch protection."` — i.e. it silently
degrades to "binaries are somewhere in an artifact" whenever branch protection
is on. Deleting the job removes a real failure mode.

---

## 2. Goal

From the next binary-touching release onward:

1. `git ls-files bin/` returns exactly two paths: `pss-hook-dispatch.sh` and
   `manifest.json`.
2. A user downloads **only their own platform's ~30 MiB**, once, and reuses it
   across plugin versions when the binary did not change.
3. Every downloaded byte is verified against a checksum that arrived through
   the git clone, not through the download.
4. Air-gapped and proxy-blocked environments have a documented, supported,
   non-network path.
5. The three existing platform resolvers keep working **unchanged in their
   naming contract** (§4).

Non-goal: changing anything about how binaries are *built*.

---

## 3. Design

### 3.1 Release assets + an in-repo manifest

Every release publishes, as GitHub release assets:

```
pss-darwin-arm64            pss-nlp-darwin-arm64
pss-darwin-x86_64           pss-nlp-darwin-x86_64
pss-linux-arm64             pss-nlp-linux-arm64
pss-linux-x86_64            pss-nlp-linux-x86_64
pss-windows-x86_64.exe      pss-nlp-windows-x86_64.exe
pss-binaries-<version>.tar.gz     (all ten, one file — for mirroring, §6)
manifest.json                     (same bytes as the tracked bin/manifest.json)
```

Asset names are **byte-identical to today's `bin/` filenames**. That is the
whole trick — see §4.

`bin/manifest.json` stays **git-tracked** (~1 KB):

```json
{
  "schema": 1,
  "plugin_version": "3.11.0",
  "release_tag": "v3.11.0",
  "binaries": {
    "pss-darwin-arm64":  { "sha256": "…", "size": 15644720 },
    "pss-nlp-darwin-arm64": { "sha256": "…", "size": 13965616 }
  }
}
```

### 3.2 The checksum must ship in git, never beside the download

**This is the load-bearing security decision.** Publishing `binary` and
`binary.sha256` as two assets on the same server verifies *transport
corruption only* — an attacker who can replace the asset replaces both. The
checksum has to arrive through a channel the user already trusted.

The user already trusted the plugin clone (they installed it; Claude Code
fetched it over TLS from GitHub; it is what supplies the hook scripts that run
on their machine). Putting the SHA256 in a **git-tracked** `bin/manifest.json`
means a tampered release asset **fails verification against the repo**, and a
tampered repo is a compromise the user already lost to. That is a real trust
improvement over the status quo, where a committed binary blob is trusted
purely because it is in the tree.

Corollary rules:
- The manifest is **generated by the build step from the actual built files**,
  never hand-written. `publish.py` recomputes and diffs it as a gate (§7, G3).
- A binary whose sha is absent from the manifest is **never** installed.
- Verification is fail-closed: verify into a `.part` file, `os.replace` only
  after the sha matches, never leave a partial file in the store.

### 3.3 Content-addressed store, so versions share binaries

Fetched binaries land in a store keyed by content, not by version:

```
<data-dir>/bin/<sha256[:16]>/<name>       # the artifact
<data-dir>/bin/current/<name>  → symlink  # what resolvers stat
<data-dir>/bin/.fetch.lock                # fcntl.LOCK_EX, writers only
```

`<data-dir>` is `pss_paths.get_data_dir()` — i.e. `$CLAUDE_PLUGIN_DATA` on
Claude Code ≥ 2.1.78, else `~/.claude/cache/`. This is the existing project
convention; no new path concept is introduced.

Why content-addressed: PSS bumps its version far more often than it rebuilds
the Rust engine (`publish.py` already skips the build when no `.rs` changed —
`_submodule_src_changed()`). With a version-keyed store, every patch release
would re-download 30 MiB for identical bytes. With a content-addressed store,
**an unchanged binary across versions is a zero-byte upgrade**: the new
manifest names the same sha, the store already has it, the fetcher only
re-points `current/`.

Writer discipline mirrors the v3.5.0 CozoDB design already documented in
`CLAUDE.md` — exclusive lock on a *separate* lock file so readers are never
blocked, download to a staging path, atomic `os.replace`. Same reasoning, same
shape, so there is one concurrency idiom in the project, not two.

### 3.4 When the fetch runs — and where it must never run

| surface | may fetch? | why |
|---|---|---|
| `UserPromptSubmit` → `bin/pss-hook-dispatch.sh` | **NEVER** | hot path, ~3 ms budget; a network call here is an instant regression. It may only `stat` the store. |
| `SessionStart` → `pss_hook.py --warm-index` | yes, **detached** | already backgrounded (`&`) with a 5 s timeout; 30 MiB will not finish in 5 s, so the hook *spawns and returns*, and the fetcher writes its own state file. |
| `/pss-status`, `/pss-reindex-skills`, `pss_paths.resolve_pss_binary()` | yes, **synchronous + fail-fast** | user-initiated, a visible wait and a loud error are correct here. |

The SessionStart hook emits one line of `additionalContext` when a fetch is in
flight (`PSS: downloading engine (~30 MB), suggestions resume next session`)
so the first-run silence is **explained rather than mysterious**.

### 3.5 Explicit failure modes — no silent degradation

Today a missing binary is a state that never occurs, so nobody notices that
`pss-hook-dispatch.sh` handles it by printing empty JSON and exiting 0,
forever, with no signal. After this change that state becomes reachable, so it
needs a voice. Two different surfaces, two different contracts:

- **Hot path stays graceful *and* gains a breadcrumb.** The shim keeps
  `[ -x ]` → empty hook JSON → `exit 0` (never break a user's session), but the
  fetcher writes `<data-dir>/bin/.state.json` with `{status, reason, hint,
  attempted_at}`, and `/pss-status` renders it.
- **Everything user-initiated is fail-fast, with the remedy in the message.**

```
PSS: cannot obtain the native engine for darwin-arm64.

  tried:  https://github.com/Emasoft/perfect-skill-suggester/releases/download/v3.11.0/pss-darwin-arm64
  result: connection refused after 3 attempts (proxy/firewall?)

  offline install:
    1) on a networked machine:
         gh release download v3.11.0 -R Emasoft/perfect-skill-suggester \
            -p 'pss-binaries-3.11.0.tar.gz'
    2) copy it over, then:
         uv run python scripts/pss_fetch_binaries.py --offline pss-binaries-3.11.0.tar.gz
  or point PSS at a directory you populate yourself:
         export PSS_BINARY_DIR=/opt/pss/bin
  or build from the vendored source (needs a Rust toolchain):
         uv run python scripts/pss_fetch_binaries.py --build-from-source
```

Corporate-network reality: a blocked download must **exit non-zero, print the
above, and leave nothing behind**. It must not retry forever, must not fall
back to an unverified mirror, and must not pretend success. FAIL-FAST.

---

## 4. The resolver contract is preserved, by construction

Three independent implementations resolve the same platform → filename map,
and all three must keep working:

| resolver | file | on miss |
|---|---|---|
| POSIX sh (hot path) | `bin/pss-hook-dispatch.sh` | empty hook JSON, `exit 0` |
| Python | `scripts/pss_paths.py::detect_platform()` / `resolve_pss_binary()` | `FileNotFoundError` |
| Rust (nlp lookup) | `rust/skill-suggester/src/main.rs::find_pss_nlp_binary()` | `None` → negation detection skipped |

**The contract is the name string** — `pss-<os>-<arch>[.exe]`,
`pss-nlp-<os>-<arch>[.exe]`. It appears in the sh `case`, in
`detect_platform()`, in the Rust probe list, in the CI matrix, and (today) as
the filename in `bin/`. This TRDD changes **none** of it: the *release asset
name is the same string*. One name, five consumers, unchanged.

The only change is an **additional search root**, inserted at a defined
precedence in all three resolvers:

```
1. $PSS_BINARY_DIR/<name>              # operator escape hatch (§6, tier 1)
2. <data-dir>/bin/current/<name>       # the fetched store
3. $CLAUDE_PLUGIN_ROOT/bin/<name>      # transitional; today's location
4. <repo>/bin/<name>                   # local dev / tests
5. (rust only) PATH via `which`        # unchanged
```

Ordering rationale: an operator override beats everything; the store beats the
in-repo copy so that after Phase 3 there *is* no step 3 to reach; step 3
survives one release as the rollback path (§8).

A `tests/unit/test_pss_binary_path_parity.py` asserts the three
implementations agree on both the name map and the search order — the same
pattern already used by `test_pss_scope_path_parity.py` and
`test_pss_db_path_parity.py`.

---

## 5. Why NOT git-lfs

Evaluated and **rejected**. Five reasons, any one of which is sufficient:

1. **It does not reduce what the user downloads.** LFS replaces blobs in
   *history* with pointers, but `git clone` still smudges every LFS file
   present in the checked-out tree. The user still receives all 12 platform
   binaries — all 154 MiB — because LFS is per-file-in-tree, not per-platform.
   It therefore does **nothing** about §1.3, which is the actual cost.
2. **It requires `git-lfs` on the consumer, and fails dangerously without it.**
   Claude Code performs the clone; we do not control the environment. Without
   the LFS filter the checkout produces ~130-byte *pointer text files* at the
   binary paths. `pss-hook-dispatch.sh`'s `[ -x "$BIN_DIR/$BIN_NAME" ]` test
   **passes** on a text file, so the hook `exec`s a text file on every prompt.
   That is a strictly worse failure than a clean "not found".
3. **GitHub LFS bandwidth is metered and billed.** The free allowance is 1 GB /
   month. At ~154 MiB per fresh install that is exhausted after ~6 installs per
   month, after which **clones fail for everyone** until quota is purchased.
   Release-asset bandwidth on public repos is unmetered. For a public plugin
   this alone is disqualifying.
4. **Adopting LFS for the existing blobs is itself a history rewrite.**
   `git lfs migrate import` rewrites every commit that touched `bin/` — exactly
   the destructive, irreversible operation this TRDD refuses to perform (§11).
   Applying LFS only to *future* blobs leaves the 1 GB where it is, so it buys
   nothing the proposed design does not already buy.
5. It adds a second tool and a server-side dependency to the release path in
   exchange for zero user-visible benefit.

LFS solves "a team that all has git-lfs wants big files out of their clones'
history". Our problem is "ship one 30 MiB platform slice to an end user who
did not run `git` themselves". Release assets solve that; LFS does not.

### Other alternatives considered

| option | why rejected |
|---|---|
| Five per-platform plugin variants | 5 marketplace entries; the user must know their arch; `plugin.json` × 5 to keep in sync. |
| `cargo install` / build on the user's machine | Requires a Rust toolchain on every consumer; 2–4 min cold compile; the hot path cannot wait. Kept only as offline tier 3 (§6). |
| Track only the two most popular platforms | Arbitrary; breaks linux-arm64 and Windows users outright; still ~60 MiB. |
| Compress the binaries in-tree (`.gz`/`upx`) | ~2× at best, still per-version × 12; adds a decompress step to the hot path. Treats the symptom. |

---

## 6. Offline / air-gapped support — three supported tiers

1. **`PSS_BINARY_DIR`** — an env var naming a directory the operator populates
   through their own artifact channel. Checked *first* by all three resolvers.
   No network, no manifest requirement, full operator control. This is the
   air-gap answer.
2. **`scripts/pss_fetch_binaries.py --offline <tarball-or-dir>`** — installs
   from the mirrored `pss-binaries-<version>.tar.gz` (or a directory) into the
   content-addressed store, running **the same SHA256 verification against the
   same tracked manifest**. One file to move across an air gap, integrity still
   enforced.
3. **`--build-from-source`** — the `rust/` submodule is already in the clone;
   `cargo build --release` produces the native binary. Requires a Rust
   toolchain, documented as the last resort.

The single-tarball asset exists precisely so a corporate admin mirrors **one**
file internally rather than ten.

---

## 7. Migration path — 4 phases, each independently revertible

**Phase 0 — remove the orphan.** Delete `bin/pss-wasm32.wasm` (§1.4): 2.15 MiB,
zero references. In-repo deletion of a committed, recoverable file; no history
operation. Can land independently of everything below.

**Phase 1 — publish assets. Nothing else changes.**
- `build-binaries.yml`: add an asset-upload step; keep the `commit-binaries`
  job for now.
- `publish.py::create_github_release()`: add `bin/*` + `manifest.json` +
  tarball to the `gh release create` invocation (single insertion point,
  already located).
- Generate `bin/manifest.json` from the built files.
- User-visible change: **none**. Proves the asset path end-to-end.

**Phase 2 — ship the fetcher; the in-repo copy still wins.**
- Add `scripts/pss_fetch_binaries.py` and the extra search root in all three
  resolvers, with the in-repo `bin/` still **ahead** of the store.
- Add the SessionStart spawn + `.state.json` + `/pss-status` rendering.
- **Differential gate (G3):** CI fetches from the release and asserts the
  downloaded sha equals the sha of the tracked `bin/` file. A mismatch is a
  hard failure. The fetcher is fully exercised while nothing yet depends on it.

**Phase 3 — flip.**
- `git rm --cached bin/pss-* bin/pss-nlp-*` (files remain on developer disks —
  nothing is deleted).
- `.gitignore`: `bin/pss-*` with `!bin/pss-hook-dispatch.sh` re-included.
- Keep tracked: `bin/pss-hook-dispatch.sh`, `bin/manifest.json`.
- Reorder the resolvers so the store precedes `$CLAUDE_PLUGIN_ROOT/bin`.
- `build-binaries.yml`: delete the `commit-binaries` job (its push step, which
  today degrades to a `::warning::` under branch protection, disappears with
  it).
- From this release forward, each new version costs the user ~30 MiB once, and
  **0 bytes** when the engine did not change.

**Phase 4 — soak one release, then delete the transitional
`$CLAUDE_PLUGIN_ROOT/bin/<name>` branch** from the three resolvers.

### Rollback

Phase 3 is one revert: re-add `bin/` to the index from the working tree (the
files are still there), restore the resolver order, restore the CI job. Phases
0–2 are additive. Nothing in this TRDD is irreversible.

---

## 8. Acceptance criteria

| # | check | how |
|---|---|---|
| P1 | release carries 10 binaries + `manifest.json` + tarball | `gh release view vX.Y.Z --json assets --jq '.assets[].name'` — expect 12 names |
| P2 | every asset's sha256 == the tracked manifest value | fetch all, `shasum -a 256`, diff against `bin/manifest.json` |
| P3 | cold install works | empty store → fetch → `pss --version` succeeds; store holds exactly 2 files |
| P4 | **tamper is refused** | flip one byte mid-download; assert non-zero exit **and** an empty store (fail-closed, no partial) |
| P5 | **blocked network is loud, and the session survives** | run behind a blackhole proxy: fetcher exits non-zero with the §3.5 message and leaves no file; `pss-hook-dispatch.sh` still emits valid empty JSON and exits 0 |
| P6 | offline install works | `--offline pss-binaries-X.Y.Z.tar.gz` with the network down |
| P7 | concurrency is safe | 5 parallel fetchers → exactly one download, 5 successes, no corrupt file |
| P8 | `bin/` is clean | `git ls-files bin/` → exactly `pss-hook-dispatch.sh`, `manifest.json` |
| P9 | clone shrinks | fresh shallow clone of the plugin drops from ~160 MiB to <10 MiB |
| P10 | resolver parity | `tests/unit/test_pss_binary_path_parity.py` — sh / Python / Rust agree on the name map **and** the search order |
| P11 | unchanged engine costs nothing | bump the version without touching `.rs`; assert the fetcher downloads 0 bytes and only re-points `current/` |

No mocks of the thing under test: P2–P7 exercise the real fetcher against a
real release (P5/P7 may use a local blackhole proxy and a real temp store —
the network is the environment, not the unit under test).

---

## 9. Risks

| # | risk | mitigation |
|---|---|---|
| R1 | a network call sneaks into the hot path | architectural rule (§3.4): the shim may only `stat`. P10 pins the search order; a `curl`/`wget` in `pss-hook-dispatch.sh` is a review-blocking defect. |
| R2 | first session after install has no suggestions | one-time, bounded (~30 MiB), and *announced* via SessionStart `additionalContext` + `.state.json`. |
| R3 | GitHub outage blocks new installs | affects new installs only (the store persists); three offline tiers (§6); bounded retry with backoff. |
| R4 | `$CLAUDE_PLUGIN_DATA` absent on older Claude Code | `get_data_dir()` already falls back to `~/.claude/cache/`; no new behavior. |
| R5 | manifest drifts from the shipped binaries | manifest is generated from the built files and re-verified by a `publish.py` gate; never hand-edited. |
| R6 | a stale `current/` symlink after a failed upgrade | `current/` is re-pointed only after all required shas verify; otherwise the previous target stays valid. |
| R7 | dev workflow confusion ("where did bin/ go?") | `bin/` still exists locally and still works (search root #4); `DEVELOPMENT.md` + `/pss-status` explain the store. |

---

## 10. Files this touches (implementation scope, for the eventual dev phase)

- `.github/workflows/build-binaries.yml` — add upload; later delete `commit-binaries`
- `scripts/publish.py` — attach assets in `create_github_release()`; add the manifest gate
- `scripts/pss_fetch_binaries.py` — **new**
- `scripts/pss_paths.py` — extra search root
- `bin/pss-hook-dispatch.sh` — extra search root (stat only)
- `rust/skill-suggester/src/main.rs::find_pss_nlp_binary()` — extra search root
- `hooks/hooks.json` — SessionStart spawns the fetcher
- `commands/pss-status/binary-status.md` — render `.state.json`
- `bin/manifest.json` — **new, tracked**
- `.gitignore` — Phase 3
- `tests/unit/test_pss_binary_path_parity.py` — **new**
- `docs/DEVELOPMENT.md`, `docs/PSS-ARCHITECTURE.md` — document the store

---

## 11. OUT OF SCOPE — history purge is a separate, USER-GATED task

The ~1 GB already in `.git` (387 objects under `bin/`) is **not** addressed
here and **must not** be folded into this work.

Removing it requires `git filter-repo` / BFG followed by `git push --force` to
a **public** repository that has existing clones, forks, and ~40 release tags.
Every commit SHA after the first rewritten commit changes, which:

- invalidates every existing clone and fork,
- breaks every `implementation-commits:` SHA recorded in the TRDD corpus (the
  project's own backtracking mechanism),
- breaks the `rust/` submodule gitlink SHAs recorded in the parent tree,
- breaks release-tag → commit associations on GitHub,
- is **irreversible** once the old objects are garbage-collected upstream.

It is also **low value**, precisely because of §1.3: Claude Code clones
marketplaces **shallow**, so end users never download that history. The people
who pay for it are developers doing full clones — a small, known set who can
`--depth 1`.

Therefore:

- This TRDD stops the bleeding. After Phase 3 the 1 GB is a **fixed, bounded,
  historical** cost that no longer grows.
- Any purge must be its own TRDD, authored separately, at **Tier 3 (USER)**.
- The exact command must be presented verbatim, with its blast radius
  enumerated, and the **user must approve that exact command in writing before
  it is run**. No agent may run it on its own judgment.
- Recommendation on the merits: **do not purge.** The forward-looking change
  captures essentially all the value at zero risk; the purge captures little at
  high, irreversible risk.

---

## Phase status

**Phase 0 — DONE** (verified 2026-08-30, first-hand): `bin/pss-wasm32.wasm` is neither tracked
(`git ls-files bin/` lists 11 entries, no `.wasm`) nor present on disk. The only remaining `wasm`
hits in the tree are language-taxonomy strings in `main.rs`, unrelated to the artifact.

**Phase 1 — IMPLEMENTED 2026-08-30**, ships in the next release:
- `scripts/publish.py` gains `RELEASE_BINARIES` (the ten names), `write_binary_manifest()`,
  `_binaries_tarball()` and `upload_release_assets()`.
- The manifest is generated from the ACTUAL built files at step 10c — after both build steps and
  before the commit, so it is staged by the existing `git add bin/` and ships in the same commit
  as the binaries it describes.
- Assets upload AFTER `create_github_release()` rather than inside it. That function returns
  early when the release already exists (the `--push-only` recovery path), so uploading from
  inside would let a recovery run repair the release and leave it asset-less — the same
  half-published state `--push-only` exists to repair, one layer down. `--clobber` keeps retries
  idempotent.
- 5 unit tests (`tests/unit/test_publish_release_assets.py`) assert the manifest describes the
  REAL bytes, that a missing binary is fatal with no partial manifest left behind, that the
  tarball holds exactly ten flat members, and that `RELEASE_BINARIES` matches what `bin/`
  actually ships.
- `bin/manifest.json` generated and spot-verified against the live binaries.

**DEVIATION from the phase-1 plan, deliberate.** The plan says *"build-binaries.yml: add an
asset-upload step"*. Not done, and it should not be: `publish.py` already uploads on the
authoritative release path, so a second uploader would give the same asset NAMES two writers
whose bytes need not agree — CI compiles with its own toolchain — while `bin/manifest.json` is
generated by only ONE of them. A CI upload landing after (or racing) the local one would publish
assets that fail verification against the tracked manifest, breaking §3.2's whole trust argument
and pre-failing the phase-2 differential gate G3. The asset path is proven end-to-end by the
local publisher, which is what the phase is for. If CI is ever to become the builder, that is a
separate decision about WHO builds a release, not an extra upload step.

**Correction to the reasoning above, and it strengthens the conclusion.** The first version of
this paragraph justified the deviation with "the manifest records exactly one build". That
premise is FALSE: `commit-binaries` (§1.6) already downloads CI-built artifacts, copies them into
`bin/`, and pushes them back, so **`bin/` has two writers today** — and only the local publisher
generates the manifest. So the hazard is not hypothetical-second-writer, it is existing-second-
writer-that-does-not-maintain-the-manifest. Two consequences for phase 2, neither of which
blocks phase 1 (nothing consumes the manifest yet):

- **P-2a — the manifest can go stale between releases.** A successful `commit-binaries` push
  replaces binaries in `bin/` without regenerating `bin/manifest.json`. Before anything verifies
  against the manifest, either that job regenerates the manifest too, or it goes away (phase 3
  deletes it anyway).

  **MEASURED 2026-08-30, and the reason is not the one the job reports.** `git log origin/main
  --grep='build: update pre-built binaries'` → **0 commits, ever**; every commit on `main` is
  authored by the owner. The job's own log for the latest run (33279963666) shows why:

  ```
  [detached HEAD 334a4e8] build: update pre-built binaries for all platforms
  fatal: You are not currently on a branch.
  ##[warning]Push blocked by branch protection. Binaries are available as workflow artifacts.
  ```

  `actions/checkout` on a TAG produces a detached HEAD, so `git push` cannot infer a target ref
  and fails before any server-side rule is consulted. **The `::warning::` text is wrong** — it
  blames branch protection for a local git error, which is precisely what led the first version
  of this section to record branch protection as the mitigation. A misattributing error message
  is worse than none: it answers the question so the reader stops asking it.

  So the CI-writer risk is real but currently inert for a structural reason, on the tag-triggered
  runs that matter for releases. Do not treat "the push fails" as a guarantee held by rulesets —
  it is held by a checkout mode, and fixing the job's push (an easy, plausible "cleanup") would
  ACTIVATE the staleness hazard. Phase 3 deletes the job; until then, leave it broken and say why.
- **P-2b — the phase-3 CI break in this phase's own test.**
  `test_release_binaries_matches_what_the_repo_actually_ships` globs the `bin/` DIRECTORY, not
  `git ls-files`. Phase 3 leaves the files on developer disks, so it will keep passing locally
  and fail in CI, where a fresh clone has none. Fix when phase 3 lands: skip the test when `bin/`
  contains no `pss-*` files. Recorded now, while the reason is known, rather than met as a red
  build later.

**Phase 1 verified against the real release v3.16.0** (not against the pipeline's own report):

- **P1 — PASS.** `gh release view v3.16.0 --json assets` lists exactly 12 names: the ten
  binaries, `manifest.json`, and `pss-binaries-3.16.0.tar.gz`.
- **P2 — PASS, including the tarball.** All ten binary assets downloaded and sha256'd: every one
  matches, sizes included. The published `manifest.json` asset is byte-identical to the tracked
  file, and — the check that stops this being circular — the tracked file is byte-identical to
  the blob at tag `v3.16.0` (`git ls-tree v3.16.0 bin/manifest.json` == `git hash-object
  bin/manifest.json` == `472b8cf2…`). So the manifest a USER receives is the one these assets
  were verified against, not merely a working-tree copy that round-tripped through GitHub.
- **The tarball is verified too**, which P2 as originally worded did not require. It was the only
  published asset nothing had ever checked, and it is the SOLE delivery path for §6's air-gapped
  tier — so leaving it unchecked would have meant the tier whose users have no fallback was the
  one tier with no evidence. Downloaded `pss-binaries-3.16.0.tar.gz`, extracted: 10 members, none
  missing, every member's sha256 matches the manifest. **P2's wording should read "every asset,
  including the tarball's members".**

**Correction to §7's phase-1 line "User-visible change: none."** Not quite: `bin/manifest.json`
is a NEW tracked file, so from v3.16.0 every user's plugin cache gains ~1 KB. No behaviour
changes, and shipping that file through git is the entire point of §3.2 — but "none" was wrong.

**Phase 2 — IN PROGRESS.** `scripts/pss_fetch_binaries.py` is written and exercised end-to-end
against the real v3.16.0 tarball. Still to do: the extra search root in all three resolvers (with
`bin/` still AHEAD of the store, per §7), the SessionStart spawn + `additionalContext` line,
`/pss-status` rendering of `.state.json`, `test_pss_binary_path_parity.py`, and the G3 CI gate.

Fetcher, as built:
- downloads only the TWO binaries this machine can execute (§1.2 measures the full set at 78-82%
  dead weight), verified against the git-tracked manifest;
- content-addressed store `<data-dir>/bin/<sha256[:16]>/<name>` + `current/<name>`, so an
  unchanged engine costs a new version 0 bytes and no network;
- verify-into-`.part`-then-`os.replace`, so a file present in the store has already matched its
  sha and a crash mid-download cannot leave something that looks installed;
- `LOCK_EX` on `.fetch.lock` — a NEW file readers never touch, so a fetch can never block the
  hot path;
- symlink for `current/`, falling back to copy where symlinks need privileges (unprivileged
  Windows), since a plugin that only works for administrators is not shipped;
- bounded retries (3) then a loud failure carrying the offline remedy inline — a proxy that
  refuses the connection refuses it on the twentieth try too, and an unbounded retry turns a
  clear failure into an undiagnosable hang.

**P3 / P6 verified for real** (no mocks, real published artifact): a cold store populated from
`pss-binaries-3.16.0.tar.gz` via `--offline` yields exactly the two artifacts plus their
`current/` entries, both executable, and the fetched binary runs.

**FINDING for phase 3 — `--version` from the store needs `CLAUDE_PLUGIN_ROOT`.** The fetched
binary reported `pss 3.15.0` when run straight out of the store, and `pss 3.16.0` with
`CLAUDE_PLUGIN_ROOT` set. Nothing is wrong with the fetch: the two releases ship a
byte-identical binary (`git ls-tree` gives the same blob `07a67a3f…` at both tags, because the
build correctly skipped on no `.rs` change), and the Rust binary resolves `VERSION` via
`CLAUDE_PLUGIN_ROOT` or relative to its own path — from the store there is no `VERSION` beside
it, so it falls back to the version compiled in at BUILD time. Today `bin/` is inside the plugin
root so the fallback never fires. After phase 3 it always will for any invocation that does not
set the env var. Claude Code's hooks do set it; a human running the binary does not. Decide
before the flip whether `/pss-status` and any version-gated logic may rely on `--version`.

**A phase-1 test caught a real defect in this session's own code:** the dry-run branch logged
`BIN_MANIFEST.relative_to(ROOT)`, which raises `ValueError` for any path outside the repo root —
a cosmetic log line that would have aborted the run. Fixed to print the path as-is.
**ADVISOR VERDICT 2026-09-28 (Fable, on 3 open phase-2 decisions) — ADOPTED:**
D1 SessionStart → separate hook entry WITHOUT the trailing ampersand running `pss_fetch_binaries.py --session-start`: two stats + maybe a Popen do not belong coupled to `_warm_index()`, whose DB read is slow/lockable and deliberately backgrounded; §3.4 already says spawns-and-returns. Contract: exit 0 always, print hook JSON only while a fetch is in flight, reuse `.fetch.lock`.
D2 parity test → drive the REAL Rust binary via a new pure-path `binary-path` subcommand (intercepted like db-path). Marginal cost ~30 lines — the rebuild is sunk anyway because phase 2 edits `find_pss_nlp_binary()`. A source-text assertion cannot catch the resolver existing macOS cfg divergence (probes arm64 then x86_64 unconditionally).
D3 store path → do NOT mirror `get_data_dir()` CLAUDE_PLUGIN_DATA conditional into sh and Rust (a 4th/5th copy of a rule with a documented 1641-element drift incident). Pin instead, same precedent as the db-path canonicalization: the fetcher writes to `~/.claude/cache/pss-bin/` UNCONDITIONALLY (`store_dir()` = `get_claude_config_dir()/cache/pss-bin`); sh and Rust add the CONSTANT path. DEVIATION from §3.3 (store under get_data_dir): deliberate, rationale above; renamed bin→pss-bin because bare bin/ in the shared cache dir is collision-prone. Phase-2 search order stays PSS_BINARY_DIR → plugin-root bin → repo bin → store (§7 in-repo-wins); §4 final order flips at phase 3.
REVIEW FORK 2026-09-28 (resolver edits) — 2 real defects found and fixed in the same session: (1) sh shim: on an unsupported platform BIN_NAME is empty and the early PSS_BINARY_DIR exec tested "-x dir/" (true for any searchable dir), exec of a directory = exit 126 = session broken; fixed with a "[ -n BIN_NAME ]" guard, settled with the env -i miss-path test. (2) binary-status.md rendered .state.json under the get_data_dir rule the D3 pin replaced — with CLAUDE_PLUGIN_DATA set (normal hook env) /pss-status would cat a path nothing writes; fixed to the constant. Finding 3 (cross-target compile of pss_platform_binary_name unproven on darwin) is accepted: the CI cross build is the first real proof.
**PHASE 2 COMPLETE 2026-09-28** (commits d42075b + bd36456 + rust da0bfff). All five remaining items landed and verified: (a) store root in all three resolvers, in-repo bin/ still ahead, store = CONSTANT ~/.claude/cache/pss-bin; (b) SessionStart --session-start hook: silent when binaries resolve, spawns detached, one additionalContext line only while in flight (CC 2.1.277 cache-miss lesson honored); (c) /pss-status renders the store + .state.json; (d) test_pss_binary_path_parity.py green — real sh/Python/Rust subprocesses, name map + order + plugin-root quoting invariant; (e) G3 gate verify-release-assets.yml (push runs exit 0 pre-publish; schedule/dispatch hard-fail). Full unit suite 496 passed. Phase 3 (the flip) is NOT started.
REVIEW ROUND 2 (phase-2 commits) — finding 1 CONFIRMED and FIXED (4f8f74a): _binaries_resolve stat'ed the script's own parent bin/, which in any copied layout resolves to the developer's repo — fresh installs concluded nothing-to-fetch and the spawn path never fired. Settled with the fork's sandbox command: notice prints, current/ populates. Finding 2 ACCEPTED AS STATED: the rebuilt bin/pss-darwin-arm64 intentionally leads the published v3.16.0 assets until the next release; the nightly G3 red is TRUTHFUL (tracked binary is genuinely not the released one) — do NOT revert the binary to green it; the next --bump regenerates the manifest. Findings 3-8: CLEAR (exe-dir root is sandboxed by the parity test's tmp copy; read-only-HOME silence accepted, no channel exists; matcher set and bulk replace verified).
**PHASE 3 EXECUTED 2026-09-28** (this commit). git rm --cached the ten binaries (files stay on dev disks); .gitignore bin/pss-* with the shim re-included (manifest+shim remain tracked — P8: git ls-files bin/ = 2); all three resolvers flipped so the STORE now wins (PSS_BINARY_DIR → store → plugin bin → repo bin; plugin-bin branch is transitional, deleted in phase 4); commit-binaries job DELETED from build-binaries.yml (its push fix would have activated hazard P-2a — the checkout-mode guarantee dies with the job); P-2b skip guard added to the bin-globbing test; /pss-status + DEVELOPMENT.md document the new order. Settled: store stub beats the repo binary in sh AND Python end-to-end; full suite 499 passed. Phase 4 (delete the transitional branch after a soak release) NOT started.
REVIEW ROUND 3 (phase-3 commit 85f40af) — finding 2 FIXED (9ce01a6): /pss-status was blind during the download window (write_state only fired at completion); session_start() now records status 'fetching' at spawn, pinned by the spawn test. Finding 1 (upgrade-window suggestions blackout) CONFIRMED as ratified §9-R2 design — announced via the SessionStart notice, accepted. Findings 4-5 (store version skew, shared store across plugin versions) inherent to content-addressing, accepted. Finding 6 edge 2 noted: tag-blob binary verification habits are retired by this flip — provenance now lives in release-assets+manifest+G3. Heartbeat-triage review: cosign card scope-corrected in the approval log (end-to-end signing story, key custody first).

## 12. Approval

Tier 2 (MANAGER). Objective floor: this changes `.github/` workflows and enters
the release pipeline (`release-via: publish`).

## Approval log

- 2026-08-25T18:23:03+0200 — APPROVED (proposal → planned) under explicit USER delegation
  ("complete all pending tasks and TRDDs… You can decide yourself without me", 2026-08-25;
  standalone project, USER is the approver). Grounds: every §1 cost figure is measured, the
  design is phased and per-phase revertible, and §11's history purge stays USER-gated OUT of
  scope. Execution starts with Phase 0 (delete the zero-referenced `bin/pss-wasm32.wasm` —
  re-verified 2026-08-25: git-tracked, zero code references); Phases 1–3 follow, Phase 3 only
  after a Phase-1/2 release proves the asset path (per §7's own sequencing).
  (Field migrated `approval-tier: 2` → `min-approval-requirement:` per the 2026-08-25 rename;
  set to `user` — standalone project, no manager.)

- 2026-08-29T15:08:09+0200 — **Phase 0 CONFIRMED DONE (no action needed).** Verified
  first-hand: `git ls-files bin/` returns 11 paths and `bin/pss-wasm32.wasm` is not among
  them, so the orphan named in §1.4 is already untracked. A repo-wide search for `wasm`
  across `.py/.rs/.sh/.json/.yml/.md` (excluding `design/` and `reports/`) finds only
  CHANGELOG history and unrelated `wasm-bindgen` rows in `rust/negation-detector/Cargo.lock`
  — zero live references. §1.1's table (12 artifacts, 153.93 MiB) is therefore STALE by one
  file: the tracked set is now 10 binaries + `pss-hook-dispatch.sh`, ~151.78 MiB. Every other
  §1 figure stands.

  **Phases 1-3 remain OPEN and are NOT being executed in this session** — a deliberate scope
  call under the "drain the board" order, recorded so the stop is visible rather than silent:
  acceptance criteria P2-P7 cannot be evaluated at all until a release that actually carries
  the assets exists (P3 cold-install, P4 tamper-refusal, P5 blackhole-proxy, P6 offline
  tarball, P7 concurrency all fetch from a real published release). The card's own §7 phasing
  agrees — "Phase 3 only after a Phase-1/2 release proves the asset path". So this is
  inherently a multi-release migration, not a single-session task, and claiming it complete
  here would be false. It stays `column: planned` with Phase 0 closed and Phase 1 as the next
  action: add asset upload to `.github/workflows/build-binaries.yml` + `bin/manifest.json`.
