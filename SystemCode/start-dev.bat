@echo on
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"

echo Starting services...

:: Backend
if not exist "%SCRIPT_DIR%backend\api" (
  echo Backend folder not found!
  pause
  exit /b
)

pip install -r requirements.txt

echo Checking backend dependencies...
cd /d "%SCRIPT_DIR%backend\api"
call npm install

cd /d "%SCRIPT_DIR%backend\api"
start "Backend" cmd /k "npm run dev"

:: Frontend
if not exist "%SCRIPT_DIR%frontend" (
  echo Frontend folder not found!
  pause
  exit /b
)

echo Checking frontend dependencies...
cd /d "%SCRIPT_DIR%frontend"
call npm install

cd /d "%SCRIPT_DIR%frontend"
start "Frontend" cmd /k "npm run dev"

:: Redis
if exist "C:\Program Files\Redis\redis-server.exe" (
  start "Redis" cmd /k "C:\Program Files\Redis\redis-server.exe"
)

echo Done launching.
pause