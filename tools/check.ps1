$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Push-Location $root
try {
    pnpm check
    pnpm test:e2e
}
finally {
    Pop-Location
}
