# Installe les outils du "Monteur IA" sous Windows.
# Clic droit > Exécuter avec PowerShell, depuis le dossier monteur-ia.
Set-Location $PSScriptRoot
winget install -e --id Gyan.FFmpeg
winget install -e --id yt-dlp.yt-dlp
winget install -e --id OpenJS.NodeJS.LTS
winget install -e --id Git.Git
winget install -e --id Google.Chrome
# whisper.cpp : télécharge le zip Windows de la dernière release
Write-Host "whisper.cpp : télécharge whisper-bin-x64.zip sur https://github.com/ggml-org/whisper.cpp/releases et dézippe-le dans C:\whisper"
# Les skills de montage
npx -y skills add Melvynx/video-agent-skills -a claude-code -y
Write-Host "Prêt. Ouvre Claude Code en mode Local sur ce dossier, puis tape /studio-setup"
