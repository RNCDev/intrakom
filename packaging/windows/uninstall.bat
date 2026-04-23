@echo off
echo.
echo  Intrakom Receiver - Uninstall
echo  ==============================
echo.

schtasks /Query /TN "Intrakom Receiver" >nul 2>&1
if %errorlevel% neq 0 (
    echo  Intrakom Receiver scheduled task not found. Nothing to remove.
    echo.
    pause
    exit /b 0
)

echo  Stopping receiver...
schtasks /End /TN "Intrakom Receiver" >nul 2>&1

echo  Removing scheduled task...
schtasks /Delete /TN "Intrakom Receiver" /F

if %errorlevel%==0 (
    echo.
    echo  Done. Intrakom Receiver has been uninstalled.
) else (
    echo  ERROR: Could not remove task. Try running as Administrator.
)

echo.
pause
