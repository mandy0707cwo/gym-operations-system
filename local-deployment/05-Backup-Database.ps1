[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\GymOperations',
    [int]$RetentionDays = 30
)

$ErrorActionPreference = 'Stop'
$backupRoot = Join-Path $InstallRoot 'backups'
$envPath = Join-Path $InstallRoot 'supabase\.env'
if (-not (Test-Path -LiteralPath $envPath)) { throw '找不到本機Supabase設定。' }
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$fileName = "gym_database_${stamp}.dump"
$containerFile = "/tmp/$fileName"
$outputFile = Join-Path $backupRoot $fileName

docker exec supabase-db pg_dump -U postgres -d postgres -Fc --no-owner --no-privileges -f $containerFile
if ($LASTEXITCODE -ne 0) { throw '資料庫備份建立失敗。' }
docker cp "supabase-db:$containerFile" $outputFile
if ($LASTEXITCODE -ne 0) { throw '資料庫備份複製失敗。' }
docker exec supabase-db rm -f $containerFile | Out-Null

$hash = Get-FileHash -LiteralPath $outputFile -Algorithm SHA256
"$($hash.Hash)  $fileName" | Set-Content -LiteralPath "$outputFile.sha256" -Encoding ascii

$cutoff = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem -LiteralPath $backupRoot -File | Where-Object {
    $_.LastWriteTime -lt $cutoff -and $_.Name -match '^gym_database_\d{8}_\d{6}\.dump(\.sha256)?$'
} | Remove-Item -Force

Write-Host "備份完成：$outputFile" -ForegroundColor Green
Write-Host "檔案大小：$([math]::Round((Get-Item -LiteralPath $outputFile).Length / 1MB, 2)) MB"
