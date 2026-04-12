@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "LOG_DIR=%SCRIPT_DIR%.dev-logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo [36m^>^> Clearing ports 3000 and 5173...[0m
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":3000 " ^| findstr "LISTENING" 2^>nul') do (
  taskkill /PID %%p /F >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":5173 " ^| findstr "LISTENING" 2^>nul') do (
  taskkill /PID %%p /F >nul 2>&1
)

:: ── Python dependencies ───────────────────────────────────────────────────────
echo [36m^>^> Checking Python dependencies...[0m
pip install --quiet redis mysql-connector-python >nul 2>&1
echo   Python packages OK.

:: ── Redis ─────────────────────────────────────────────────────────────────────
echo [36m^>^> Starting Redis...[0m
sc query Redis >nul 2>&1
if %errorlevel% == 0 (
  sc start Redis >nul 2>&1
  echo   [32mRedis service started.[0m
) else (
  where redis-server >nul 2>&1
  if %errorlevel% == 0 (
    start "Redis" /min redis-server
    echo   [32mRedis started (redis-server).[0m
  ) else (
    echo   [33mWarning: Redis not found. Install Redis for Windows and add it to PATH.[0m
  )
)

:: ── MySQL ─────────────────────────────────────────────────────────────────────
echo [36m^>^> Starting MySQL...[0m
sc query MySQL >nul 2>&1
if %errorlevel% == 0 (
  sc start MySQL >nul 2>&1
  echo   [32mMySQL service started.[0m
) else (
  sc query MySQL80 >nul 2>&1
  if %errorlevel% == 0 (
    sc start MySQL80 >nul 2>&1
    echo   [32mMySQL80 service started.[0m
  ) else (
    echo   [33mWarning: MySQL service not found. Ensure MySQL is installed and running.[0m
  )
)

:: ── Backend (Node.js Express) ─────────────────────────────────────────────────
echo [36m^>^> Starting backend...[0m
cd /d "%SCRIPT_DIR%backend\api"
if not exist "node_modules" (
  echo   Installing backend dependencies...
  call npm install
)
start "Backend" /min cmd /c "npm run dev > "%LOG_DIR%\backend.log" 2>&1"
echo   [32mBackend starting — http://localhost:3000[0m

:: ── Frontend (Vite) ───────────────────────────────────────────────────────────
echo [36m^>^> Starting frontend...[0m
cd /d "%SCRIPT_DIR%frontend"
if not exist "node_modules" (
  echo   Installing frontend dependencies...
  call npm install
)
start "Frontend" /min cmd /c "npm run dev > "%LOG_DIR%\frontend.log" 2>&1"
echo   [32mFrontend starting — http://localhost:5173[0m

echo.
echo [32mAll services started.[0m
echo   Logs: .dev-logs\backend.log ^| .dev-logs\frontend.log
echo   Close the Backend and Frontend windows (or use Task Manager) to stop them.
echo   Note: Redis and MySQL services remain running. Stop them via services.msc.
echo.

:: Stream logs
echo [36mStreaming logs (Ctrl+C to stop tailing — services keep running):[0m
powershell -Command "Get-Content '%LOG_DIR%\backend.log', '%LOG_DIR%\frontend.log' -Wait"
