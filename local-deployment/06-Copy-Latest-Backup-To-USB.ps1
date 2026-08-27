[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\GymOperations',
    [string]$UsbDrive = ''
)

$ErrorActionPreference = 'Stop'
$backupRoot = Join-Path $InstallRoot 'backups'
$latest = Get-ChildItem -LiteralPath $backupRoot -Filter 'gym_database_*.dump' -File |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $latest) { throw '找不到可複製的資料庫備份，請先執行05備份工具。' }

if (-not $UsbDrive) {
    $usb = Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -eq 2 } | Select-Object -First 1
    if (-not $usb) { throw '找不到USB隨身碟。請插入USB後重試。' }
    $UsbDrive = $usb.DeviceID
}

$destination = Join-Path "$UsbDrive\" '秀傳運醫營運系統備份'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
Copy-Item -LiteralPath $latest.FullName -Destination $destination -Force
$hashFile = "$($latest.FullName).sha256"
if (Test-Path -LiteralPath $hashFile) { Copy-Item -LiteralPath $hashFile -Destination $destination -Force }

$copied = Join-Path $destination $latest.Name
$sourceHash = (Get-FileHash -LiteralPath $latest.FullName -Algorithm SHA256).Hash
$copiedHash = (Get-FileHash -LiteralPath $copied -Algorithm SHA256).Hash
if ($sourceHash -ne $copiedHash) { throw 'USB備份驗證失敗，請更換USB後重試。' }

Write-Host "USB備份完成並通過驗證：$copied" -ForegroundColor Green
Write-Host '請使用「安全地移除硬體」後再拔除USB。'
