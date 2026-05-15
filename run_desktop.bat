@echo off
cd /d %~dp0
if not exist .env (
  echo Creating portable configuration...
  python main.py --init-portable .
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "JAV" pythonw "%~dp0main.py" --desktop
) else (
  echo pythonw not found; starting with python console...
  python "%~dp0main.py" --desktop
  if errorlevel 1 (
    echo.
    echo JAV desktop failed. Running doctor...
    python "%~dp0main.py" --doctor
    pause
  )
)
