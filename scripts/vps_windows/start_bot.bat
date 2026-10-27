@echo off
REM Lance le bot et le relance automatiquement s'il s'arrête (crash, redémarrage MT5...).
REM A placer dans le Planificateur de tâches Windows : "Au démarrage", "Exécuter même si l'utilisateur n'est pas connecté".
cd /d %~dp0\..\..
:loop
python -m bot run %*
echo Bot arrete, relance dans 30 secondes...
timeout /t 30 /nobreak >nul
goto loop
