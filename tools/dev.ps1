param(
    [ValidateSet("api", "worker", "frontend")]
    [string]$Target = "api"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

switch ($Target) {
    "api" { uv run --project "$root/backend" easy-quant-api }
    "worker" { uv run --project "$root/backend" easy-quant-worker }
    "frontend" { pnpm --dir "$root/frontend" dev }
}
