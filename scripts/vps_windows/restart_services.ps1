<#
.SYNOPSIS
    Script pour redémarrer tous les services du Trading Bot
    
.DESCRIPTION
    Redémarre MongoDB, Backend FastAPI et Cloudflare Tunnel
#>

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "🔄 Redémarrage des services" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Vérifier droits admin
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "❌ Droits administrateur requis!" -ForegroundColor Red
    exit 1
}

$services = @("MongoDB", "TradingBotBackend", "MT5AutoStart")

foreach ($service in $services) {
    $svc = Get-Service $service -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Host "🔄 Redémarrage de $service..." -ForegroundColor Yellow
        Restart-Service -Name $service -Force
        Start-Sleep -Seconds 2
        $state = (Get-Service $service).Status
        Write-Host "✅ $service - $state" -ForegroundColor Green
    }
}

Write-Host "
✅ Services redémarrés" -ForegroundColor Green
Write-Host "
"
