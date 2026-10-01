param(
    [ValidateSet("backup", "restore")][string]$Action = "backup",
    [Parameter(Mandatory)][string]$Path,
    [string]$HostName = "127.0.0.1",
    [int]$Port = 3306,
    [string]$Database = "easy_quant",
    [string]$User = "easy_quant"
)
$ErrorActionPreference = "Stop"
$resolved = [System.IO.Path]::GetFullPath($Path)
if ($Action -eq "backup") {
    & mariadb-dump --single-transaction --host=$HostName --port=$Port --user=$User --password $Database --result-file=$resolved
    if ($LASTEXITCODE -ne 0) { throw "备份失败" }
    Write-Output "备份已写入 $resolved"
} else {
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) { throw "恢复文件不存在：$resolved" }
    Write-Warning "即将把 $resolved 恢复到数据库 $Database；此操作会覆盖同名对象中的数据"
    Get-Content -Raw -LiteralPath $resolved | & mariadb --host=$HostName --port=$Port --user=$User --password $Database
    if ($LASTEXITCODE -ne 0) { throw "恢复失败" }
    Write-Output "恢复完成"
}
