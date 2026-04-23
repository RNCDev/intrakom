@echo off
setlocal EnableDelayedExpansion

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

:: Get hub URL
set "HUB_URL=%~2"
if "%HUB_URL%"=="" (
    set /p "HUB_URL=Enter the hub URL (e.g. http://192.168.1.10:8000): "
)
if "%HUB_URL%"=="" (
    echo ERROR: Hub URL cannot be empty.
    pause
    exit /b 1
)

echo.
echo  Installing receiver "%RECEIVER_NAME%" pointing to %HUB_URL%
echo.

:: Remove any existing task with the same name first
schtasks /Query /TN "Intrakom Receiver" >nul 2>&1
if %errorlevel%==0 (
    echo  Removing existing scheduled task...
    schtasks /Delete /TN "Intrakom Receiver" /F >nul 2>&1
)

:: Create scheduled task: runs at every logon, 10s delay, restarts on failure
schtasks /Create ^
  /SC ONLOGON ^
  /TN "Intrakom Receiver" ^
  /TR "\"%EXE%\" --name \"%RECEIVER_NAME%\" --hub \"%HUB_URL%\"" ^
  /DELAY 0000:10 ^
  /F >nul

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
