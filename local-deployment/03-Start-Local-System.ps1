[CmdletBinding()]
param([string]$InstallRoot = 'C:\GymOperations')

$ErrorActionPreference = 'Stop'
$supabase = Join-Path $InstallRoot 'supabase'
if (-not (Test-Path -LiteralPath (Join-Path $supabase '.env'))) { throw '找不到本機系統安裝目錄。' }
Push-Location $supabase
try {
    docker compose up -d --wait db auth rest meta studio api-gw gym-app
    docker compose ps
} finally { Pop-Location }
