# ============================================================================
# Trading Bot - Affiche l'URL actuelle du tunnel Cloudflare
# ============================================================================
# Cherche dans cloudflared.log la derniere URL publique HTTPS
# attribuee par trycloudflare.com
#
# USAGE :
#   cd C:\trading-bot
#   .\scripts\vps_windows\get_tunnel_url.ps1
# ============================================================================

$LogFile = "C:\trading-bot\logs\cloudflared.log"

if (-not (Test-Path $LogFile)) {
    Write-Host "[X] Log cloudflared introuvable : $LogFile" -ForegroundColor Red
    Write-Host "    Verifie que le tunnel est demarre : Get-Service TradingBotTunnel" -ForegroundColor Yellow
    exit 1
}

$content = Get-Content $LogFile -Raw
$urls = [regex]::Matches($content, "https://[a-z0-9-]+\.trycloudflare\.com") | ForEach-Object { $_.Value } | Select-Object -Unique
$lastUrl = $urls | Select-Object -Last 1

if (-not $lastUrl) {
    Write-Host "[X] Aucune URL Cloudflare trouvee dans le log." -ForegroundColor Red
    Write-Host "    Le tunnel n'a peut-etre pas encore demarre. Attends 30 secondes et reessaye." -ForegroundColor Yellow
    Write-Host "    Ou regarde les logs en direct : Get-Content $LogFile -Tail 50 -Wait" -ForegroundColor Gray
    exit 1
}

# Test si l'URL repond
Write-Host ""
Write-Host "==> URL du tunnel Cloudflare detectee :" -ForegroundColor Cyan
Write-Host ""
Write-Host "    $lastUrl" -ForegroundColor Green
Write-Host ""
Write-Host "==> Test de connectivite..." -ForegroundColor Cyan

try {
    $r = Invoke-WebRequest -Uri "$lastUrl/api/health" -UseBasicParsing -TimeoutSec 8
    Write-Host "    [OK] Backend repond ! HTTP $($r.StatusCode)" -ForegroundColor Green
    Write-Host ""
    Write-Host "==> Copie cette URL dans l'app :" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "    1. Ouvre l'app -> Plus -> Reglages" -ForegroundColor White
    Write-Host "    2. Colle l'URL :" -ForegroundColor White
    Write-Host "       $lastUrl" -ForegroundColor Cyan
    Write-Host "    3. Clique 'Tester' puis 'Sauvegarder'" -ForegroundColor White
    Write-Host "    4. Recharge l'app (Cmd+R ou ferme/rouvre)" -ForegroundColor White
} catch {
    Write-Host "    [!] L'URL existe mais le backend ne repond pas." -ForegroundColor Yellow
    Write-Host "        Erreur: $($_.Exception.Message)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "    Verifie que le backend tourne : Get-Process python*" -ForegroundColor Yellow
    Write-Host "    Ou relance le tunnel : Restart-Service TradingBotTunnel" -ForegroundColor Yellow
}

Write-Host ""
# Copy to clipboard for convenience
try {
    $lastUrl | Set-Clipboard
    Write-Host "[BONUS] URL copiee dans le presse-papier (Ctrl+V pour coller)" -ForegroundColor Magenta
} catch {}
Write-Host ""
