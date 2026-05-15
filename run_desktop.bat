@echo off
cd /d %~dp0
python main.py --desktop
if errorlevel 1 (
  echo.
  echo JAV desktop failed. Running doctor...
  python main.py --doctor
)
pause
