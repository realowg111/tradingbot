<#
.SYNOPSIS
    Script pour configurer Cloudflare Tunnel (expose le backend en HTTPS public)
    
.DESCRIPTION
    - Installe cloudflared
    - Configure le tunnel pour le backend
    - Crée une Scheduled Task pour auto-démarrage
    
.PARAMETER TunnelName
    Nom du tunnel Cloudflare
    
.EXAMPLE
    .\setup_cloudflare_tunnel.ps1 -TunnelName "trading-bot-tunnel"
#>

param(
    [string]$TunnelName = "trading-bot-tunnel"
)

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "🌐 Configuration Cloudflare Tunnel" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Vérifier droits admin
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "❌ Droits administrateur requis!" -ForegroundColor Red
    exit 1
}

# Installer cloudflared
Write-Host "📦 Installation de Cloudflare Tunnel..." -ForegroundColor Yellow

if (-NOT (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    choco install cloudflare-warp -y
    Write-Host "✅ Cloudflared installé" -ForegroundColor Green
} else {
    Write-Host "✅ Cloudflared déjà installé" -ForegroundColor Green
}

# Créer le fichier de configuration
Write-Host "
⚙️  Configuration du tunnel..." -ForegroundColor Yellow

$configDir = "C:\cloudflare"
if (-NOT (Test-Path $configDir)) {
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
}

$configFile = Join-Path $configDir "config.yml"

$configContent = @"
tunnel: $TunnelName
credentials-file: $configDir\cert.pem

ingress:
  - hostname: $TunnelName.trycloudflare.com
    service: http://localhost:8001
  - service: http_status:404
"@

Set-Content -Path $configFile -Value $configContent -Encoding UTF8
Write-Host "✅ Fichier de configuration créé: $configFile" -ForegroundColor Green

# Créer Scheduled Task pour le tunnel
Write-Host "
📅 Création Scheduled Task pour Cloudflare Tunnel..." -ForegroundColor Yellow

$taskName = "CloudflareTunnel"
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Write-Host "Suppression de la tâche existante..." -ForegroundColor Gray
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute "cloudflared.exe" `
    -Argument "tunnel run $TunnelName"

$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserID "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal

Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
Write-Host "✅ Scheduled Task créée: $taskName" -ForegroundColor Green

# Test du tunnel (optionnel)
Write-Host "
🧪 Tester le tunnel immédiatement? (Y/n):" -ForegroundColor Yellow
$testResponse = Read-Host

if ($testResponse -ne "n") {
    Write-Host "
⏳ Lancement du tunnel (Ctrl+C pour arrêter)..." -ForegroundColor Cyan
    & cloudflared.exe tunnel run $TunnelName
}

# Résumé
Write-Host "
" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Green
Write-Host "✅ CLOUDFLARE TUNNEL CONFIGURÉ!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "
📋 Résumé:" -ForegroundColor Cyan
Write-Host "  ✓ Cloudflared installé"
Write-Host "  ✓ Tunnel: $TunnelName"
Write-Host "  ✓ Configuration: $configFile"
Write-Host "  ✓ Auto-démarrage configuré"

Write-Host "
🌐 URL PUBLIQUE:" -ForegroundColor Green
Write-Host "  https://$TunnelName.trycloudflare.com" -ForegroundColor Cyan

Write-Host "
📝 À utiliser dans .env frontend:" -ForegroundColor Yellow
Write-Host "  EXPO_PUBLIC_BACKEND_URL=https://$TunnelName.trycloudflare.com" -ForegroundColor Cyan

Write-Host "
⚠️  NOTES:" -ForegroundColor Yellow
Write-Host "  • L'URL change à chaque redémarrage (tunnel quick)"
Write-Host "  • Pour une URL fixe, migrer vers Named Tunnel (domaine requis)"
Write-Host "  • Vérifier la Scheduled Task: Get-ScheduledTask -TaskName 'CloudflareTunnel'"

Write-Host "
"
