[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Write-Check([string]$Name, [bool]$Passed, [string]$Detail) {
    $mark = if ($Passed) { '[通過]' } else { '[未通過]' }
    Write-Host "$mark $Name：$Detail" -ForegroundColor $(if ($Passed) { 'Green' } else { 'Red' })
}

$os = Get-CimInstance Win32_OperatingSystem
$computer = Get-CimInstance Win32_ComputerSystem
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
$memoryGb = [math]::Round($computer.TotalPhysicalMemory / 1GB, 1)
$freeDiskGb = [math]::Round($disk.FreeSpace / 1GB, 1)
$is64Bit = $os.OSArchitecture -match '64'
$memoryOk = $memoryGb -ge 15
$diskOk = $freeDiskGb -ge 100
$docker = Get-Command docker -ErrorAction SilentlyContinue
$git = Get-Command git -ErrorAction SilentlyContinue

Write-Host '秀傳運醫營運系統－本機伺服器檢查' -ForegroundColor Cyan
Write-Check 'Windows 64位元' $is64Bit $os.Caption
Write-Check '記憶體' $memoryOk "$memoryGb GB（需求至少16GB規格）"
Write-Check 'C槽可用空間' $diskOk "$freeDiskGb GB（建議至少100GB）"
Write-Check 'Docker' ([bool]$docker) $(if ($docker) { '已安裝' } else { '尚未安裝 Docker Desktop' })
Write-Check 'Git' ([bool]$git) $(if ($git) { '已安裝' } else { '尚未安裝 Git for Windows' })

if ($docker) {
    docker info *> $null
    Write-Check 'Docker服務' ($LASTEXITCODE -eq 0) $(if ($LASTEXITCODE -eq 0) { '已啟動' } else { '尚未啟動' })
}

$network = Get-NetIPConfiguration | Where-Object {
    $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up'
} | Select-Object -First 1

if ($network) {
    Write-Check '院內網路' $true "$($network.InterfaceAlias)／$($network.IPv4Address.IPAddress)"
} else {
    Write-Check '院內網路' $false '找不到可用的IPv4網路與預設閘道'
}

Write-Host "`n檢查完成。未全部通過前，不執行正式安裝。"
