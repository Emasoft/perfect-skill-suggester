# PSS Plugin Development Guide

This document provides instructions for building, testing, and developing the Perfect Skill Suggester (PSS) plugin.

**Claude Code compatibility**: see [`CC-COMPATIBILITY.md`](CC-COMPATIBILITY.md) for the
version-by-version matrix of supported Claude Code releases, declared hook events, hook
input/output schema notes, and migration guidance when new CC versions land.

---

## Prerequisites

### Required Tools

1. **Rust Toolchain**
   ```bash
   # Install rustup (Rust toolchain installer)
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

   # Verify installation
   rustc --version
   cargo --version
   ```

2. **Cross-Compilation Targets**

   To build binaries for all supported platforms, install the following targets:

   ```bash
   # macOS targets
   rustup target add aarch64-apple-darwin    # macOS ARM (M1/M2/M3)
   rustup target add x86_64-apple-darwin     # macOS Intel

   # Linux targets
   rustup target add x86_64-unknown-linux-musl    # Linux x64
   rustup target add aarch64-unknown-linux-musl   # Linux ARM

   # Windows target
   rustup target add x86_64-pc-windows-gnu       # Windows x64
   ```

3. **Additional Dependencies (for cross-compilation)**

   ```bash
   cargo install cross    # Docker-based cross-compilation (preferred for Linux/Windows)
   cargo install cargo-zigbuild  # Fallback cross-compiler using Zig
   brew install zig        # Required for cargo-zigbuild
   ```

   **CRITICAL: Homebrew Rust Conflict** — If `brew install rust` is installed alongside `rustup`, it shadows rustup's cargo/rustc in PATH. Symptoms: `can't find crate for std` on cross-compilation. Fix: `brew uninstall rust`.

   On macOS, you may also need:
   ```bash
   brew install mingw-w64  # For Windows cross-compilation
   ```

   On Linux, you may need:
   ```bash
   sudo apt-get install gcc-mingw-w64-x86-64  # For Windows cross-compilation
   sudo apt-get install gcc-aarch64-linux-gnu # For ARM cross-compilation
   ```

---

## Building from Source

### Basic Build (Current Platform)

```bash
cd rust/skill-suggester

# Debug build (faster compilation, slower execution)
cargo build

# Release build (optimized for performance)
cargo build --release
```

The binary will be located at:
- Debug: `target/debug/pss`
- Release: `target/release/pss`

---

## Cross-Compilation for All Platforms

### Preferred Method: Build Script

The build script handles platform detection, toolchain selection, and binary placement:

```bash
uv run scripts/pss_build.py --all          # All 5 targets
uv run scripts/pss_build.py                # Native only (darwin-arm64)
uv run scripts/pss_build.py --target linux-x86_64  # Specific target
```

### Manual Build for Specific Target

```bash
cd rust/skill-suggester

# macOS ARM (M1/M2/M3)
cargo build --release --target aarch64-apple-darwin

# macOS Intel
cargo build --release --target x86_64-apple-darwin

# Linux x64 (requires cross + Docker — uses musl for static binaries)
DOCKER_DEFAULT_PLATFORM=linux/amd64 cross build --release --target x86_64-unknown-linux-musl

# Linux ARM (requires cross + Docker)
DOCKER_DEFAULT_PLATFORM=linux/amd64 cross build --release --target aarch64-unknown-linux-musl

# Windows x64 (REQUIRES cross + Docker — zigbuild fails without mingw dlltool)
DOCKER_DEFAULT_PLATFORM=linux/amd64 cross build --release --target x86_64-pc-windows-gnu
```

> **Apple Silicon note:** the `DOCKER_DEFAULT_PLATFORM=linux/amd64` env var is
> REQUIRED on Apple Silicon hosts. Cross's Docker images are x86_64-only and
> Docker will reject them with "no matching manifest for linux/arm64/v8"
> without this override. `scripts/pss_build.py` sets it automatically.

### Build All Platforms at Once

```bash
cd rust/skill-suggester

# Build script for all platforms
for target in \
  aarch64-apple-darwin \
  x86_64-apple-darwin \
  x86_64-unknown-linux-musl \
  aarch64-unknown-linux-musl \
  x86_64-pc-windows-gnu
do
  echo "Building for $target..."
  cargo build --release --target $target
