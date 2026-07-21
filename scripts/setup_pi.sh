#!/usr/bin/env bash
#
# setup_pi.sh — one-command setup for SpectrometerV2 on Raspberry Pi OS.
#
# Installs the system prerequisites (camera stack, plus the NumPy/OpenBLAS and
# matplotlib packages that otherwise trip people up), creates a virtual
# environment that can see them, installs SpectrometerV2, and verifies it.
# Safe to re-run.
#
set -euo pipefail

echo ">> SpectrometerV2 — Raspberry Pi setup"

if ! command -v apt-get >/dev/null 2>&1; then
  echo "!! This script targets Debian / Raspberry Pi OS (apt). See INSTALL.md for other systems." >&2
  exit 1
fi

# Repo root = the directory above this script.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo ">> Installing system packages (camera + NumPy + matplotlib + OpenBLAS)..."
sudo apt-get update
# python3-numpy pulls libopenblas transitively; we also name it explicitly so
# the dependency is obvious and belt-and-suspenders. matplotlib enables --plot
# and the waterfall.
sudo apt-get install -y \
  python3-venv python3-picamera2 python3-opencv python3-numpy python3-matplotlib libopenblas0

echo ">> Creating virtual environment (.venv, able to see the apt packages)..."
python3 -m venv --system-site-packages .venv

echo ">> Installing SpectrometerV2 into the venv..."
# --system-site-packages means NumPy/matplotlib come from apt (already built for
# the Pi), so pip never pulls a wheel that needs its own OpenBLAS.
./.venv/bin/pip install --upgrade pip >/dev/null
./.venv/bin/pip install -e .

echo ">> Verifying install..."
./.venv/bin/spectrometerv2 --version

cat <<'DONE'

>> Done. To use SpectrometerV2:
     source .venv/bin/activate
     spectrometerv2 verify-hardware
     spectrometerv2 --set camera.backend=synthetic --frames 60 stream
DONE
