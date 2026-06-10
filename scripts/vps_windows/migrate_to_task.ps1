# ============================================================================
# Trading Bot - Migration Service Windows -> Tache planifiee (interactive)
# ============================================================================
# Resout l'erreur "IPC timeout" entre le backend et MT5.
#
# Raison : un service Windows tourne en session 0 (non-interactive), MT5
# tourne dans votre session utilisateur. Les pipes IPC de MT5 sont locales
# a la session => impossible de communiquer.
#
# Solution : remplacer le service par une Scheduled Task qui demarre le
# backend a l'ouverture de session, DANS votre session interactive
# (= meme session que MT5).
#
# USAGE (PowerShell ADMIN sur le VPS) :
#   cd C:\trading-bot
#   git pull
#   Set-ExecutionPolicy Bypass -Scope Process -Force
#   .\scripts\vps_windows\migrate_to_task.ps1
# ============================================================================

$ErrorActionPreference = "Stop"

function Step($msg)  { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function OK($msg)    { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "    [!]  $msg" -ForegroundColor Yellow }
function Die($msg)   { Write-Host "    [X]  $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "+------------------------------------------------+" -ForegroundColor Cyan
Write-Host "|  Migration Backend : Service -> Scheduled Task |" -ForegroundColor Cyan
Write-Host "+------------------------------------------------+" -ForegroundColor Cyan

# --- Admin check ---
$current = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal $current).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Die "Lance PowerShell EN ADMINISTRATEUR" }
OK "Mode administrateur OK"

$AppDir       = "C:\trading-bot"
$BackendDir   = "$AppDir\backend"
$LogDir       = "$AppDir\logs"
$VenvPython   = "$BackendDir\venv\Scripts\python.exe"
$Uvicorn      = "$BackendDir\venv\Scripts\uvicorn.exe"
$ServiceName  = "TradingBotBackend"
$TaskName     = "TradingBotBackend"
$LauncherBat  = "$AppDir\scripts\vps_windows\run_backend_interactive.bat"

if (-not (Test-Path $BackendDir))  { Die "Dossier backend introuvable : $BackendDir" }
if (-not (Test-Path $VenvPython))  { Die "venv Python introuvable : $VenvPython" }
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

$UserName = "$env:USERDOMAIN\$env:USERNAME"
OK "Compte utilisateur cible : $UserName"

# --- 1) Arret et suppression du service existant ---
Step "1/5 - Arret et suppression du service Windows existant..."
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc) {
    try {
        if ($svc.Status -eq 'Running') {
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 3
        }
        $nssm = Get-Command nssm -ErrorAction SilentlyContinue
        if ($nssm) {
            nssm remove $ServiceName confirm | Out-Null
        } else {
            sc.exe delete $ServiceName | Out-Null
        }
        Start-Sleep -Seconds 2
        OK "Service supprime"
    } catch {
        Warn "Echec suppression service: $($_.Exception.Message). On continue..."
    }
} else {
    OK "Aucun service existant"
}

# --- 2) Suppression ancienne Scheduled Task si presente ---
Step "2/5 - Nettoyage ancienne tache planifiee..."
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    OK "Ancienne tache supprimee"
} else {
    OK "Pas d'ancienne tache"
}

# --- 3) Generation du launcher BAT ---
Step "3/5 - Generation du script de lancement..."
$batContent = @"
@echo off
REM Trading Bot - Launcher (interactive session)
cd /d $BackendDir
set PYTHONUNBUFFERED=1
"$Uvicorn" server:app --host 0.0.0.0 --port 8001 > "$LogDir\backend.log" 2>&1
"@
$batDir = Split-Path $LauncherBat -Parent
if (-not (Test-Path $batDir)) { New-Item -ItemType Directory -Path $batDir -Force | Out-Null }
Set-Content -Path $LauncherBat -Value $batContent -Encoding ASCII
OK "Launcher cree : $LauncherBat"

# --- 4) Creation de la tache planifiee (interactive) ---
Step "4/5 - Creation de la Scheduled Task interactive..."

# Trigger : a l'ouverture de session de l'utilisateur courant
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserName

# Action : lancer le BAT
$action = New-ScheduledTaskAction -Execute $LauncherBat -WorkingDirectory $BackendDir

# Principal : tourner sous l'utilisateur courant, INTERACTIF (session 1+),
# avec privileges admin pour pouvoir binder le port 8001
$principal = New-ScheduledTaskPrincipal -UserId $UserName -LogonType Interactive -RunLevel Highest

# Settings : auto-restart, sans timeout
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName `
    -Description "Trading Bot Backend (FastAPI) - runs in interactive session for MT5 IPC" `
    -Trigger $trigger -Action $action -Principal $principal -Settings $settings `
    -Force | Out-Null
OK "Tache planifiee creee"

# --- 5) Demarrage immediat ---
Step "5/5 - Demarrage immediat de la tache..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 5

# Verifier qu'uvicorn ecoute bien
$listening = $false
for ($i = 1; $i -le 10; $i++) {
    try {
        $r = Invoke-WebRequest "http://localhost:8001/api/health" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $listening = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "+------------------------------------------------+" -ForegroundColor Green
if ($listening) {
    Write-Host "|             BACKEND OK SUR PORT 8001           |" -ForegroundColor Green
    Write-Host "+------------------------------------------------+" -ForegroundColor Green
    Write-Host ""
    OK "API repond : http://localhost:8001/api/health"
} else {
    Write-Host "|       BACKEND NON DEMARRE / EN COURS           |" -ForegroundColor Yellow
    Write-Host "+------------------------------------------------+" -ForegroundColor Yellow
    Write-Host ""
    Warn "L'API ne repond pas encore."
    Warn "Verifie les logs : Get-Content $LogDir\backend.log -Tail 50"
}

Write-Host ""
Write-Host "PROCHAINE ETAPE CRITIQUE :" -ForegroundColor Yellow
Write-Host "  1. Ouvre MT5 manuellement, log-toi sur RoboForex" -ForegroundColor Gray
Write-Host "  2. Attends que MT5 affiche 'Connecte : XX ms' en bas" -ForegroundColor Gray
Write-Host "  3. Dans l'app : Plus -> Connexion MT5 -> 'Connecter a MT5'" -ForegroundColor Gray
Write-Host ""
Write-Host "GESTION DE LA TACHE :" -ForegroundColor Cyan
Write-Host "  Statut    : Get-ScheduledTask -TaskName $TaskName" -ForegroundColor Gray
Write-Host "  Redemarre : Stop-ScheduledTask -TaskName $TaskName ; Start-ScheduledTask -TaskName $TaskName" -ForegroundColor Gray
Write-Host "  Logs      : Get-Content $LogDir\backend.log -Tail 50 -Wait" -ForegroundColor Gray
Write-Host ""
Write-Host "IMPORTANT : la tache ne demarre QUE quand votre user est connecte." -ForegroundColor Yellow
Write-Host "Si tu fais 'Deconnexion' RDP au lieu de fermer, la tache continue." -ForegroundColor Yellow
Write-Host ""
