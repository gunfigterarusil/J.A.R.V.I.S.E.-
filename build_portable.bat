@echo off
setlocal enabledelayedexpansion
echo ========================================
echo  JAV Portable Builder v15.6
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
echo [3/3] Creating portable release folder...
python scripts\make_portable_release.py dist\JAV_portable
if errorlevel 1 goto :error

echo.
echo Done. Portable release: dist\JAV_portable\
goto :end

:error
echo.
echo BUILD FAILED. See output above.
endlocal
exit /b 1

:end
endlocal
pause
