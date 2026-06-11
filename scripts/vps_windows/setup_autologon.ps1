# ============================================================
# setup_autologon.ps1 — Autonomie 100% apres reboot du VPS
# ============================================================
# Ce script configure :
#  1. AutoLogon Windows : la session s'ouvre toute seule au boot
#     -> la tache planifiee TradingBotBackend demarre automatiquement
#     -> le tunnel Cloudflare (service) demarre deja tout seul au boot
#  2. La tache TradingBotBackend pour redemarrer en cas de crash
#
# Usage (PowerShell EN ADMINISTRATEUR) :
#   C:\trading-bot\scripts\vps_windows\setup_autologon.ps1
# ============================================================

$ErrorActionPreference = "Stop"

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function OK($msg) { Write-Host "  [OK] $msg" -ForegroundColor Green }

# --- Verification admin ---
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "ERREUR: Lancez PowerShell en tant qu'ADMINISTRATEUR." -ForegroundColor Red
    exit 1
}

# --- 1. AutoLogon ---
Step "Configuration de l'AutoLogon Windows..."
$username = $env:USERNAME
$domain = $env:USERDOMAIN
Write-Host "  Compte detecte : $domain\$username"
$password = Read-Host "  Mot de passe Windows de ce compte (pour l'auto-connexion au boot)" -AsSecureString
$plainPwd = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($password))

$winlogon = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
Set-ItemProperty -Path $winlogon -Name "AutoAdminLogon" -Value "1" -Type String
Set-ItemProperty -Path $winlogon -Name "DefaultUserName" -Value $username -Type String
Set-ItemProperty -Path $winlogon -Name "DefaultDomainName" -Value $domain -Type String
Set-ItemProperty -Path $winlogon -Name "DefaultPassword" -Value $plainPwd -Type String
Remove-ItemProperty -Path $winlogon -Name "AutoLogonCount" -ErrorAction SilentlyContinue
OK "AutoLogon active pour $domain\$username"

# --- 2. Resilience de la tache backend ---
Step "Configuration du redemarrage automatique de la tache TradingBotBackend..."
$task = Get-ScheduledTask -TaskName "TradingBotBackend" -ErrorAction SilentlyContinue
if ($task) {
    $settings = New-ScheduledTaskSettingsSet `
        -RestartCount 99 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable
    Set-ScheduledTask -TaskName "TradingBotBackend" -Settings $settings | Out-Null
    OK "La tache redemarre automatiquement en cas de crash (99 tentatives, 1 min d'intervalle)"
} else {
    Write-Host "  [!] Tache TradingBotBackend introuvable (lancez migrate_to_task.ps1 d'abord)" -ForegroundColor Yellow
}

# --- 3. Verification du service tunnel ---
Step "Verification du tunnel Cloudflare..."
$tunnel = Get-Service -Name "TradingBotTunnel" -ErrorAction SilentlyContinue
if ($tunnel) {
    Set-Service -Name "TradingBotTunnel" -StartupType Automatic
    OK "Service tunnel en demarrage automatique ($($tunnel.Status))"
    Write-Host "  [!] Rappel: l'URL du quick tunnel CHANGE apres un redemarrage de cloudflared." -ForegroundColor Yellow
} else {
    Write-Host "  [!] Service TradingBotTunnel introuvable" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host " AUTONOMIE CONFIGUREE !" -ForegroundColor Green
Write-Host " Au prochain reboot du VPS :" -ForegroundColor Green
Write-Host "  1. Windows se connecte tout seul" -ForegroundColor Gray
Write-Host "  2. Le backend demarre (tache planifiee)" -ForegroundColor Gray
Write-Host "  3. MT5 se reconnecte automatiquement (~60s)" -ForegroundColor Gray
Write-Host "  4. Le tunnel demarre (service Windows)" -ForegroundColor Gray
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Test conseille : Restart-Computer puis verifier l'app dans 2-3 minutes." -ForegroundColor Cyan
