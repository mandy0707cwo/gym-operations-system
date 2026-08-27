[CmdletBinding()]
param([string]$InstallRoot = 'C:\GymOperations')

$ErrorActionPreference = 'Stop'
$supabase = Join-Path $InstallRoot 'supabase'
Push-Location $supabase
try {
    $required = @('supabase-db', 'supabase-auth', 'supabase-rest', 'supabase-envoy', 'gym-operations-app')
    $running = docker ps --format '{{.Names}}|{{.Status}}'
    foreach ($name in $required) {
        $match = $running | Where-Object { $_ -like "$name|*" }
        if ($match) { Write-Host "[正常] $match" -ForegroundColor Green }
        else { Write-Host "[異常] $name 未執行" -ForegroundColor Red }
    }
    $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8501/_stcore/health' -UseBasicParsing -TimeoutSec 10
    if ($response.StatusCode -eq 200) { Write-Host '[正常] Streamlit健康檢查通過' -ForegroundColor Green }
} finally { Pop-Location }
