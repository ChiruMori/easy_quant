param([string]$ApiUrl = "http://127.0.0.1:5000/api/v1/health", [switch]$RequireWorker)
$ErrorActionPreference = "Stop"
$response = Invoke-RestMethod -Uri $ApiUrl -TimeoutSec 5
if ($response.status -ne "ok") { throw "API 健康检查失败" }
if ($RequireWorker) {
    $worker = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "easy-quant-worker|easy_quant.worker" }
    if (-not $worker) { throw "未发现 worker 进程" }
}
Write-Output "API 健康；worker 检查=$RequireWorker"
