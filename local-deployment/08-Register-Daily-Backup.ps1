[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\GymOperations',
    [string]$BackupTime = '02:00'
)

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '請以系統管理員身分開啟PowerShell後再執行。'
}

$backupScript = Join-Path $InstallRoot 'app\local-deployment\05-Backup-Database.ps1'
if (-not (Test-Path -LiteralPath $backupScript)) {
    $sourceScript = Join-Path $PSScriptRoot '05-Backup-Database.ps1'
    if (-not (Test-Path -LiteralPath $sourceScript)) { throw '找不到備份程式。' }
    $targetFolder = Split-Path -Parent $backupScript
    New-Item -ItemType Directory -Force -Path $targetFolder | Out-Null
    Copy-Item -LiteralPath $sourceScript -Destination $backupScript -Force
}

$at = [datetime]::ParseExact($BackupTime, 'HH:mm', $null)
$argument = "-NoProfile -ExecutionPolicy Bypass -File `"$backupScript`" -InstallRoot `"$InstallRoot`""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument
$trigger = New-ScheduledTaskTrigger -Daily -At $at
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName '秀傳運醫營運系統每日備份' -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force | Out-Null

Write-Host "已設定每日 $BackupTime 自動備份。" -ForegroundColor Green
