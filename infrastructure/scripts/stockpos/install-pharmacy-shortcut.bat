@echo off
setlocal
REM Stock & POS - install-pharmacy-shortcut.bat
REM Creates the "Pharmacy" Desktop + Start Menu shortcut (opens over Wi-Fi and
REM copies the address so another device can open the system).
REM Optional: pass the server URL / hotkey, e.g.
REM   install-pharmacy-shortcut.bat -Url "http://192.168.1.50" -Hotkey "CTRL+ALT+P"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-pharmacy-shortcut.ps1" %*
exit /b %ERRORLEVEL%
