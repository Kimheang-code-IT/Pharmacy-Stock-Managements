@echo off
setlocal EnableExtensions
REM Forward to the PowerShell installer from repository root.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-client.ps1" %*
exit /b %ERRORLEVEL%
