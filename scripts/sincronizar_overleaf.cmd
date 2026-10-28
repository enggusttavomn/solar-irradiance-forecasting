@echo off
cd /d "%~dp0.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0sincronizar_overleaf.ps1"
if errorlevel 1 (
  echo.
  echo A sincronizacao com o Overleaf terminou com erro. Leia a mensagem acima.
)
echo.
pause
