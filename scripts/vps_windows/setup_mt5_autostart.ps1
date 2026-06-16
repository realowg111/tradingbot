# ============================================================================
# Trading Bot - Setup auto-start de MetaTrader 5 au demarrage Windows
# ============================================================================
# Configure 3 choses :
#   1. MT5 demarre automatiquement quand Windows boote (Scheduled Task)
#   2. MT5 redemarre automatiquement si il crash (avec un watchdog leger)
#   3. La fenetre MT5 est minimisee pour ne pas geler l'interactivite
#
# UTILISATION :
#   1. Ouvre PowerShell EN ADMINISTRATEUR sur ton VPS
#   2. Lance : powershell -ExecutionPolicy Bypass -File C:\trading-bot\scripts\vps_windows\setup_mt5_autostart.ps1
# ============================================================================

$ErrorActionPreference = "Stop"
$TaskName = "TradingBot-MT5-AutoStart"
$WatchdogTaskName = "TradingBot-MT5-Watchdog"
$LogFile = "C:\trading-bot\mt5_watchdog.log"

# Possible MT5 install paths (broker-specific)
$PossiblePaths = @(
    "C:\Program Files\MetaTrader 5\terminal64.exe",
    "C:\Program Files\MetaTrader 5 IC Markets Global\terminal64.exe",
    "C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
    "C:\Program Files\FBS - MetaTrader 5\terminal64.exe",
    "C:\Program Files\Exness MetaTrader 5\terminal64.exe",
    "C:\Program Files\XM MT5\terminal64.exe",
    "$env:APPDATA\MetaQuotes\Terminal\*\terminal64.exe"
)

function Find-MT5 {
    foreach ($p in $PossiblePaths) {
        $resolved = Get-ChildItem -Path $p -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($resolved) { return $resolved.FullName }
    }
    # Fallback : look at any terminal64.exe in Program Files
    $hit = Get-ChildItem -Path "C:\Program Files\","C:\Program Files (x86)\" -Filter "terminal64.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { return $hit.FullName }
    return $null
}

Write-Host "=============================================================" -ForegroundColor Magenta
Write-Host "  TRADING BOT - Auto-start MT5 au boot" -ForegroundColor Magenta
Write-Host "=============================================================" -ForegroundColor Magenta

# --- Detection MT5 ---
$Mt5Path = Find-MT5
if (-not $Mt5Path) {
    Write-Host "`nERREUR : MetaTrader 5 introuvable." -ForegroundColor Red
    Write-Host "Reponds a cette question manuellement :" -ForegroundColor Yellow
    $Mt5Path = Read-Host "Chemin complet vers terminal64.exe (ex: C:\Program Files\MetaTrader 5\terminal64.exe)"
    if (-not (Test-Path $Mt5Path)) {
        throw "Chemin invalide : $Mt5Path"
    }
}
Write-Host "`n[OK] MT5 detecte : $Mt5Path" -ForegroundColor Green

# --- 1. Task : MT5 au boot (au logon car MT5 a besoin d'une session interactive) ---
Write-Host "`n[1/2] Creation de la tache 'demarrage MT5 au logon'..." -ForegroundColor Cyan
schtasks /Delete /TN $TaskName /F 2>&1 | Out-Null

$action = New-ScheduledTaskAction -Execute $Mt5Path
$trigger = New-ScheduledTaskTrigger -AtLogon
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
Write-Host "    [OK] Tache '$TaskName' creee. MT5 demarrera au prochain logon Windows." -ForegroundColor Green

# --- 2. Watchdog : verifie toutes les 5 minutes que MT5 tourne, sinon le relance ---
Write-Host "`n[2/2] Creation du watchdog (relance auto si MT5 crash)..." -ForegroundColor Cyan
$WatchdogScript = @"
`$ErrorActionPreference = "SilentlyContinue"
`$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
`$proc = Get-Process terminal64 -ErrorAction SilentlyContinue
if (`$null -eq `$proc) {
    Add-Content -Path "$LogFile" -Value "[`$ts] MT5 absent -> relance"
    Start-Process -FilePath "$Mt5Path" -WindowStyle Minimized
} else {
    Add-Content -Path "$LogFile" -Value "[`$ts] MT5 OK (PID=`$(`$proc.Id))"
}
"@
$WatchdogScriptPath = "C:\trading-bot\scripts\vps_windows\mt5_watchdog.ps1"
Set-Content -Path $WatchdogScriptPath -Value $WatchdogScript -Encoding UTF8

schtasks /Delete /TN $WatchdogTaskName /F 2>&1 | Out-Null
$wdAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WatchdogScriptPath`""
$wdTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$wdPrincipal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Highest
$wdSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $WatchdogTaskName -Action $wdAction -Trigger $wdTrigger -Principal $wdPrincipal -Settings $wdSettings | Out-Null
Write-Host "    [OK] Watchdog '$WatchdogTaskName' actif (check toutes les 5 min)" -ForegroundColor Green

# --- Lance MT5 maintenant si pas deja en cours ---
$running = Get-Process terminal64 -ErrorAction SilentlyContinue
if ($null -eq $running) {
    Write-Host "`n[BONUS] Demarrage de MT5 maintenant..." -ForegroundColor Cyan
    Start-Process -FilePath $Mt5Path -WindowStyle Minimized
    Start-Sleep -Seconds 5
    Write-Host "    [OK] MT5 lance" -ForegroundColor Green
} else {
    Write-Host "`n[INFO] MT5 deja en cours (PID=$($running.Id))" -ForegroundColor Yellow
}

Write-Host "`n=============================================================" -ForegroundColor Green
Write-Host "  INSTALLATION AUTOSTART TERMINEE" -ForegroundColor Green
Write-Host "=============================================================" -ForegroundColor Green
Write-Host "`nResume :" -ForegroundColor White
Write-Host "  - Au boot du VPS Windows : AutoLogon (deja configure) -> MT5 demarre auto -> Bot Python se reconnecte automatiquement (toutes les 10s)" -ForegroundColor White
Write-Host "  - Si MT5 crash : watchdog le relance dans les 5 min maximum" -ForegroundColor White
Write-Host "  - Logs watchdog : $LogFile" -ForegroundColor White
Write-Host "`nTu peux fermer le RDP sereinement : tout tourne en arriere-plan." -ForegroundColor Yellow
Write-Host ""
