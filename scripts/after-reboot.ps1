<#
.SYNOPSIS
    重启之后的一步到位脚本：启动 Docker Desktop → 等待引擎就绪 → 拉起 MySQL/Redis。
.DESCRIPTION
    前提：已执行过 scripts\setup-docker-admin.ps1 并重启电脑。
    如果拉镜像失败，说明代理没配好，脚本会给出提示而不是一直卡住。
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\after-reboot.ps1
#>
param(
    [switch]$SkipCompose
)

$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

function Info($t) { Write-Host "  $t" }
function Ok($t) { Write-Host "  [√] $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  [!] $t" -ForegroundColor Yellow }
function Dead($t) { Write-Host "  [×] $t" -ForegroundColor Red }

Write-Host "`n[1/4] 检查 WSL2" -ForegroundColor Cyan
wsl --status *> $null
if ($LASTEXITCODE -ne 0) {
    Dead "WSL2 未就绪（exit=$LASTEXITCODE）。请确认已重启电脑；仍未解决就以管理员身份重跑 setup-docker-admin.ps1。"
    exit 1
}
Ok "WSL2 正常"

Write-Host "`n[2/4] 启动 Docker 引擎" -ForegroundColor Cyan
function Test-Engine {
    docker info *> $null
    return ($LASTEXITCODE -eq 0)
}
if (Test-Engine) {
    Ok "引擎已在运行"
} else {
    $exe = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path $exe)) { Dead "找不到 Docker Desktop：$exe"; exit 1 }
    Info "启动 Docker Desktop ..."
    Start-Process -FilePath $exe
    $deadline = (Get-Date).AddMinutes(6)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        Write-Host '.' -NoNewline
        if (Test-Engine) { break }
    }
    Write-Host ''
    if (Test-Engine) { Ok "引擎已就绪" } else { Dead "等待超时：请在托盘里确认 Docker Desktop 已接受协议、鲸鱼图标为绿色"; exit 1 }
}

Write-Host "`n[3/4] 测试拉镜像（验证代理）" -ForegroundColor Cyan
$job = Start-Job { docker pull hello-world }
if (Wait-Job $job -Timeout 90) {
    $out = Receive-Job $job
    if ($job.State -eq 'Completed' -and ($out -join "`n") -match 'Status: Downloaded|Image is up to date') {
        Ok "镜像拉取正常"
        docker rmi hello-world *> $null
    } else {
        Warn "拉取异常，输出：" ; $out | Select-Object -Last 5 | ForEach-Object { Info $_ }
    }
} else {
    Stop-Job $job -ErrorAction SilentlyContinue
    Warn "拉取超时（90s）——基本可以确定是没走代理"
    Info "解决：Docker Desktop → Settings → Resources → Proxies → Manual → http://127.0.0.1:10808 → Apply & restart"
}
Remove-Job $job -Force -ErrorAction SilentlyContinue

if ($SkipCompose) {
    Write-Host "`n已跳过 compose（-SkipCompose）" -ForegroundColor Yellow
    exit 0
}

Write-Host "`n[4/4] 启动 MySQL / Redis" -ForegroundColor Cyan
if (-not (Test-Path (Join-Path $root '.env'))) {
    Copy-Item (Join-Path $root '.env.example') (Join-Path $root '.env')
    Info "已从 .env.example 生成 .env（密码是示例值，正式环境记得改）"
}
docker compose -f docker-compose.dev.yml up -d 2>&1 | ForEach-Object { "  $_" }

Info "等待健康检查 ..."
$deadline = (Get-Date).AddMinutes(3)
do {
    Start-Sleep -Seconds 5
    $ps = docker compose -f docker-compose.dev.yml ps --format json 2>$null
    $healthy = ($ps -join '') -match '"Health":"healthy"'
} while ((Get-Date) -lt $deadline -and -not $healthy)

Write-Host ''
docker compose -f docker-compose.dev.yml ps
Write-Host ""
if ($healthy) {
    Ok "MySQL / Redis 已就绪"
    Info "MySQL : mysql+pymysql://app:app_pass@127.0.0.1:3306/shopify_shopline?charset=utf8mb4"
    Info "Redis : redis://:redis_pass@127.0.0.1:6379/0"
} else {
    Warn "容器已创建但健康检查未通过，看日志：docker compose -f docker-compose.dev.yml logs -f"
}
Write-Host ""
