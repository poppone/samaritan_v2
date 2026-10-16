@echo off
REM Taglia le clip dalle live Twitch e le consegna a Finch.
REM Funziona da qualsiasi cartella: parte da dove sta questo file.
cd /d "%~dp0"
if not exist .venv (
  echo Prima volta: preparo l ambiente Python...
  py -3.12 -m venv .venv 2>nul || python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\pip install -r requirements.txt
)
.venv\Scripts\python taglia_live.py %*
if "%CLIP_AUTO%"=="" pause