done
```

---

## Binary Naming Convention

PSS binaries follow this naming pattern: `pss-{os}-{arch}[.exe]`

### Naming Examples

| Platform | Binary Name |
|----------|-------------|
| macOS ARM | `pss-darwin-arm64` |
| macOS Intel | `pss-darwin-x86_64` |
| Linux x64 | `pss-linux-x86_64` |
| Linux ARM | `pss-linux-arm64` |
| Windows x64 | `pss-windows-x86_64.exe` |

### Installing Binaries to Plugin

After building, copy binaries to the plugin's `bin/` directory:

```bash
cd rust/skill-suggester

# Create bin directory if it doesn't exist
mkdir -p bin

# Copy and rename binaries
cp target/aarch64-apple-darwin/release/pss bin/pss-darwin-arm64
cp target/x86_64-apple-darwin/release/pss bin/pss-darwin-x86_64
cp target/x86_64-unknown-linux-musl/release/pss bin/pss-linux-x86_64
cp target/aarch64-unknown-linux-musl/release/pss bin/pss-linux-arm64
cp target/x86_64-pc-windows-gnu/release/pss.exe bin/pss-windows-x86_64.exe

# Make binaries executable (Unix-like systems)
chmod +x bin/pss-*
```

---

## Running Tests

### Unit Tests

```bash
cd rust/skill-suggester

# Run all tests
cargo test

# Run tests with output
cargo test -- --nocapture

# Run specific test
cargo test test_name
```

### Linting and Code Quality

```bash
# Run Clippy (Rust linter)
cargo clippy --all-targets --all-features

# Check formatting
cargo fmt -- --check

# Auto-format code
cargo fmt
```

### Type Checking

```bash
# Check code without building
cargo check

# Check with all features enabled
cargo check --all-features
```

---

## Local Development Workflow

### 1. Make Code Changes

Edit files in `rust/skill-suggester/src/`

### 2. Build and Test

```bash
cargo build --release
cargo test
cargo clippy --all-targets
```

### 3. Install to Plugin

```bash
# Copy binary to bin/ with correct name
cp target/release/pss bin/pss-darwin-arm64  # Adjust for your platform
chmod +x bin/pss-darwin-arm64
```

### 4. Test with Claude Code

```bash
# From the plugin directory
cd /path/to/perfect-skill-suggester

# Launch Claude Code with plugin loaded
claude --plugin-dir .
```

### 5. Verify Plugin Loaded

Within Claude Code:
```
/pss-status
```

This should show the plugin is active and the binary is found.

---

## Plugin Validation

After building, validate the plugin structure:

```bash
cd /path/to/perfect-skill-suggester

# Run CPV remote validation (no local scripts needed)
uvx --from git+https://github.com/Emasoft/claude-plugins-validation --with pyyaml \
    cpv-remote-validate plugin . --verbose

# Or from Claude Code
claude plugin validate /path/to/perfect-skill-suggester
```

---

## Development Tips

### Fast Iteration

For rapid development, use `cargo watch` to auto-rebuild on file changes:

```bash
# Install cargo-watch
cargo install cargo-watch

# Auto-rebuild on changes
cargo watch -x build

# Auto-test on changes
cargo watch -x test
```

### Debugging

```bash
# Build with debug symbols
cargo build

# Run with logging
RUST_LOG=debug ./target/debug/pss <args>
```

### Performance Profiling

```bash
# Build with profiling info
cargo build --release --profile profiling

# Use tools like flamegraph
cargo install flamegraph
cargo flamegraph
```

---

## Common Build Issues

### Issue: Target not installed

**Error**: `error: Can't find crate for core`

**Solution**: Install the target:
```bash
rustup target add <target-name>
```

### Issue: Cross-compilation linker error

**Error**: `error: linker 'cc' not found`

**Solution**: Install the appropriate cross-compilation toolchain (see Prerequisites).

### Issue: Permission denied on binary

**Error**: `Permission denied` when running binary

**Solution**: Make binary executable:
```bash
chmod +x bin/pss-*
```

---

## Troubleshooting cross-compilation on Apple Silicon

As of v2.9.36, `scripts/pss_build.py` sets `DOCKER_DEFAULT_PLATFORM=linux/amd64`
when invoking `cross` on every target. This is REQUIRED on Apple Silicon hosts
because cross's Docker images (`ghcr.io/cross-rs/*`) are x86_64-only — without
the platform override, Docker reports:

```
docker: no matching manifest for linux/arm64/v8 in the manifest list entries
```

and cross fails on Apple Silicon. The env var forces Docker to pull the x86_64
image and run it under Rosetta/QEMU. Intel hosts ignore the hint and continue
as before.

Additionally, the per-target cross timeout is **30 minutes** (cold Docker image
pulls plus the nlprule English model download inside the container can exceed
10 minutes). The `publish.py` wrapper sets the overall build timeout to **45
minutes**. Build failures are FATAL — `publish.py` aborts the release if any
target fails to build, and verifies that every platform binary was rebuilt
during the current run via build-start mtime comparison.

