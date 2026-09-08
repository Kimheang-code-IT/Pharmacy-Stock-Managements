@echo off
setlocal EnableExtensions
REM Clone the repository and build it. Run from any folder in Command Prompt.

set "REPO_URL=https://github.com/Kimheang-code-IT/stock_pos.git"
set "ROOT=%USERPROFILE%\stock_pos"

where git >nul 2>&1
if errorlevel 1 (
  echo Git is not installed. Install Git, then run this again.
  exit /b 1
)
where docker >nul 2>&1
if errorlevel 1 (
  echo Docker is not installed. Install Docker Desktop, start it, then run this again.
  exit /b 1
)

if not exist "%ROOT%\docker-compose.yml" (
  echo Cloning %REPO_URL% to %ROOT%
  git clone "%REPO_URL%" "%ROOT%"
  if errorlevel 1 exit /b 1
)

cd /d "%ROOT%"
call "%ROOT%\infrastructure\scripts\install-client.cmd"
endlocal
