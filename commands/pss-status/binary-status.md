# Binary Status

The command also checks if the Rust binary is available for the detected platform.

## Supported Platforms

| Platform | Binary | Notes |
|----------|--------|-------|
| macOS Apple Silicon | `bin/pss-darwin-arm64` | Native build |
| macOS Intel | `bin/pss-darwin-x86_64` | Native build |
| Linux x86_64 | `bin/pss-linux-x86_64` | Static (musl) |
| Linux ARM64 | `bin/pss-linux-arm64` | Static (musl) |
| Windows x86_64 | `bin/pss-windows-x86_64.exe` | Cross-compiled |

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
