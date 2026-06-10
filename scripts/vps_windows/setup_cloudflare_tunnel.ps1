# ============================================================================
# Trading Bot - Configuration Cloudflare Tunnel
# ============================================================================
# Expose le backend (http://localhost:8001) sur une URL HTTPS publique.
# Resout le probleme de Mixed Content (HTTPS frontend vs HTTP backend).
#
# USAGE (PowerShell ADMIN sur le VPS) :
#   Set-ExecutionPolicy Bypass -Scope Process -Force
#   C:\trading-bot\scripts\vps_windows\setup_cloudflare_tunnel.ps1
#
# Ou en one-liner depuis n'importe ou :
#   iex (Get-Content C:\trading-bot\scripts\vps_windows\setup_cloudflare_tunnel.ps1 -Raw)
# ============================================================================

$ErrorActionPreference = "Stop"

function Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function OK($msg)   { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    [!]  $msg" -ForegroundColor Yellow }
function Die($msg)  { Write-Host "    [X]  $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "+---------------------------------------------+" -ForegroundColor Cyan
Write-Host "|   Cloudflare Tunnel - Setup HTTPS public    |" -ForegroundColor Cyan
Write-Host "+---------------------------------------------+" -ForegroundColor Cyan

# --- Admin check ---
$current = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal $current).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Die "Lance PowerShell EN ADMINISTRATEUR (clic droit -> Run as Administrator)"
}
OK "Mode administrateur OK"

$AppDir = "C:\trading-bot"
$CloudflaredExe = "$AppDir\cloudflared.exe"
$LogDir = "$AppDir\logs"
$LogFile = "$LogDir\cloudflared.log"
$ServiceName = "TradingBotTunnel"
$BackendPort = 8001

if (-not (Test-Path $AppDir)) { New-Item -ItemType Directory -Path $AppDir -Force | Out-Null }
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

# --- Telecharger cloudflared ---
Step "Verification de cloudflared.exe..."
if (-not (Test-Path $CloudflaredExe)) {
    Step "Telechargement de cloudflared (Cloudflare Tunnel client)..."
    $url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    try {
        Invoke-WebRequest -Uri $url -OutFile $CloudflaredExe -UseBasicParsing
        OK "cloudflared telecharge dans $CloudflaredExe"
    } catch {
        Die "Echec du telechargement de cloudflared : $($_.Exception.Message)"
    }
} else {
    OK "cloudflared deja present"
}

# --- Verifier NSSM (deja installe par install.ps1) ---
Step "Verification de NSSM (service manager)..."
$nssm = Get-Command nssm -ErrorAction SilentlyContinue
if (-not $nssm) {
    # Tenter d'installer via chocolatey
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        Warn "NSSM introuvable, installation via chocolatey..."
        choco install -y nssm --no-progress | Out-Null
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    } else {
        Die "NSSM introuvable et chocolatey absent. Lance d'abord install.ps1"
    }
}
OK "NSSM disponible"

# --- Stop / Remove service existant ---
Step "Nettoyage de l'ancien service tunnel s'il existe..."
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Status -eq 'Running') {
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
    nssm remove $ServiceName confirm | Out-Null
    Start-Sleep -Seconds 2
    OK "Ancien service supprime"
} else {
    OK "Pas d'ancien service"
}

# Reset log file
if (Test-Path $LogFile) { Remove-Item $LogFile -Force }
New-Item -ItemType File -Path $LogFile -Force | Out-Null

# --- Installer le service NSSM ---
Step "Installation du service Windows $ServiceName..."
nssm install $ServiceName $CloudflaredExe "tunnel --no-autoupdate --url http://localhost:$BackendPort" | Out-Null
nssm set $ServiceName DisplayName "Trading Bot - Cloudflare Tunnel" | Out-Null
nssm set $ServiceName Description "Expose le backend FastAPI en HTTPS via Cloudflare Quick Tunnel" | Out-Null
nssm set $ServiceName Start SERVICE_AUTO_START | Out-Null
nssm set $ServiceName AppStdout $LogFile | Out-Null
nssm set $ServiceName AppStderr $LogFile | Out-Null
nssm set $ServiceName AppRotateFiles 1 | Out-Null
nssm set $ServiceName AppRotateBytes 5242880 | Out-Null
nssm set $ServiceName AppRestartDelay 5000 | Out-Null
OK "Service installe"

# --- Demarrer le service ---
Step "Demarrage du tunnel..."
Start-Service -Name $ServiceName
Start-Sleep -Seconds 5
OK "Service demarre"

# --- Recuperer l'URL publique ---
Step "Recuperation de l'URL HTTPS publique..."
$publicUrl = $null
$maxTries = 30
for ($i = 1; $i -le $maxTries; $i++) {
    Start-Sleep -Seconds 2
    if (Test-Path $LogFile) {
        $content = Get-Content $LogFile -Raw -ErrorAction SilentlyContinue
        if ($content -and $content -match "(https://[a-z0-9-]+\.trycloudflare\.com)") {
            $publicUrl = $matches[1]
            break
        }
    }
    Write-Host "    ... attente du tunnel ($i/$maxTries)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "+---------------------------------------------+" -ForegroundColor Green
if ($publicUrl) {
    Write-Host "|       TUNNEL ACTIF !                        |" -ForegroundColor Green
    Write-Host "+---------------------------------------------+" -ForegroundColor Green
    Write-Host ""
    Write-Host "URL PUBLIQUE HTTPS DU BACKEND :" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  $publicUrl" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "TEST RAPIDE :" -ForegroundColor Yellow
    Write-Host "  Invoke-WebRequest $publicUrl/api/health | Select-Object -ExpandProperty Content" -ForegroundColor Gray
    Write-Host ""
    Write-Host "COPIE CETTE URL ET ENVOIE-LA A L'AGENT EMERGENT" -ForegroundColor Magenta
    Write-Host "pour qu'il configure le frontend." -ForegroundColor Magenta
    Write-Host ""

    # Tester l'URL
    Step "Test de l'URL..."
    try {
        $response = Invoke-WebRequest -Uri "$publicUrl/api/health" -UseBasicParsing -TimeoutSec 10
        OK "API repond ! Status: $($response.StatusCode)"
    } catch {
        Warn "L'URL ne repond pas encore (peut prendre 30s). Re-essaye dans 1 minute."
    }
} else {
    Write-Host "|       URL NON TROUVEE                       |" -ForegroundColor Red
    Write-Host "+---------------------------------------------+" -ForegroundColor Red
    Write-Host ""
    Warn "Le tunnel a peut-etre demarre mais l'URL n'a pas ete capturee."
    Warn "Verifie les logs : Get-Content $LogFile -Tail 50"
    Write-Host ""
}

Write-Host "GESTION DU TUNNEL :" -ForegroundColor Cyan
Write-Host "  Statut    : Get-Service $ServiceName" -ForegroundColor Gray
Write-Host "  Redemarrer: Restart-Service $ServiceName" -ForegroundColor Gray
Write-Host "  Logs      : Get-Content $LogFile -Tail 50 -Wait" -ForegroundColor Gray
Write-Host "  Arreter   : Stop-Service $ServiceName" -ForegroundColor Gray
Write-Host ""
Write-Host "NOTE : L'URL change si le service redemarre (Quick Tunnel gratuit)." -ForegroundColor Yellow
Write-Host "       Pour une URL fixe, il faut un compte Cloudflare + domaine." -ForegroundColor Yellow
Write-Host ""
