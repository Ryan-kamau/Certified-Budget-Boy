@echo off
REM ============================================================
REM  FinTrack — Windows Task Scheduler Setup
REM  ------------------------------------------------------------
REM  Run this ONCE (as Administrator) to register the cron job.
REM
REM  What it creates
REM  ---------------
REM    Task name : FinTrack_CronRunner
REM    Trigger   : Every hour, every day, starting at midnight
REM    Action    : Calls scripts\run_cron.bat
REM    Run as    : The current logged-in user (no password needed
REM                when "Run only when user is logged on" is set)
REM    On failure: Restart up to 3 times, 5 minutes apart
REM
REM  To change the schedule, edit the /SC, /MO and /ST flags
REM  below, then re-run this script.
REM
REM  Common schedule examples
REM  ------------------------
REM    Every hour       : /SC HOURLY  /MO 1
REM    Every 30 minutes : /SC MINUTE  /MO 30
REM    Daily at 06:00   : /SC DAILY   /ST 06:00
REM    Every 15 minutes : /SC MINUTE  /MO 15
REM
REM  To remove the task later:
REM    schtasks /Delete /TN "FinTrack_CronRunner" /F
REM ============================================================

setlocal EnableDelayedExpansion

REM ── Must be run as Administrator ────────────────────────────────────────────
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo  ERROR: This script must be run as Administrator.
    echo  Right-click the file and choose "Run as administrator".
    echo.
    pause
    exit /b 1
)

REM ── Resolve project root ────────────────────────────────────────────────────
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
pushd "%PROJECT_ROOT%"
set "PROJECT_ROOT=%CD%"
popd

set "TASK_NAME=FinTrack_CronRunner"
set "BAT_PATH=%PROJECT_ROOT%\scripts\run_cron.bat"

REM ── Verify the bat file exists ──────────────────────────────────────────────
if not exist "%BAT_PATH%" (
    echo  ERROR: Cannot find %BAT_PATH%
    echo  Make sure you are running this from inside the FinTrack project.
    pause
    exit /b 1
)

echo.
echo  FinTrack Task Scheduler Setup
echo  ============================================================
echo  Task name  : %TASK_NAME%
echo  Script     : %BAT_PATH%
echo  Schedule   : Every hour
echo  Start time : 00:00
echo  ============================================================
echo.

REM ── Delete any existing task with the same name ──────────────────────────────
schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if %ERRORLEVEL% == 0 (
    echo  Removing existing task "%TASK_NAME%" …
    schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1
)

REM ── Create the new task ──────────────────────────────────────────────────────
REM
REM  /SC HOURLY    — repeat trigger
REM  /MO 1         — every 1 hour
REM  /ST 00:00     — starting at midnight
REM  /TR           — command to run (cmd /c lets us call a .bat)
REM  /RL HIGHEST   — run at highest available privilege level
REM  /F            — force create (no confirmation prompt)
REM

schtasks /Create ^
    /TN "%TASK_NAME%" ^
    /SC HOURLY ^
    /MO 8 ^
    /ST 00:00 ^
    /TR "cmd /c \"%BAT_PATH%\"" ^
    /RL HIGHEST ^
    /F

if %ERRORLEVEL% neq 0 (
    echo.
    echo  ERROR: Failed to create the scheduled task.
    echo  Check you are running as Administrator and that schtasks is available.
    pause
    exit /b 1
)

REM ── Configure retry on failure (via schtasks XML update) ─────────────────────
REM  The /XML approach is most reliable for advanced settings.
REM  We export, patch, and reimport the task XML.

set "XML_TMP=%TEMP%\fintrack_task.xml"

schtasks /Query /TN "%TASK_NAME%" /XML ONE > "%XML_TMP%" 2>nul

REM Patch: add RestartOnFailure (3 retries, 5-minute interval)
REM We use PowerShell for the XML edit since batch has no XML support.
powershell -NoProfile -Command ^
    "(Get-Content '%XML_TMP%') ^
     -replace '</Settings>', ^
     '<RestartOnFailure><Interval>PT5M</Interval><Count>3</Count></RestartOnFailure></Settings>' ^
     | Set-Content '%XML_TMP%'"

if %ERRORLEVEL% == 0 (
    schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1
    schtasks /Create /TN "%TASK_NAME%" /XML "%XML_TMP%" /F >nul 2>&1
    if %ERRORLEVEL% == 0 (
        echo  Retry-on-failure configured (3 retries, 5 min apart).
    ) else (
        echo  Note: Could not apply retry settings — task created without them.
    )
)
del "%XML_TMP%" >nul 2>&1

REM ── Show result ──────────────────────────────────────────────────────────────
echo.
echo  ============================================================
echo  Task "%TASK_NAME%" created successfully!
echo.
echo  To verify:
echo    Task Scheduler GUI  → search for "%TASK_NAME%"
echo    Command line        → schtasks /Query /TN "%TASK_NAME%"
echo.
echo  To run it manually right now:
echo    schtasks /Run /TN "%TASK_NAME%"
echo    — or —
echo    scripts\run_cron.bat
echo.
echo  To remove it:
echo    schtasks /Delete /TN "%TASK_NAME%" /F
echo  ============================================================
echo.

pause
endlocal
exit /b 0