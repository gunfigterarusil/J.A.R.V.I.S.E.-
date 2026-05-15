@echo off
setlocal enabledelayedexpansion
echo ========================================
echo  JAV Release Builder v15.6
echo ========================================
echo.

echo [1/5] Cleaning old build artefacts...
python scripts\clean_build.py --all
if errorlevel 1 goto :error

echo.
echo [2/5] Building desktop app (PyInstaller)...
python scripts\build_desktop_app.py --no-clean
if errorlevel 1 goto :error

echo.
echo [3/5] Running build smoke test...
python scripts\build_smoke_test.py dist\JAV --no-doctor
if errorlevel 1 goto :smoke_error

echo.
echo [4/5] Building Windows installer (Inno Setup)...
python scripts\build_windows_installer.py
if errorlevel 1 (
    echo WARNING: Installer build failed ^(ISCC.exe missing?^). Continuing...
)

echo.
echo [5/5] Creating portable ZIP...
python scripts\make_portable_release.py dist\JAV_portable
if errorlevel 1 goto :error

echo.
echo ========================================
echo  BUILD SUCCESSFUL
echo  Installer : installer_output\
echo  Portable  : dist\JAV_portable\
echo ========================================
goto :end

:smoke_error
echo.
echo BUILD FAILED: Smoke test did not pass.
echo Check dist\JAV\ and re-run build.
endlocal
exit /b 1

:error
echo.
echo BUILD FAILED. See output above.
endlocal
exit /b 1

:end
endlocal
pause
