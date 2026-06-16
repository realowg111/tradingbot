<#
.SYNOPSIS
    Script pour installer/configurer MT5 Terminal sur Windows VPS
    
.DESCRIPTION
    - Télécharge MT5 selon le broker spécifié
    - Lance le terminal au démarrage via Task Scheduler
    - Active AutoLogon Windows (pour session interactive)
    
.PARAMETER Broker
    Broker MT5: ICMarkets, RoboForex, ActivTrades, etc.
    
.EXAMPLE
    .\install_mt5_terminal.ps1 -Broker "RoboForex"
#>

param(
    [string]$Broker = "RoboForex"
)

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "📊 Installation MT5 Terminal" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Vérifier droits admin
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "❌ Ce script doit être exécuté en tant qu'administrateur!" -ForegroundColor Red
    exit 1
}

# URLs de téléchargement MT5 par broker
$brokerUrls = @{
    "RoboForex" = "https://download.roboforex.com/mt5/roboforex-mt5-setup.exe"
    "ICMarkets" = "https://download.icmarkets.com/mt5/icmarkets-mt5-setup.exe"
    "ActivTrades" = "https://download.activtrades.com/mt5/activtrades-mt5-setup.exe"
}

if (-NOT $brokerUrls.ContainsKey($Broker)) {
    Write-Host "❌ Broker non supporté. Disponibles: $(($brokerUrls.Keys -join ', '))" -ForegroundColor Red
    exit 1
}

$downloadUrl = $brokerUrls[$Broker]
Write-Host "🌐 Broker sélectionné: $Broker" -ForegroundColor Cyan

# Télécharger l'installeur
Write-Host "
📥 Téléchargement MT5..." -ForegroundColor Yellow
$installerPath = "C:\Temp\mt5-setup.exe"
if (-NOT (Test-Path "C:\Temp")) {
    New-Item -ItemType Directory -Path "C:\Temp" -Force | Out-Null
}

if (-NOT (Test-Path $installerPath)) {
    try {
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $downloadUrl -OutFile $installerPath
        Write-Host "✅ Téléchargement terminé" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  Téléchargement échoué. Télécharger manuellement:" -ForegroundColor Yellow
        Write-Host "  $downloadUrl" -ForegroundColor Cyan
        exit 1
    }
} else {
    Write-Host "✅ Installeur déjà présent" -ForegroundColor Green
}

# Installer silencieusement
Write-Host "
⚙️  Installation silencieuse MT5..." -ForegroundColor Yellow
& $installerPath /S | Out-Null
Write-Host "✅ MT5 Terminal installé" -ForegroundColor Green

# Attendre la finalisation
Start-Sleep -Seconds 5

# Trouver le répertoire d'installation
Write-Host "
🔍 Détection du répertoire MT5..." -ForegroundColor Yellow
$mt5Paths = @(
    "C:\Program Files\RoboForex - MetaTrader 5",
    "C:\Program Files\MetaTrader 5",
    "C:\Program Files\IC Markets\MetaTrader 5",
    "C:\Program Files (x86)\MetaTrader 5"
)

$mt5Path = $null
foreach ($path in $mt5Paths) {
    if (Test-Path "$path\terminal64.exe") {
        $mt5Path = $path
        break
    }
}

if (-NOT $mt5Path) {
    Write-Host "⚠️  MT5 terminal64.exe non trouvé. Recherche manuelle..." -ForegroundColor Yellow
    $mt5Path = Read-Host "Entrez le chemin complet vers le répertoire MT5"
}

Write-Host "✅ Chemin MT5 détecté: $mt5Path" -ForegroundColor Green

# Créer Scheduled Task pour lancer MT5 au démarrage
Write-Host "
📅 Création Scheduled Task pour auto-démarrage..." -ForegroundColor Yellow

$terminal64Exe = "$mt5Path\terminal64.exe"
$taskName = "MT5AutoStart"

# Supprimer la tâche existante
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "Suppression de la tâche existante..." -ForegroundColor Gray
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Créer une nouvelle tâche
$action = New-ScheduledTaskAction -Execute $terminal64Exe
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserID "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal

Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
Write-Host "✅ Scheduled Task créée: $taskName" -ForegroundColor Green

# Optionnel: AutoLogon Windows
Write-Host "
❓ Configurer AutoLogon Windows? (Y/n):" -ForegroundColor Yellow
$response = Read-Host

if ($response -ne "n") {
    Write-Host "
⚙️  Configuration AutoLogon..." -ForegroundColor Yellow
    Write-Host "Entrez vos identifiants Windows:" -ForegroundColor Cyan
    $username = Read-Host "Nom d'utilisateur"
    $password = Read-Host "Mot de passe" -AsSecureString
    $plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToCoTaskMemUnicode($password))
    
    # Configurer AutoLogon via Registry
    $regPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
    Set-ItemProperty -Path $regPath -Name "AutoAdminLogon" -Value "1"
    Set-ItemProperty -Path $regPath -Name "DefaultUsername" -Value $username
    Set-ItemProperty -Path $regPath -Name "DefaultPassword" -Value $plainPassword
    Set-ItemProperty -Path $regPath -Name "DefaultDomain" -Value $env:COMPUTERNAME
    
    Write-Host "✅ AutoLogon configuré" -ForegroundColor Green
}

# Résumé
Write-Host "
" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Green
Write-Host "✅ CONFIGURATION MT5 TERMINÉE!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "
📋 Résumé:" -ForegroundColor Cyan
Write-Host "  ✓ MT5 Terminal installé"
Write-Host "  ✓ Chemin: $mt5Path"
Write-Host "  ✓ Scheduled Task créée (démarrage automatique)"
if ($response -ne "n") {
    Write-Host "  ✓ AutoLogon Windows configuré"
}

Write-Host "
⚠️  PROCHAINES ÉTAPES:" -ForegroundColor Yellow
Write-Host "  1. Redémarrer le VPS"
Write-Host "  2. MT5 doit se lancer automatiquement"
Write-Host "  3. Connecter le compte (login/password)"
Write-Host "  4. LAISSER OUVERT (en arrière-plan)"
Write-Host "
📝 Vérifier la Scheduled Task:" -ForegroundColor Green
Write-Host "  Get-ScheduledTask -TaskName 'MT5AutoStart'"
Write-Host "
"
