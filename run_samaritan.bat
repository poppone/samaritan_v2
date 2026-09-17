@echo off
REM Esegue Samaritan dalla cartella in cui si trova questo file,
REM cosi' funziona su qualsiasi PC senza percorsi hardcoded.
cd /d "%~dp0"
python main.py %*
pause
