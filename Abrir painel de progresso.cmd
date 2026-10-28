@echo off
powershell.exe -NoProfile -File "%~dp0scripts\abrir_painel_progresso.ps1"
if errorlevel 1 pause
