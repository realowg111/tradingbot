<#
.SYNOPSIS
    Script pour vérifier l'état de tous les services et connexions
    
.DESCRIPTION
    - État des services Windows
    - Tests de connectivité
    - État de MongoDB
    - État du Backend API
#>

$ErrorActionPreference = "Continue"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "📊 État du Trading Bot" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# État des services
Write-Host "🔧 État des services Windows:" -ForegroundColor Cyan
$services = @("MongoDB", "TradingBotBackend", "MT5AutoStart")

foreach ($service in $services) {
    $svc = Get-Service $service -ErrorAction SilentlyContinue
    if ($svc) {
        $status = $svc.Status
        $color = if ($status -eq "Running") { "Green" } else { "Red" }
        Write-Host "  $service: $status" -ForegroundColor $color
    } else {
        Write-Host "  $service: NON INSTALLÉ" -ForegroundColor Yellow
    }
}

# Test MongoDB
Write-Host "
🗄️  Test MongoDB:" -ForegroundColor Cyan
try {
    $client = New-Object System.Data.MongoDb.MongoClient("mongodb://localhost:27017")
    $db = $client.GetDatabase("admin")
    $db.RunCommandAsync([System.Collections.Generic.Dictionary[string, object]]@{ping = 1}).Result | Out-Null
    Write-Host "  ✅ MongoDB accessible" -ForegroundColor Green
} catch {
    Write-Host "  ❌ MongoDB indisponible" -ForegroundColor Red
}

# Test Backend API
Write-Host "
⚡ Test Backend API:" -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8001/api/health" -UseBasicParsing -TimeoutSec 5
    if ($response.StatusCode -eq 200) {
        Write-Host "  ✅ Backend répond (status: 200)" -ForegroundColor Green
        $data = $response.Content | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($data) {
            Write-Host "    Réponse: $($data | ConvertTo-Json -Depth 2)" -ForegroundColor Gray
        }
    }
} catch {
    Write-Host "  ⚠️  Backend indisponible: $($_.Exception.Message)" -ForegroundColor Yellow
}

# Test MT5 Terminal
Write-Host "
📊 Test MT5 Terminal:" -ForegroundColor Cyan
$mt5Process = Get-Process terminal64 -ErrorAction SilentlyContinue
if ($mt5Process) {
    Write-Host "  ✅ Terminal MT5 en cours d'exécution" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  Terminal MT5 pas trouvé (lancer manuellement)" -ForegroundColor Yellow
}

# Logs récents
Write-Host "
📝 Logs récents (backend):" -ForegroundColor Cyan
$logPath = "C:\tradingbot\logs\backend_stderr.log"
if (Test-Path $logPath) {
    Write-Host "  Dernières 10 lignes:" -ForegroundColor Gray
    Get-Content $logPath -Tail 10 | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
} else {
    Write-Host "  Fichier log non trouvé" -ForegroundColor Yellow
}

Write-Host "
============================================" -ForegroundColor Cyan
Write-Host "
"
