@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0codigo_fonte\acompanhamento\abrir_painel_progresso.ps1"
if errorlevel 1 pause
