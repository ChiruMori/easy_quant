param([ValidateSet("upgrade", "downgrade")][string]$Action = "upgrade", [string]$Revision = "head")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if ($Action -eq "downgrade" -and $Revision -eq "head") {
    throw "降级必须显式传入 -Revision，避免意外回退数据库"
}
uv run --project "$root/backend" alembic -c "$root/backend/alembic.ini" $Action $Revision
