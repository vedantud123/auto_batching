#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "[1/4] Installing build dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install pyinstaller

echo "[2/4] Building executable..."
pyinstaller --noconfirm --clean --onefile --windowed --name auto_batching_app auto_batching_pi.py

echo "[3/4] Copying executable to bundle root..."
cp -f dist/auto_batching_app ./auto_batching_app
chmod +x ./auto_batching_app

echo "[4/4] Done. Run with: ./auto_batching_app"
