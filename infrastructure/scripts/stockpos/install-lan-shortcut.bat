@echo off
setlocal
REM Stock & POS - install-lan-shortcut.bat
REM Creates Desktop + Start Menu "LAN" shortcuts and the Ctrl+Alt+L hotkey.
REM Optional: pass the server URL / hotkey, e.g.
REM   install-lan-shortcut.bat -Url "http://192.168.1.50" -Hotkey "CTRL+ALT+L"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-lan-shortcut.ps1" %*
exit /b %ERRORLEVEL%
