#!/usr/bin/env bash
cd "$(dirname "$0")"
python3 main.py --desktop
code=$?
if [ "$code" -ne 0 ]; then
  echo ""
  echo "JAV desktop failed. Running doctor..."
  python3 main.py --doctor
fi
exit "$code"
