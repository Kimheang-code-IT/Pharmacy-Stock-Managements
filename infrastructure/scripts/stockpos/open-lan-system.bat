@echo off
setlocal
REM Stock & POS - open-lan-system.bat (forwards to PowerShell)
REM Optional: override the URL, e.g. open-lan-system.bat -Url "http://192.168.1.50"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0open-lan-system.ps1" %*
exit /b %ERRORLEVEL%
