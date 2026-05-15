@echo off
setlocal enabledelayedexpansion
echo ========================================
echo  JAV Installer Builder v15.6
echo ========================================
echo.

echo [1/3] Cleaning old build artefacts...
python scripts\clean_build.py
if errorlevel 1 goto :error

echo.
echo [2/3] Building desktop app (PyInstaller)...
python scripts\build_desktop_app.py --no-clean
if errorlevel 1 goto :error

echo.
echo [3/3] Building Inno Setup installer...
python scripts\build_windows_installer.py
if errorlevel 1 goto :error

echo.
echo Done. Installer output: installer_output\
goto :end

:error
echo.
echo BUILD FAILED. See output above.
endlocal
exit /b 1

:end
endlocal
pause
