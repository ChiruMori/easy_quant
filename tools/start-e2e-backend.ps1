$ErrorActionPreference = "Stop"

$projectRoot = Join-Path $PSScriptRoot ".."
$backendRoot = Join-Path $projectRoot "backend"
$env:FLASK_SKIP_DOTENV = "1"
Set-Location $backendRoot
uv run --project $backendRoot flask --app tests.e2e_app:create_e2e_app run --no-reload --host 127.0.0.1 --port 5100
