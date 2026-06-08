# ============================================================================
# Trading Bot - Auto-update quotidien (Windows Scheduled Task)
# ============================================================================
# Ce script pulle la derniere version du code via git et redemarre le service.
# A executer chaque jour via Windows Task Scheduler.
#
# INSTALLATION (PowerShell admin sur le VPS Windows) :
#   $action = New-ScheduledTaskAction -Execute "PowerShell.exe" `
#       -Argument "-ExecutionPolicy Bypass -File C:\trading-bot\scripts\vps_windows\auto_update.ps1"
#   $trigger = New-ScheduledTaskTrigger -Daily -At 5:00am
#   $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
#   Register-ScheduledTask -TaskName "TradingBotAutoUpdate" -Action $action -Trigger $trigger -Principal $principal
# ============================================================================

$ErrorActionPreference = "Stop"
$AppDir = "C:\trading-bot"
$LogFile = "$AppDir\logs\auto_update.log"

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "[$ts] $msg"
}

try {
    Write-Log "===== Auto-update demarre ====="

    Set-Location $AppDir

    # 1. Pull latest code
    $before = git rev-parse HEAD
    git fetch
    git pull --ff-only
    $after = git rev-parse HEAD

    if ($before -eq $after) {
        Write-Log "Aucune mise a jour disponible."
        exit 0
    }

    Write-Log "Mise a jour : $before -> $after"

    # 2. Update Python deps (pip-sync) if requirements changed
    $requirementsChanged = git diff --name-only $before $after | Select-String "requirements.txt"
    if ($requirementsChanged) {
        Write-Log "requirements.txt change, mise a jour des deps..."
        & "$AppDir\venv\Scripts\pip.exe" install -r "$AppDir\backend\requirements.txt" --upgrade
    }

    # 3. Restart backend service
    Write-Log "Redemarrage TradingBotBackend..."
    Restart-Service -Name TradingBotBackend -Force

    # 4. Health check apres restart (5 tentatives, 5s entre chaque)
    Start-Sleep -Seconds 5
    $ok = $false
    for ($i = 1; $i -le 5; $i++) {
        try {
            $res = Invoke-WebRequest -Uri "http://localhost:8001/api/health" -UseBasicParsing -TimeoutSec 5
            if ($res.StatusCode -eq 200) {
                Write-Log "Health check OK (tentative $i)"
                $ok = $true
                break
            }
        } catch {
            Write-Log "Tentative $i failed: $($_.Exception.Message)"
            Start-Sleep -Seconds 5
        }
    }

    if (-not $ok) {
        Write-Log "ECHEC: backend ne repond pas apres update. Rollback..."
        git reset --hard $before
        Restart-Service -Name TradingBotBackend -Force
        Write-Log "Rollback effectue vers $before"
        exit 1
    }

    Write-Log "===== Auto-update reussi ====="
} catch {
    Write-Log "EXCEPTION: $($_.Exception.Message)"
    exit 1
}
