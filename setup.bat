@echo off
setlocal
cd /d "%~dp0"
title Murmur Desktop setup
echo.
echo  === Murmur Desktop setup ===
echo  This installs what Murmur needs (about 800 MB of downloads) into this folder.
echo.

rem --- Find Python 3.11 or newer --------------------------------------------
set "PY="
where py >nul 2>nul && py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo  Python 3.11 or newer was not found.
    echo.
    echo  Install Python 3.12 from https://www.python.org/downloads/
    echo  and tick "Add python.exe to PATH" in the installer, or run this in a terminal:
    echo.
    echo      winget install -e --id Python.Python.3.12
    echo.
    echo  Then run setup.bat again.
    goto :fail
)
for /f "delims=" %%v in ('%PY% -c "import sys; print(sys.version.split()[0])"') do echo  Using Python %%v

rem --- Virtual environment and packages -------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo  Creating a private Python environment in .venv ...
    %PY% -m venv .venv || goto :fail
)
echo  Installing packages ...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip || goto :fail
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || goto :pipfail

rem --- Speech model ------------------------------------------------------------
".venv\Scripts\python.exe" scripts\fetch_model.py || goto :fail

rem --- Shortcuts ---------------------------------------------------------------
echo.
choice /c YN /n /m " Start Murmur automatically when Windows starts? [Y/N] "
set "STARTUP=0"
if errorlevel 2 (set "STARTUP=0") else (set "STARTUP=1")
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\shortcuts.ps1 -Startup %STARTUP% || goto :fail

echo.
echo  === Done ===
echo  Murmur is in your Start menu. Starting it now...
echo  When the mic icon appears in the tray, click into any text box,
echo  hold RIGHT CTRL, speak, and let go.
echo.
start "" ".venv\Scripts\pythonw.exe" -m murmur
pause
exit /b 0

:pipfail
echo.
echo  Installing packages failed. If you have a very new Python version, some packages may
echo  not support it yet: install Python 3.12 (winget install -e --id Python.Python.3.12),
echo  delete the .venv folder, and run setup.bat again.
:fail
echo.
echo  Setup did not finish. See the message above.
pause
exit /b 1
