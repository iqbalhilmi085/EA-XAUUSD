#Requires -Version 5.1
<#
.SYNOPSIS
  Set environment variables Vercel untuk bot XAUUSD.

.DESCRIPTION
  Jalankan setelah:
    npx vercel login
    npx vercel link

  Script membaca TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID dari telegram.json,
  membuat SCAN_SECRET / TELEGRAM_WEBHOOK_SECRET / CRON_SECRET secara acak,
  lalu mengirimkannya ke environment `production` project Vercel yang sedang
  di-link.

  Nilai secret yang dibuat juga disimpan ke .vercel-env.local.json
  (sudah di-.gitignore) supaya kamu bisa memakai SCAN_SECRET untuk cron URL.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File deploy/vercel/setup_env.ps1
#>

$ErrorActionPreference = 'Stop'

$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $root

if (-not (Test-Path 'telegram.json')) {
    throw 'telegram.json tidak ditemukan di root project.'
}
if (-not (Test-Path '.vercel\project.json')) {
    throw 'Project belum di-link. Jalankan dulu: npx vercel link'
}

$cfg = Get-Content 'telegram.json' -Raw | ConvertFrom-Json
$token = [string]$cfg.bot_token
$chat = [string]$cfg.chat_id

if (-not $token -or $token -match 'PASTE|CONTOH') {
    throw 'bot_token kosong di telegram.json.'
}
if (-not $chat -or $chat -match 'PASTE') {
    throw 'chat_id kosong di telegram.json.'
}

function New-Secret {
    python -c "import secrets; print(secrets.token_urlsafe(32))"
}

$scan = if ($env:SCAN_SECRET) { $env:SCAN_SECRET } else { New-Secret }
$hook = if ($env:TELEGRAM_WEBHOOK_SECRET) { $env:TELEGRAM_WEBHOOK_SECRET } else { New-Secret }
$cron = if ($env:CRON_SECRET) { $env:CRON_SECRET } else { New-Secret }

$vars = [ordered]@{
    TELEGRAM_BOT_TOKEN        = $token
    TELEGRAM_CHAT_ID          = $chat
    TELEGRAM_ALLOWED_CHAT_IDS = $chat
    TELEGRAM_WEBHOOK_SECRET   = $hook
    SCAN_SECRET               = $scan
    CRON_SECRET               = $cron
    SYMBOL                    = 'XAUUSD'
    BACKEND                   = 'paper'
    DEFAULT_MODE              = 'semi'
}

Write-Host 'Mengirim environment variables ke Vercel...' -ForegroundColor Cyan

foreach ($name in $vars.Keys) {
    $value = [string]$vars[$name]
    $value | npx --yes vercel@latest env add $name --environment production --force --yes 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Gagal set $name (exit $LASTEXITCODE). Pastikan sudah login dan link."
    }
    Write-Host "  OK  $name" -ForegroundColor Green
}

$secrets = [ordered]@{
    SCAN_SECRET             = $scan
    TELEGRAM_WEBHOOK_SECRET = $hook
    CRON_SECRET             = $cron
}
$secrets | ConvertTo-Json | Out-File -Encoding utf8 '.vercel-env.local.json'

Write-Host ''
Write-Host 'Selesai. Secret lokal disimpan di .vercel-env.local.json' -ForegroundColor Cyan
Write-Host "SCAN_SECRET = $scan" -ForegroundColor Yellow
Write-Host ''
Write-Host 'Langkah berikutnya:' -ForegroundColor Cyan
Write-Host '  1. npx vercel --prod'
Write-Host '  2. python deploy/vercel/setup_webhook.py --url https://<project>.vercel.app'
