#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -f .env ] || python main.py --init-portable .
python main.py --desktop
