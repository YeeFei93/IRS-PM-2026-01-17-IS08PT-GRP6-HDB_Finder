@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PID_FILE=%~dp0evaluator.pid"
set "PORT=8011"
set "APP_PID="
set "PYTHON_EXE="

call :find_running_pid
if defined APP_PID (
  echo AI Recommender Evaluator is already running with PID !APP_PID!.
  choice /C YN /N /M "Terminate it now? (Y/N): "
  if errorlevel 2 goto :keep_running
  call :stop_running_pid
  exit /b 0
)

call :resolve_python
if not defined PYTHON_EXE (
  echo Could not find a Python runtime to start the evaluator.
  exit /b 1
)

powershell -NoProfile -Command ^
  "$proc = Start-Process -FilePath '!PYTHON_EXE!' -ArgumentList 'app.py' -WorkingDirectory '%~dp0' -PassThru; Set-Content -Path '%PID_FILE%' -Value $proc.Id -Encoding Ascii; Write-Host ('Started AI Recommender Evaluator with PID ' + $proc.Id)"

echo Open http://127.0.0.1:%PORT%/
exit /b 0

:keep_running
echo Keeping the current evaluator process running.
echo Open http://127.0.0.1:%PORT%/
exit /b 0

:stop_running_pid
powershell -NoProfile -Command ^
  "$proc = Get-Process -Id !APP_PID! -ErrorAction SilentlyContinue; if ($proc) { Stop-Process -Id !APP_PID! -Force; exit 0 } else { exit 1 }"
if errorlevel 1 (
  echo No running AI Recommender Evaluator process was found for PID !APP_PID!.
) else (
  echo Stopped AI Recommender Evaluator with PID !APP_PID!.
)
if exist "%PID_FILE%" del "%PID_FILE%" >nul 2>nul
exit /b 0

:find_running_pid
set "APP_PID="

if exist "%PID_FILE%" (
  for /f "usebackq delims=" %%P in ("%PID_FILE%") do (
    set "APP_PID=%%P"
    goto :have_pid_file
  )
:have_pid_file
  if defined APP_PID (
    powershell -NoProfile -Command ^
      "$proc = Get-Process -Id !APP_PID! -ErrorAction SilentlyContinue; if ($proc) { exit 0 } else { exit 1 }"
    if not errorlevel 1 exit /b 0
  )
  del "%PID_FILE%" >nul 2>nul
  set "APP_PID="
)

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  set "APP_PID=%%P"
  >"%PID_FILE%" echo %%P
  exit /b 0
)

exit /b 0

:resolve_python
set "PYTHON_EXE="

for /f "usebackq delims=" %%I in (`py -c "import sys; print(sys.executable)" 2^>nul`) do (
  set "PYTHON_EXE=%%I"
)

if not defined PYTHON_EXE (
  for /f "usebackq delims=" %%I in (`python -c "import sys; print(sys.executable)" 2^>nul`) do (
    set "PYTHON_EXE=%%I"
  )
)

exit /b 0
