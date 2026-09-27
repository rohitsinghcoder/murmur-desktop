@echo off
cd /d "%~dp0"
echo.
echo  This removes Murmur's Start menu and startup shortcuts.
echo  Quit Murmur from its tray icon first.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\shortcuts.ps1 -Remove
echo.
echo  To remove Murmur completely, also delete:
echo    - this folder: %~dp0
echo    - Murmur's Python environment and your dictation history: %USERPROFILE%\.murmur
echo.
pause
