<#
.SYNOPSIS
    启用 WSL2 并安装 Docker Desktop（需要管理员权限）。
.DESCRIPTION
    依次执行：检查虚拟化 → 启用 WSL/虚拟机平台 → 更新 WSL2 内核 → 安装 Docker Desktop。
    执行完必须重启电脑，Docker 才能正常启动。
.EXAMPLE
    # 右键 PowerShell「以管理员身份运行」，然后：
    powershell -ExecutionPolicy Bypass -File "C:\Users\18767\Desktop\独立站\scripts\setup-docker-admin.ps1"

    # 顺带装一个 Ubuntu 发行版（可选）：
    powershell -ExecutionPolicy Bypass -File .\scripts\setup-docker-admin.ps1 -WithUbuntu
#>
#Requires -RunAsAdministrator
param(
    [switch]$WithUbuntu
)

$ErrorActionPreference = 'Continue'

function Step($n, $text) { Write-Host "`n[$n] $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "    √ $text" -ForegroundColor Green }
function Warn($text) { Write-Host "    ! $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host "    × $text" -ForegroundColor Red }

Step 1 "检查 CPU 虚拟化"
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
if ($cpu.VirtualizationFirmwareEnabled) {
    Ok ("{0} · VT-x 已开启" -f $cpu.Name.Trim())
} else {
    Fail "BIOS 里未开启虚拟化，请进 BIOS 打开 Intel VT-x / SVM 后再运行本脚本"
    exit 1
}

Step 2 "启用 Windows 功能（WSL + 虚拟机平台）"
$features = @('Microsoft-Windows-Subsystem-Linux', 'VirtualMachinePlatform')
foreach ($f in $features) {
    $state = (Get-WindowsOptionalFeature -Online -FeatureName $f).State
    if ($state -eq 'Enabled') {
        Ok "$f 已启用"
    } else {
        Write-Host "    启用 $f ..." -NoNewline
        $r = Enable-WindowsOptionalFeature -Online -FeatureName $f -All -NoRestart -WarningAction SilentlyContinue
        if ($r.RestartNeeded) { Write-Host " 完成（需重启生效）" -ForegroundColor Yellow }
        else { Write-Host " 完成" -ForegroundColor Green }
    }
}

Step 3 "更新 WSL2 内核并设为默认版本"
wsl --update 2>&1 | ForEach-Object { "    $_" }
wsl --set-default-version 2 2>&1 | ForEach-Object { "    $_" }

if ($WithUbuntu) {
    Step 3.1 "安装 Ubuntu 发行版"
    wsl --install -d Ubuntu --no-launch 2>&1 | ForEach-Object { "    $_" }
}

Step 4 "安装 Docker Desktop"
$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($docker) {
    Ok "Docker 已存在：$($docker.Source)"
} else {
    Write-Host "    通过 winget 安装 Docker.DockerDesktop（约 500 MB，请耐心等待）..." -ForegroundColor Gray
    winget install --id Docker.DockerDesktop --exact --silent `
        --accept-package-agreements --accept-source-agreements --disable-interactivity 2>&1 |
        ForEach-Object { "    $_" }
    if ($LASTEXITCODE -eq 0) {
        Ok "Docker Desktop 安装完成"
    } else {
        Fail "winget 安装失败（exit=$LASTEXITCODE），可手动下载：https://www.docker.com/products/docker-desktop/"
    }
}

Write-Host "`n================ 下一步 ================" -ForegroundColor Cyan
Write-Host "1. 重启电脑（必须，否则 WSL2 无法工作）"
Write-Host "2. 重启后启动 Docker Desktop，等右下角鲸鱼图标变绿"
Write-Host "3. 配置代理（国内拉镜像必需）："
Write-Host "   Docker Desktop → Settings → Resources → Proxies → http://127.0.0.1:10808"
Write-Host "4. 回到项目目录执行："
Write-Host "   docker compose -f docker-compose.dev.yml up -d"
Write-Host "5. 自检：powershell -ExecutionPolicy Bypass -File .\scripts\verify-env.ps1`n"