## CI/CD Integration

> **Canonical example:** [.github/workflows/build-binaries.yml](../.github/workflows/build-binaries.yml) is the authoritative CI build pipeline. The snippet below is for reference only.

For automated builds in CI/CD pipelines (GitHub Actions, GitLab CI, etc.):

```bash
# Install rustup (NOT Homebrew rust — lacks cross target support)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source $HOME/.cargo/env

# Add all targets (musl for Linux — produces static binaries with no libc dep)
rustup target add aarch64-apple-darwin x86_64-apple-darwin \
  x86_64-unknown-linux-musl aarch64-unknown-linux-musl \
  x86_64-pc-windows-gnu

# Install cross (Docker-based cross-compilation)
cargo install cross --git https://github.com/cross-rs/cross

# Build via the canonical build script
export DOCKER_DEFAULT_PLATFORM=linux/amd64  # Apple Silicon runners only
uv run scripts/pss_build.py --all

# Or the full release pipeline (lint + test + validate + build + bump + push):
uv run python scripts/publish.py --bump patch
```

The `pss_build.py` script handles:
- Darwin native build via `cargo build --release`
- Darwin Intel via `cargo build --target x86_64-apple-darwin`
- Linux and Windows via `cross build --target <triple>` with
  `DOCKER_DEFAULT_PLATFORM=linux/amd64` for Apple Silicon compatibility
- Automatic fallback to `cargo-zigbuild` when `cross` is unavailable (but
  zigbuild does NOT support windows on macOS — cross + Docker is required)

Separately, `pss_build_all.py --nlp-only` rebuilds the pss-nlp (negation detector)
binaries. `publish.py` runs this automatically when `rust/negation-detector/`
source changes since the last tag.

---

## Release Checklist

> **Automated release:** `uv run python scripts/publish.py --bump patch` handles the full pipeline (version bump, build, validate, commit, tag).

Before releasing a new version manually:

1. ✅ Update version in ALL 4 files:
   - `VERSION` (project root) — single line, source of truth for display version
   - `rust/skill-suggester/Cargo.toml` → `version = "X.Y.Z"` (metadata only, no recompile)
   - `.claude-plugin/plugin.json` → `"version": "X.Y.Z"`
   - `pyproject.toml` → `version = "X.Y.Z"`
2. ✅ Run full test suite: `cargo test`
3. ✅ Run linter: `cargo clippy --all-targets`
4. ✅ Build all platform binaries
5. ✅ Copy binaries to `bin/` with correct names
6. ✅ Validate plugin: `uvx --from git+https://github.com/Emasoft/claude-plugins-validation --with pyyaml cpv-remote-validate plugin . --verbose`
7. ✅ Test with Claude Code: `claude --plugin-dir .`
8. ✅ Update CHANGELOG.md
9. ✅ Commit and tag: `git tag v1.0.0`

---

## Agent Configuration Profiling

The `/pss-setup-agent` command profiles agent definitions and generates `.agent.toml` configuration files with recommended skills, sub-agents, commands, rules, MCP servers, LSP servers, hooks, and dependencies.

### Workflow

1. **Context Gathering**: Reads agent `.md` definition + optional requirements documents
2. **Two-Pass Scoring**: Pass 1 scores agent-only descriptor; Pass 2 scores requirements-only descriptor (when `--requirements` provided)
3. **AI Post-Filtering**: Profiler agent applies mutual exclusivity, stack compatibility, non-coding detection, redundancy pruning
4. **Specialization Cherry-Pick**: Requirements candidates filtered by agent's domain/duties (pss-design-alignment skill)
5. **Force Include/Exclude**: User-specified `--include`/`--exclude` directives applied
6. **Tier Classification**: Skills sorted into primary/secondary/specialized tiers
7. **Cross-Type Coherence**: Validates no overlaps between skills, agents, MCP, commands
8. **Write & Validate**: Generates `.agent.toml`, validates against schema
9. **Element Verification**: Anti-hallucination check — all names verified against skill index
10. **Self-Review**: Checks name integrity, auto_skills pinning, non-coding filter, coverage, exclusion quality
11. **Interactive Review** (optional): User reviews profile, issues directives to modify

### Key Files

