[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\GymOperations',
    [string]$ServerIp = '',
    [string]$SupabaseRelease = 'self-hosted/v0.8.0'
)

$ErrorActionPreference = 'Stop'
$serviceNames = @('db', 'auth', 'rest', 'meta', 'studio', 'api-gw', 'gym-app')

function Require-Command([string]$Name, [string]$Hint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "找不到 $Name。$Hint"
    }
}

function Set-EnvValue([string]$Path, [string]$Name, [string]$Value) {
    $lines = [System.Collections.Generic.List[string]](Get-Content -LiteralPath $Path)
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^$([regex]::Escape($Name))=") {
            $lines[$i] = "$Name=$Value"
            $found = $true
            break
        }
    }
    if (-not $found) { $lines.Add("$Name=$Value") }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($Path, $lines, $utf8NoBom)
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '請以系統管理員身分開啟PowerShell後再執行安裝。'
}

Require-Command docker '請先安裝並啟動 Docker Desktop。'
Require-Command git '請先安裝 Git for Windows。'
Require-Command bash '請確認 Git for Windows 已包含 Git Bash。'
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop 尚未啟動。' }

$computer = Get-CimInstance Win32_ComputerSystem
$memoryGb = [math]::Round($computer.TotalPhysicalMemory / 1GB, 1)
if ($memoryGb -lt 15) { throw "目前記憶體為 $memoryGb GB；此安裝包以16GB規格為最低基準。" }

if (-not $ServerIp) {
    $ServerIp = (Get-NetIPConfiguration | Where-Object {
        $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up'
    } | Select-Object -First 1).IPv4Address.IPAddress
}
if ($ServerIp -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
    throw '無法判斷伺服器IPv4位址，請使用 -ServerIp 192.168.x.x 指定。'
}

$appSource = Split-Path -Parent $PSScriptRoot
$appTarget = Join-Path $InstallRoot 'app'
$supabaseTarget = Join-Path $InstallRoot 'supabase'
$downloadTarget = Join-Path $InstallRoot '_download_supabase'
$backupTarget = Join-Path $InstallRoot 'backups'

if (Test-Path -LiteralPath $supabaseTarget) {
    throw "安裝目錄已存在：$supabaseTarget。為避免覆蓋資料，安裝已停止。"
}

New-Item -ItemType Directory -Force -Path $InstallRoot, $appTarget, $backupTarget | Out-Null
git clone --depth 1 --branch $SupabaseRelease https://github.com/supabase/supabase.git $downloadTarget
if ($LASTEXITCODE -ne 0) { throw 'Supabase官方部署檔下載失敗。' }
Copy-Item -Path (Join-Path $downloadTarget 'docker') -Destination $supabaseTarget -Recurse

$appFiles = @('app.py', 'requirements.txt', 'VERSION', 'Dockerfile.local', '.dockerignore')
foreach ($file in $appFiles) {
    Copy-Item -LiteralPath (Join-Path $appSource $file) -Destination (Join-Path $appTarget $file) -Force
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'docker-compose.gym.yml') -Destination (Join-Path $supabaseTarget 'docker-compose.gym.yml') -Force
Copy-Item -LiteralPath (Join-Path $supabaseTarget '.env.example') -Destination (Join-Path $supabaseTarget '.env') -Force

$bashPath = ($supabaseTarget -replace '\\', '/')
& bash -lc "cd '$bashPath' && sh utils/generate-keys.sh --update-env && sh utils/add-new-auth-keys.sh --update-env"
if ($LASTEXITCODE -ne 0) { throw '安全金鑰產生失敗，安裝已停止。' }

$envPath = Join-Path $supabaseTarget '.env'
Set-EnvValue $envPath 'COMPOSE_FILE' 'docker-compose.yml:docker-compose.gym.yml'
Set-EnvValue $envPath 'SUPABASE_PUBLIC_URL' "http://127.0.0.1:8000"
Set-EnvValue $envPath 'API_EXTERNAL_URL' "http://127.0.0.1:8000/auth/v1"
Set-EnvValue $envPath 'SITE_URL' "http://${ServerIp}:8501"
Set-EnvValue $envPath 'ADDITIONAL_REDIRECT_URLS' "http://${ServerIp}:8501/**"
Set-EnvValue $envPath 'API_GW_HTTP_PORT' '127.0.0.1:8000'
Set-EnvValue $envPath 'DISABLE_SIGNUP' 'true'
Set-EnvValue $envPath 'ENABLE_EMAIL_AUTOCONFIRM' 'true'
Set-EnvValue $envPath 'STUDIO_DEFAULT_ORGANIZATION' 'Show Chwan Sports Medicine'
Set-EnvValue $envPath 'STUDIO_DEFAULT_PROJECT' 'Gym Operations Local'

Push-Location $supabaseTarget
try {
    docker compose pull db auth rest meta studio api-gw
    if ($LASTEXITCODE -ne 0) { throw 'Docker映像下載失敗。' }
    docker compose up -d --build --wait @serviceNames
    if ($LASTEXITCODE -ne 0) { throw '本機服務啟動失敗。' }
} finally {
    Pop-Location
}

if (-not (Get-NetFirewallRule -DisplayName '秀傳運醫營運系統-8501' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName '秀傳運醫營運系統-8501' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8501 -Profile Private | Out-Null
}

Write-Host "`n本機測試環境已建立。" -ForegroundColor Green
Write-Host "系統網址：http://${ServerIp}:8501"
Write-Host '目前仍是空白本機資料庫；請勿停用線上系統。下一步須執行資料搬移與核對。'
Write-Host "安全設定檔：$envPath（不得傳送或上傳）"
