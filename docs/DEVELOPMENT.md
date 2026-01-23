# PSS Plugin Development Guide

This document provides instructions for building, testing, and developing the Perfect Skill Suggester (PSS) plugin.

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
   rustup target add x86_64-unknown-linux-gnu    # Linux x64
   rustup target add aarch64-unknown-linux-gnu   # Linux ARM

   # Windows target
   rustup target add x86_64-pc-windows-gnu       # Windows x64
   ```

3. **Additional Dependencies (for cross-compilation)**

   On macOS, you may need:
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
cd /Users/emanuelesabetta/Code/SKILL_FACTORY/OUTPUT_SKILLS/perfect-skill-suggester/rust/skill-suggester

# Debug build (faster compilation, slower execution)
cargo build

# Release build (optimized for performance)
cargo build --release
```

The binary will be located at:
- Debug: `target/debug/skill-suggester`
- Release: `target/release/skill-suggester`

---

## Cross-Compilation for All Platforms

### Build for Specific Target

```bash
cd rust/skill-suggester

# macOS ARM (M1/M2/M3)
cargo build --release --target aarch64-apple-darwin

# macOS Intel
cargo build --release --target x86_64-apple-darwin

# Linux x64
cargo build --release --target x86_64-unknown-linux-gnu

# Linux ARM
cargo build --release --target aarch64-unknown-linux-gnu

# Windows x64
cargo build --release --target x86_64-pc-windows-gnu
```

### Build All Platforms at Once

```bash
cd rust/skill-suggester

# Build script for all platforms
for target in \
  aarch64-apple-darwin \
  x86_64-apple-darwin \
  x86_64-unknown-linux-gnu \
  aarch64-unknown-linux-gnu \
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
| macOS ARM | `pss-macos-arm64` |
| macOS Intel | `pss-macos-x64` |
| Linux x64 | `pss-linux-x64` |
| Linux ARM | `pss-linux-arm64` |
| Windows x64 | `pss-windows-x64.exe` |

### Installing Binaries to Plugin

After building, copy binaries to the plugin's `bin/` directory:

```bash
cd rust/skill-suggester

# Create bin directory if it doesn't exist
mkdir -p ../../bin

# Copy and rename binaries
cp target/aarch64-apple-darwin/release/skill-suggester ../../bin/pss-macos-arm64
cp target/x86_64-apple-darwin/release/skill-suggester ../../bin/pss-macos-x64
cp target/x86_64-unknown-linux-gnu/release/skill-suggester ../../bin/pss-linux-x64
cp target/aarch64-unknown-linux-gnu/release/skill-suggester ../../bin/pss-linux-arm64
cp target/x86_64-pc-windows-gnu/release/skill-suggester.exe ../../bin/pss-windows-x64.exe

# Make binaries executable (Unix-like systems)
chmod +x ../../bin/pss-*
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
cp target/release/skill-suggester ../../bin/pss-macos-arm64  # Adjust for your platform
chmod +x ../../bin/pss-macos-arm64
```

### 4. Test with Claude Code

```bash
# From the SKILL_FACTORY directory
cd /Users/emanuelesabetta/Code/SKILL_FACTORY

# Launch Claude Code with plugin loaded
claude --plugin-dir ./OUTPUT_SKILLS/perfect-skill-suggester
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
cd /Users/emanuelesabetta/Code/SKILL_FACTORY/OUTPUT_SKILLS/perfect-skill-suggester

# Run PSS-specific validator
uv run python scripts/pss_validate_plugin.py --verbose

# Or from Claude Code
claude plugin validate ./OUTPUT_SKILLS/perfect-skill-suggester
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
RUST_LOG=debug ./target/debug/skill-suggester <args>
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

## CI/CD Integration

For automated builds in CI/CD pipelines:

```bash
# Install Rust in CI
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source $HOME/.cargo/env

# Add all targets
rustup target add aarch64-apple-darwin x86_64-apple-darwin \
  x86_64-unknown-linux-gnu aarch64-unknown-linux-gnu \
  x86_64-pc-windows-gnu

# Build all platforms
cd rust/skill-suggester
cargo build --release --target aarch64-apple-darwin
cargo build --release --target x86_64-apple-darwin
cargo build --release --target x86_64-unknown-linux-gnu
cargo build --release --target aarch64-unknown-linux-gnu
cargo build --release --target x86_64-pc-windows-gnu

# Run tests
cargo test
cargo clippy --all-targets
```

---

## Release Checklist

Before releasing a new version:

1. ✅ Update version in `Cargo.toml`
2. ✅ Update version in `.claude-plugin/plugin.json`
3. ✅ Run full test suite: `cargo test`
4. ✅ Run linter: `cargo clippy --all-targets`
5. ✅ Build all platform binaries
6. ✅ Copy binaries to `bin/` with correct names
7. ✅ Validate plugin: `uv run python scripts/pss_validate_plugin.py`
8. ✅ Test with Claude Code: `claude --plugin-dir .`
9. ✅ Update CHANGELOG.md
10. ✅ Commit and tag: `git tag v1.0.0`

---

## Additional Resources

- [Rust Book](https://doc.rust-lang.org/book/)
- [Cargo Documentation](https://doc.rust-lang.org/cargo/)
- [Cross-Compilation Guide](https://rust-lang.github.io/rustup/cross-compilation.html)
- [PSS Architecture](./PSS-ARCHITECTURE.md)
- [Plugin Validation](./PLUGIN-VALIDATION.md)
