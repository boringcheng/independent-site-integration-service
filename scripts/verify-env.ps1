<#
.SYNOPSIS
    检查本机是否满足 Shopify + SHOPLINE 集成平台的开发环境要求。
.NOTES
    用法: powershell -ExecutionPolicy Bypass -File .\scripts\verify-env.ps1
    只读检查，不会修改任何配置。
#>

$ErrorActionPreference = 'Continue'
$script:fail = 0
$script:warn = 0

function Write-Item {
    param([string]$Status, [string]$Name, [string]$Detail)
    $color = switch ($Status) { 'OK' { 'Green' } 'WARN' { 'Yellow' } default { 'Red' } }
    if ($Status -eq 'FAIL') { $script:fail++ }
    if ($Status -eq 'WARN') { $script:warn++ }
    $mark = switch ($Status) { 'OK' { '√' } 'WARN' { '!' } default { '×' } }
    Write-Host ("  [{0}] {1,-22} {2}" -f $mark, $Name, $Detail) -ForegroundColor $color
}

function Get-Version {
    param([string]$Command, [string[]]$Arguments = @('--version'))
    try {
        $out = & $Command @Arguments 2>&1 | Out-String
        return ($out -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1).Trim()
    } catch { return $null }
}

Write-Host "`n=== 系统 ===" -ForegroundColor Cyan
$os = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -ErrorAction SilentlyContinue
$build = [int]$os.CurrentBuild
$name = if ($build -ge 22000) { 'Windows 11' } else { 'Windows 10' }
$edition = switch -Wildcard ($os.EditionID) { 'Core*' { '家庭版' } 'Professional*' { '专业版' } default { $os.EditionID } }
Write-Item 'OK' 'Windows' ("{0} {1} (Build {2})" -f $name, $edition, $build)
$elevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Write-Item $(if ($elevated) { 'OK' } else { 'WARN' }) '提权状态' $(if ($elevated) { '管理员' } else { '普通用户（装 Docker/WSL 需提权）' })

$drives = [System.IO.DriveInfo]::GetDrives() | Where-Object { $_.IsReady -and $_.DriveType -eq 'Fixed' }
foreach ($d in $drives) {
    $freeGB = [math]::Round($d.AvailableFreeSpace / 1GB, 1)
    Write-Item $(if ($freeGB -ge 20) { 'OK' } else { 'WARN' }) ("磁盘 " + $d.Name) ("剩余 {0} GB" -f $freeGB)
}

Write-Host "`n=== 后端 ===" -ForegroundColor Cyan
$py312 = $null
try {
    $launchers = & py -0p 2>&1
    $py312 = ($launchers | Select-String '3\.12').ToString().Trim()
} catch { }

if ($py312) {
    $ver = (& py -3.12 -c "import sys;print(sys.version.split()[0])" 2>&1).Trim()
    Write-Item 'OK' 'Python 3.12' "$ver"
} else {
    Write-Item 'FAIL' 'Python 3.12' '未安装：py -0p 无 3.12'
}

$venv = Test-Path (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe')
Write-Item $(if ($venv) { 'OK' } else { 'WARN' }) '项目 .venv' $(if ($venv) { '已创建' } else { '未创建：py -3.12 -m venv .venv' })

$pipVer = Get-Version 'python' @('-m', 'pip', '--version')
Write-Item $(if ($pipVer) { 'OK' } else { 'FAIL' }) 'pip' $(if ($pipVer) { ($pipVer -split ' ')[1] } else { '不可用' })

Write-Host "`n=== 版本管理 ===" -ForegroundColor Cyan
$gitVer = Get-Version 'git'
Write-Item $(if ($gitVer) { 'OK' } else { 'FAIL' }) 'Git' $(if ($gitVer) { $gitVer } else { '未安装' })

$userName = (& git config --global user.name) 2>&1
$userEmail = (& git config --global user.email) 2>&1
if ($userName -and $userEmail -and $userName -notmatch 'fatal') {
    Write-Item 'OK' 'git 身份' "$userName <$userEmail>"
} else {
    Write-Item 'WARN' 'git 身份' '未配置：git config --global user.name/user.email'
}

Write-Host "`n=== 前端 ===" -ForegroundColor Cyan
$nodeVer = Get-Version 'node'
if ($nodeVer) {
    $major = [int](($nodeVer -replace '^v', '') -split '\.')[0]
    Write-Item $(if ($major -ge 20) { 'OK' } else { 'WARN' }) 'Node.js' "$nodeVer$(if ($major -ge 20) { '' } else { '（建议 20+ LTS）' })"
} else {
    Write-Item 'FAIL' 'Node.js' '未安装'
}
$npmVer = Get-Version 'npm'
Write-Item $(if ($npmVer) { 'OK' } else { 'FAIL' }) 'npm' $(if ($npmVer) { $npmVer } else { '不可用（检查执行策略）' })

Write-Host "`n=== 容器 ===" -ForegroundColor Cyan
$dockerVer = Get-Version 'docker'
Write-Item $(if ($dockerVer) { 'OK' } else { 'FAIL' }) 'Docker' $(if ($dockerVer) { $dockerVer } else { '未安装：先跑 scripts\setup-docker-admin.ps1' })

$wslRaw = (& wsl --list --quiet 2>$null | Out-String)
$wslDists = ($wslRaw -replace "`0", '') -split "`r?`n" | Where-Object { $_.Trim() } | ForEach-Object { $_.Trim() }
if ($LASTEXITCODE -eq 0 -and $wslDists) {
    Write-Item 'OK' 'WSL 发行版' ($wslDists -join ', ')
} else {
    Write-Item 'WARN' 'WSL' '未启用或未安装发行版'
}

Write-Host "`n=== 端口占用（本地开发常用） ===" -ForegroundColor Cyan
$dockerPorts = ''
try { $dockerPorts = (& docker ps --format '{{.Names}} {{.Ports}}' 2>$null | Out-String) } catch { }
foreach ($port in 3306, 6379, 8000, 5173) {
    $busy = $null
    try { $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue } catch { }
    if (-not $busy) {
        Write-Item 'OK' "端口 $port" '空闲'
    } else {
        $mine = ($dockerPorts -split "`r?`n" | Where-Object { $_ -match ":$port->" } | Select-Object -First 1)
        if ($mine) { Write-Item 'OK' "端口 $port" ("由本项目容器占用（" + ($mine -split ' ')[0] + "）") }
        else { Write-Item 'WARN' "端口 $port" '已被其他程序占用' }
    }
}

Write-Host ""
if ($script:fail -eq 0 -and $script:warn -eq 0) {
    Write-Host "全部就绪，可以开始开发。" -ForegroundColor Green
} else {
    Write-Host ("检查完成：{0} 项不合格，{1} 项待处理。" -f $script:fail, $script:warn) -ForegroundColor Yellow
}
exit $(if ($script:fail -gt 0) { 1 } else { 0 })
