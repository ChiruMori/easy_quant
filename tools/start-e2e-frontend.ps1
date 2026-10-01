$ErrorActionPreference = "Stop"

$projectRoot = Join-Path $PSScriptRoot ".."
$env:EASY_QUANT_API_PROXY_TARGET = "http://127.0.0.1:5100"
pnpm --dir (Join-Path $projectRoot "frontend") dev --host 127.0.0.1 --port 5174
