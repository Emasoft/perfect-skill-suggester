# Perfect Skill Suggester - Windows hook wrapper
# Runs the pre-built Windows binary

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$BinDir = Join-Path $ScriptDir "bin"
$Binary = Join-Path $BinDir "pss-windows-x86_64.exe"

# Check if binary exists
if (-not (Test-Path $Binary)) {
    Write-Error "Binary not found: $Binary"
    Write-Error "Please build the project or download pre-built binaries."
    # Return empty response to not block Claude
    Write-Output '{"version":"1.0","additionalContext":[]}'
    exit 0
}

# Read stdin and pipe to binary
$input | & $Binary
