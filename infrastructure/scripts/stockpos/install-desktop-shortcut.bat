@echo off
setlocal
REM Stock & POS - install-desktop-shortcut.bat
REM Creates Desktop + Start Menu shortcuts and the Ctrl+Alt+S hotkey.
REM Optional: pass a different hotkey, e.g.
REM   install-desktop-shortcut.bat -Hotkey "CTRL+ALT+P"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-desktop-shortcut.ps1" %*
exit /b %ERRORLEVEL%
