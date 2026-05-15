#!/usr/bin/env bash
cd "$(dirname "$0")"
python3 main.py --desktop || { echo "Desktop failed. Running doctor..."; python3 main.py --doctor; }
