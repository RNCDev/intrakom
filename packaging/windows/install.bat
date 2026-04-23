@echo off
setlocal EnableDelayedExpansion

:: Self-elevate to Administrator if needed (Register-ScheduledTask requires it)
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command ^
      "Start-Process cmd -ArgumentList '/c \"%~f0\" %*' -Verb RunAs -Wait"
    exit /b
)

echo.
echo  Intrakom Receiver - Install
echo  ===========================
echo.

:: Determine the binary path (same folder as this script)
set "SCRIPT_DIR=%~dp0"
set "EXE=%SCRIPT_DIR%intrakom-receiver.exe"

if not exist "%EXE%" (
    echo ERROR: intrakom-receiver.exe not found in %SCRIPT_DIR%
    echo Please unzip the release package and run install.bat from inside the folder.
    echo.
    pause
    exit /b 1
)

:: Get receiver name
set "RECEIVER_NAME=%~1"
if "%RECEIVER_NAME%"=="" (
    set /p "RECEIVER_NAME=Enter a name for this receiver (e.g. Living Room, Office): "
)
if "%RECEIVER_NAME%"=="" (
    echo ERROR: Receiver name cannot be empty.
    pause
    exit /b 1
)

:: Hub URL is fixed for this household
set "HUB_URL=%~2"
if "%HUB_URL%"=="" set "HUB_URL=https://piserver-1005.tail2ace7b.ts.net:8000"

echo.
echo  Checking hub is reachable at %HUB_URL% ...
powershell -NoProfile -Command ^
  "try { $r = Invoke-WebRequest -Uri '%HUB_URL%/ping' -TimeoutSec 5 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  WARNING: Could not reach %HUB_URL%
    echo  Make sure the hub is running and the URL is correct.
    echo.
    set /p "_CONT=  Continue anyway? [y/N] "
    if /i not "!_CONT!"=="y" (
        pause
        exit /b 1
    )
)

echo.
echo  Installing receiver "%RECEIVER_NAME%" pointing to %HUB_URL%
echo.

:: Create/replace scheduled task via PowerShell so we can set restart-on-failure
powershell -NoProfile -Command ^
  "$exe = '%EXE%'; $name = '%RECEIVER_NAME%'; $hub = '%HUB_URL%';" ^
  "$action  = New-ScheduledTaskAction -Execute $exe -Argument ('--name \"' + $name + '\" --hub \"' + $hub + '\"');" ^
  "$trigger = New-ScheduledTaskTrigger -AtLogOn;" ^
  "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Days 3650) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1);" ^
  "Register-ScheduledTask -TaskName 'Intrakom Receiver' -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null"

if %errorlevel% neq 0 (
    echo ERROR: Failed to create scheduled task. Try running as Administrator.
    pause
    exit /b 1
)

:: Start it now without waiting for reboot
echo  Starting receiver now...
schtasks /Run /TN "Intrakom Receiver" >nul 2>&1

echo.
echo  Done! The receiver will start automatically at every login.
echo.
echo  To verify it's running, open the hub admin page in your browser:
echo    %HUB_URL%/admin
echo.
echo  To uninstall, run uninstall.bat in this folder.
echo.
pause
