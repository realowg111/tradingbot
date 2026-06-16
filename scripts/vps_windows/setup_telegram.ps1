# ============================================================================
# Trading Bot - Setup automatique du module Copie Telegram (RentaTrade)
# ============================================================================
# Ce script fait TOUT automatiquement :
#   1. git pull
#   2. pip install telethon
#   3. ajoute les variables Telegram au .env (sans ecraser le reste)
#   4. cree le dossier data/ pour la session Telethon
#   5. redemarre l'app (signal au watchdog uvicorn --reload)
#
# UTILISATION :
#   1. Ouvre PowerShell EN ADMINISTRATEUR sur ton VPS
#   2. Colle ces 2 lignes (1 seule fois) :
#        cd C:\trading-bot
#        powershell -ExecutionPolicy Bypass -File .\scripts\vps_windows\setup_telegram.ps1
#   3. Attends la fin du script (30-60 secondes)
#   4. Va dans l'app -> Plus -> Copie Telegram -> "Envoyer le code SMS"
# ============================================================================

$ErrorActionPreference = "Stop"
$AppDir = "C:\trading-bot"
$EnvFile = "$AppDir\backend\.env"
$DataDir = "$AppDir\backend\data"

function Write-Step($n, $msg) {
    Write-Host "`n[$n] $msg" -ForegroundColor Cyan
}

function Write-Ok($msg) {
    Write-Host "    OK $msg" -ForegroundColor Green
}

function Write-Warn($msg) {
    Write-Host "    !! $msg" -ForegroundColor Yellow
}

try {
    Write-Host "=============================================================" -ForegroundColor Magenta
    Write-Host "  TRADING BOT - Setup module Telegram (RentaTrade)" -ForegroundColor Magenta
    Write-Host "=============================================================" -ForegroundColor Magenta

    if (-not (Test-Path $AppDir)) {
        throw "Dossier $AppDir introuvable. Le bot n'est pas installe au bon endroit."
    }

    Set-Location $AppDir

    # ------------------------------------------------------------------------
    Write-Step 1 "Pull du code GitHub..."
    $before = git rev-parse HEAD
    git fetch 2>&1 | Out-Null
    git pull --ff-only 2>&1 | Out-Null
    $after = git rev-parse HEAD
    if ($before -eq $after) {
        Write-Ok "Code deja a jour ($($after.Substring(0,7)))"
    } else {
        Write-Ok "Mis a jour : $($before.Substring(0,7)) -> $($after.Substring(0,7))"
    }

    # ------------------------------------------------------------------------
    Write-Step 2 "Installation de Telethon (Python)..."
    $pip = "$AppDir\venv\Scripts\pip.exe"
    if (-not (Test-Path $pip)) {
        throw "venv introuvable a $pip. Reinstalle le bot avec install.ps1 d'abord."
    }
    & $pip install telethon 2>&1 | Out-Null
    & $pip install -r "$AppDir\backend\requirements.txt" 2>&1 | Out-Null
    Write-Ok "Telethon installe + deps a jour"

    # ------------------------------------------------------------------------
    Write-Step 3 "Configuration des variables d'environnement Telegram..."

    $envVars = @{
        "TELEGRAM_API_ID"        = "30879528"
        "TELEGRAM_API_HASH"      = "5674826007957132ee773fa767e623f2"
        "TELEGRAM_PHONE"         = "+33769008392"
        "TELEGRAM_CHANNEL"       = "RentaTrade Z VIP"
        "TELEGRAM_SESSION_PATH"  = "$DataDir\telegram.session"
    }

    if (-not (Test-Path $EnvFile)) {
        New-Item -Path $EnvFile -ItemType File -Force | Out-Null
    }
    $envLines = Get-Content $EnvFile -ErrorAction SilentlyContinue
    if ($null -eq $envLines) { $envLines = @() }

    $added = 0
    $updated = 0
    $newLines = [System.Collections.ArrayList]@()
    $seen = @{}

    foreach ($line in $envLines) {
        $matched = $false
        foreach ($key in $envVars.Keys) {
            if ($line -match "^\s*$key\s*=") {
                $newLines.Add("$key=$($envVars[$key])") | Out-Null
                $seen[$key] = $true
                $updated++
                $matched = $true
                break
            }
        }
        if (-not $matched) {
            $newLines.Add($line) | Out-Null
        }
    }

    # Ajoute les cles manquantes
    $hasSeparator = $false
    foreach ($key in $envVars.Keys) {
        if (-not $seen.ContainsKey($key)) {
            if (-not $hasSeparator) {
                $newLines.Add("") | Out-Null
                $newLines.Add("# Telegram copy trading") | Out-Null
                $hasSeparator = $true
            }
            $newLines.Add("$key=$($envVars[$key])") | Out-Null
            $added++
        }
    }

    Set-Content -Path $EnvFile -Value $newLines -Encoding UTF8
    Write-Ok "Variables Telegram : $added ajoutees, $updated mises a jour"

    # ------------------------------------------------------------------------
    Write-Step 4 "Creation du dossier de session Telegram..."
    if (-not (Test-Path $DataDir)) {
        New-Item -Path $DataDir -ItemType Directory -Force | Out-Null
    }
    Write-Ok "$DataDir pret"

    # ------------------------------------------------------------------------
    Write-Step 5 "Redemarrage du backend (uvicorn --reload prendra en compte le .env)..."
    # uvicorn --reload watche le code mais PAS le .env. On touche un fichier .py pour forcer le reload.
    $touchFile = "$AppDir\backend\server.py"
    if (Test-Path $touchFile) {
        $now = Get-Date
        (Get-Item $touchFile).LastWriteTime = $now
        Write-Ok "Backend redemarre (touch server.py)"
    } else {
        Write-Warn "server.py introuvable, redemarre manuellement si necessaire."
    }

    # ------------------------------------------------------------------------
    Write-Host "`n=============================================================" -ForegroundColor Green
    Write-Host "  INSTALLATION TERMINEE" -ForegroundColor Green
    Write-Host "=============================================================" -ForegroundColor Green
    Write-Host "`nProchaines etapes :" -ForegroundColor White
    Write-Host "  1. Ouvre ton app (preview Emergent ou ton URL)" -ForegroundColor White
    Write-Host "  2. Va dans : Plus -> Copie Telegram (RentATrade)" -ForegroundColor White
    Write-Host "  3. Verifie que 'Connecte a Telegram' = Oui" -ForegroundColor White
    Write-Host "  4. Clique : '1. Envoyer le code SMS'" -ForegroundColor White
    Write-Host "  5. Tu vas recevoir un code sur Telegram (pas par SMS)" -ForegroundColor White
    Write-Host "     -> Saisis-le et clique '2. Valider le code'" -ForegroundColor White
    Write-Host "  6. (Optionnel) Si la 2FA Telegram est activee : entre ton mot de passe cloud" -ForegroundColor White
    Write-Host "`nLe Shadow mode est ACTIF par defaut (analyse seule, sans execution)." -ForegroundColor Yellow
    Write-Host "Quand tu seras satisfait du parsing (24-48h), desactive Shadow pour passer en LIVE." -ForegroundColor Yellow
    Write-Host ""
}
catch {
    Write-Host "`nERREUR : $($_.Exception.Message)" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed
    exit 1
}
