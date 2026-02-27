#!/bin/bash
# Perfect Skill Suggester - Unix hook wrapper
# Detects platform and runs the appropriate pre-built binary

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$SCRIPT_DIR/bin"

# Detect OS and architecture
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

# Map architecture names
case "$ARCH" in
    x86_64|amd64)
        ARCH="x86_64"
        ;;
    aarch64|arm64)
        ARCH="arm64"
        ;;
    *)
        echo "Unsupported architecture: $ARCH" >&2
        exit 1
        ;;
esac

# Map OS names and select binary
case "$OS" in
    darwin)
        if [ "$ARCH" = "arm64" ]; then
            BINARY="$BIN_DIR/pss-darwin-arm64"
        else
            BINARY="$BIN_DIR/pss-darwin-x86_64"
        fi
        ;;
    linux)
        if [ "$ARCH" = "arm64" ]; then
            BINARY="$BIN_DIR/pss-linux-arm64"
        else
            BINARY="$BIN_DIR/pss-linux-x86_64"
        fi
        ;;
    *)
        echo "Unsupported OS: $OS" >&2
        exit 1
        ;;
esac

# Check if binary exists
if [ ! -f "$BINARY" ]; then
    echo "Binary not found: $BINARY" >&2
    echo "Please build the project or download pre-built binaries." >&2
    # Return empty response to not block Claude
    echo '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit"}}'
    exit 0
fi

# Make sure it's executable
chmod +x "$BINARY" 2>/dev/null || true

# Run the binary, passing stdin through
exec "$BINARY"
