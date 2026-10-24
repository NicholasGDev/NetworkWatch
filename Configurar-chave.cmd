@echo off
REM Inicia o assistente PowerShell para configurar chaves do NetWatch.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\configure-key.ps1"
pause
