@echo off
REM ============================================================
REM  FinTrack Cron Runner — Windows Launcher
REM  ------------------------------------------------------------
REM  Run this file directly for a manual trigger, or let
REM  Windows Task Scheduler call it on a schedule.
REM
REM  Usage (double-click or call from Task Scheduler):
REM    run_cron.bat               — run all jobs
REM    run_cron.bat --dry-run     — simulate only
REM    run_cron.bat --jobs recurring,goals
REM    run_cron.bat --verbose
REM
REM  The script:
REM    1. Resolves the project root from the batch file's location
REM    2. Activates the virtual environment (if one exists)
REM    3. Runs cron_runner.py with any arguments passed to this .bat
REM    4. Writes the exit code to reports\logs\last_run_exit_code.txt
REM    5. Exits with that same code so Task Scheduler can detect failures
REM ============================================================

setlocal EnableDelayedExpansion

REM ── Resolve project root (one level up from scripts\) ──────────────────────
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

REM Normalize the path (remove trailing backslash + resolve ..)
pushd "%PROJECT_ROOT%"
set "PROJECT_ROOT=%CD%"
popd

REM ── Log directory ───────────────────────────────────────────────────────────
set "LOG_DIR=%PROJECT_ROOT%\reports\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set "RUN_LOG=%LOG_DIR%\cron_run.log"
set "EXIT_CODE_FILE=%LOG_DIR%\last_run_exit_code.txt"

REM ── Timestamp for the run log ───────────────────────────────────────────────
for /f "tokens=1-3 delims=/ " %%a in ("%DATE%") do (
    set "YY=%%a"
    set "MM=%%b"
    set "DD=%%c"
)
for /f "tokens=1-2 delims=:. " %%a in ("%TIME%") do (
    set "HH=%%a"
    set "MIN=%%b"
)
set "TIMESTAMP=%YY%-%MM%-%DD% %HH%:%MIN%"

echo. >> "%RUN_LOG%"
echo ============================================================ >> "%RUN_LOG%"
echo  FinTrack Cron Runner — %TIMESTAMP% >> "%RUN_LOG%"
echo  Args: %* >> "%RUN_LOG%"
echo ============================================================ >> "%RUN_LOG%"

REM ── Locate Python ───────────────────────────────────────────────────────────
REM  Priority order:
REM    1. .venv in the project root (recommended)
REM    2. venv in the project root
REM    3. Python from PATH

set "PYTHON_EXE="

if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
    echo Using virtualenv: %PROJECT_ROOT%\.venv >> "%RUN_LOG%"
    goto :found_python
)

if exist "%PROJECT_ROOT%\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_ROOT%\venv\Scripts\python.exe"
    echo Using virtualenv: %PROJECT_ROOT%\venv >> "%RUN_LOG%"
    goto :found_python
)

REM Fall back to system Python
where python >nul 2>&1
if %ERRORLEVEL% == 0 (
    set "PYTHON_EXE=python"
    echo Using system Python >> "%RUN_LOG%"
    goto :found_python
)

where python3 >nul 2>&1
if %ERRORLEVEL% == 0 (
    set "PYTHON_EXE=python3"
    echo Using system python3 >> "%RUN_LOG%"
    goto :found_python
)

echo ERROR: Python not found. Install Python or create a venv at %PROJECT_ROOT%\.venv >> "%RUN_LOG%"
echo ERROR: Python not found. >> "%RUN_LOG%"
echo 2 > "%EXIT_CODE_FILE%"
exit /b 2

:found_python

REM ── Run the cron runner ──────────────────────────────────────────────────────
"%PYTHON_EXE%" -m fintrack.cron.cron_runner %* >> "%RUN_LOG%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

REM ── Record exit code ────────────────────────────────────────────────────────
echo %EXIT_CODE% > "%EXIT_CODE_FILE%"

REM ── Log result ──────────────────────────────────────────────────────────────
if "%EXIT_CODE%" == "0" (
    echo  Result: SUCCESS (exit 0) >> "%RUN_LOG%"
) else if "%EXIT_CODE%" == "1" (
    echo  Result: PARTIAL FAILURE (exit 1) — check reports\logs\cron.log >> "%RUN_LOG%"
) else (
    echo  Result: FATAL ERROR (exit %EXIT_CODE%) >> "%RUN_LOG%"
)

endlocal
exit /b %EXIT_CODE%