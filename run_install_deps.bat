@echo off
cd /d %~dp0
python scripts\bootstrap_dependencies.py --all
pause
