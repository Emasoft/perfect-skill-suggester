# Binary Status

The command also checks if the Rust binary is available for the detected platform.

## Supported Platforms

| Platform | Binary | Notes |
|----------|--------|-------|
| macOS Apple Silicon | `pss-darwin-arm64` | Native build |
| macOS Intel | `pss-darwin-x86_64` | Native build |
| Linux x86_64 | `pss-linux-x86_64` | Static (musl) |
| Linux ARM64 | `pss-linux-arm64` | Static (musl) |
| Windows x86_64 | `pss-windows-x86_64.exe` | Cross-compiled |

## Where the binary is looked for

The name above is the same string everywhere; only the directory varies. All
three resolvers (`pss-hook-dispatch.sh`, `pss_paths.resolve_pss_binary()`,
and the Rust `pss-nlp` probe) search these roots in this order:

| # | root | what it is |
|---|------|------------|
| 1 | `$PSS_BINARY_DIR/<name>` | operator escape hatch — populate it yourself |
| 2 | `$HOME/.claude/cache/pss-bin/current/<name>` | the fetched store (see below) — fresh installs fetch here on first session start |
| 3 | `$CLAUDE_PLUGIN_ROOT/bin/<name>` | transitional — fresh installs have nothing here |
| 4 | `<repo>/bin/<name>` | local development checkouts |

The store path is a CONSTANT — deliberately not derived from
`$CLAUDE_PLUGIN_DATA` — so the POSIX-sh resolver and the Rust resolver can
stat the same path without importing Python.

## Fetched-binary store

`scripts/pss_fetch_binaries.py` downloads only the two binaries this machine
can execute and verifies each against the sha256 in the git-tracked
`bin/manifest.json`. The store is content-addressed, so an unchanged engine
costs a new plugin version zero bytes. Phase 3 (this release): the store is
the FIRST location checked after `$PSS_BINARY_DIR`; a fresh install fetches
here on first session start.

```
$HOME/.claude/cache/pss-bin/<sha256[:16]>/<name>   the artifact
$HOME/.claude/cache/pss-bin/current/<name>         what the resolvers stat
$HOME/.claude/cache/pss-bin/.state.json            why the last attempt ended how it did
```

Render the state file — it is the ONLY signal a fetch failed, because the hot
path stays graceful (empty hook JSON, exit 0) rather than breaking the session:

```bash
STATE="$HOME/.claude/cache/pss-bin/.state.json"

if [ -f "$STATE" ]; then
    cat "$STATE"
else
    echo "No fetch has run — the binary is being served from bin/."
fi
```

Report `status` verbatim and translate it for the user:

| `status` | means | remedy to show |
|----------|-------|----------------|
| `ok` | store is populated and verified | none |
| `fetching` | a download is running right now (written at spawn) | none — say the engine is downloading and suggestions may be limited this session |
| `network-blocked` | download refused after 3 attempts | offline install, or `PSS_BINARY_DIR` |
| `checksum-mismatch` | bytes did not match `bin/manifest.json` | **do not use them** — re-run the fetch; a repeat means a tampered or mis-published asset |
| `manifest-incomplete` | this platform is absent from the manifest | the release did not ship this platform's binary |
| `offline-missing` / `offline-incomplete` | `--offline` tarball absent or short | re-download `pss-binaries-<version>.tar.gz` |
| `unsupported-platform` | no binary exists for this OS/arch | build from source |

A `checksum-mismatch` is never cosmetic: it is the one failure the git-tracked
manifest exists to catch, so surface it prominently rather than folding it in
with the network errors.

## Example Output

```
╔══════════════════════════════════════════════════════════════╗
║                     BINARY STATUS                            ║
╠══════════════════════════════════════════════════════════════╣
║ Platform:             darwin-arm64                           ║
║ Binary:               bin/pss-darwin-arm64                   ║
║ Status:               ✓ AVAILABLE                            ║
║ Size:                 2.2 MB                                 ║
║ Expected Latency:     ~10ms                                  ║
╚══════════════════════════════════════════════════════════════╝
```