- `agents/pss-agent-profiler.md` — Profiler agent definition (9-step workflow)
- `skills/pss-agent-toml/SKILL.md` — Profiler skill with 7-phase reference documentation
- `schemas/pss-agent-toml-schema.json` — JSON Schema for `.agent.toml` format
- `scripts/pss_validate_agent_toml.py` — Validator script
- `commands/pss-setup-agent.md` — Command definition with argument parsing
- `scripts/pss_verify_profile.py` — Element verification script (anti-hallucination)
- `skills/pss-design-alignment/SKILL.md` — Requirements alignment skill (two-pass scoring + cherry-pick)
- `commands/pss-change-agent-profile.md` — Command for modifying existing profiles

### `.agent.toml` Sections

| Section | Purpose |
|---------|---------|
| `[agent]` | Agent name, source, path |
| `[requirements]` | Project type, tech stack |
| `[skills]` | Primary, secondary, specialized tiers + excluded |
| `[agents]` | Complementary/sub-agents |
| `[commands]` | Recommended slash commands |
| `[rules]` | Active rules |
| `[mcp]` | MCP server recommendations |
| `[hooks]` | Hook configurations |
| `[lsp]` | Language server assignments |
| `[dependencies]` | Required plugins, skills, MCP servers, CLI tools |

### Modifying Existing Profiles

The `/pss-change-agent-profile` command modifies existing `.agent.toml` profiles with natural language instructions:

```bash
/pss-change-agent-profile /path/to/agent.agent.toml add websocket-handler to primary skills
/pss-change-agent-profile /path/to/agent.agent.toml --requirements docs/prd.md align with project requirements
```

Changes are verified against the skill index and validated against the schema before writing.

---

## Querying the index (Phase D, v2.11.0+)

Once the index is built (via `/pss-reindex-skills`), the `pss` binary exposes
read-only subcommands for inspection, scripting, and CI gates. All commands
query CozoDB directly — no Python process, no JSON re-parse.

### Core inventory

```bash
# How many entries are indexed?
pss count
# → 8479

# Populated? Use $? for CI gates (0=yes, 1=empty/corrupt, 2=missing).
pss health; echo $?
# → 0

# Full breakdown: type counts, source counts, timestamp banner.
pss stats --format table
```

### Filtering entries by timestamp

`first_indexed_at` records the moment an entry first entered the index
(preserved across reindexes). `last_updated_at` changes on every reindex.

```bash
# Entries installed in the last day
pss list-added-since 1d

# Pipe to jq to filter by type
pss list-added-since 1d --json | jq '.[] | select(.type == "skill")'

# Range query
pss list-added-between 2026-04-01 2026-04-17 --limit 200

# What changed in the last reindex?
pss list-updated-since 1h
```

Datetime formats: RFC 3339 (`2026-04-16T22:12:27Z`), date-only
(`2026-04-16`, midnight UTC), or relative (`1d`, `2w`, `24h`, `30m`, `120s`).

### Search

```bash
# Substring match on the name column (case-insensitive)
pss find-by-name docker

# Exact keyword match via the skill_keywords auxiliary relation
pss find-by-keyword kubernetes --json | jq length

# Domain-scoped discovery (via skill_domains)
pss find-by-domain security --json

# Language-scoped discovery (via skill_languages)
pss find-by-language python --limit 100
```

### Fetching a single entry

```bash
pss get tailwind-4-docs                # Human-readable block
pss get tailwind-4-docs --json         # JSON object (or array if multiple sources)
pss get react --source user            # Disambiguate when name collides
```

### Scripting tip

All Phase D subcommands exit non-zero on error (invalid datetime, missing DB,
entry not found) and write diagnostics to stderr. Safe to use in `set -e`
scripts without explicit `|| exit`. JSON is always on stdout.

```bash
# CI gate: fail if the index has fewer than 5000 entries
[ "$(pss count)" -ge 5000 ] || {
    echo "Index too small: $(pss count)" >&2
    exit 1
}

# Alert when many skills were added today
today="$(date -u +%Y-%m-%d)"
added_today="$(pss list-added-since "$today" --json | jq length)"
[ "$added_today" -lt 50 ] || echo "High churn: $added_today new today"
```

See [PSS-ARCHITECTURE.md §Rust CLI reference](./PSS-ARCHITECTURE.md#rust-cli-reference-phase-d-v2110)
for the full command list and the Python API equivalents.

---

## Additional Resources

- [Rust Book](https://doc.rust-lang.org/book/)
- [Cargo Documentation](https://doc.rust-lang.org/cargo/)
- [Cross-Compilation Guide](https://rust-lang.github.io/rustup/cross-compilation.html)
- [PSS Architecture](./PSS-ARCHITECTURE.md)
- [Plugin Validation](./PLUGIN-VALIDATION.md)
