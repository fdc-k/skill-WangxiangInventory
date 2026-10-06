@echo off
rem ===================================================================
rem  Wangxiang Inventory - Windows launcher (ASCII only on purpose:
rem  Chinese text is printed by Python so cmd.exe never garbles it)
rem ===================================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0.."
set "VPY=%CD%\.venv\Scripts\python.exe"

if exist "%VPY%" goto havevenv

set "BOOT="
where py >nul 2>nul && set "BOOT=py -3"
if not defined BOOT where python >nul 2>nul && set "BOOT=python"
if not defined BOOT where python3 >nul 2>nul && set "BOOT=python3"
if not defined BOOT goto nopython

echo.
echo   Environment not found. Installing now (needs internet, 1-3 min)...
echo.
%BOOT% "tools\bootstrap.py"
if not exist "%VPY%" goto bootfail

:havevenv
"%VPY%" "tools\banner.py" step3
"%VPY%" -m wangxiang sync --ask %*
if exist "output\sync" start "" "output\sync"

goto done

:nopython
echo.
echo   [x] Python was not found on this computer.
echo.
echo   How to fix:
echo     1. If you use WorkBuddy, open WorkBuddy once, then run this again.
echo     2. Otherwise install Python from https://www.python.org/downloads/
echo        During setup, tick "Add Python to PATH".
echo.
pause
exit /b 1

:bootfail
echo.
echo   [x] Install failed. Please send the messages above to your helper.
echo.
pause
exit /b 1

:done
if "%~1"=="" pause
exit /b %ERRORLEVEL%
