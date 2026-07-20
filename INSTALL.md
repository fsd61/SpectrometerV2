# Installing SpectrometerV2

SpectrometerV2 runs on **Linux, Windows, and Raspberry Pi**. The scientific core
needs only Python and NumPy; camera support is optional and platform-specific.

## Requirements

- Python **3.9+**
- NumPy (installed automatically)
- A camera backend only if you want live acquisition (see below). The synthetic
  backend and all analysis run with no camera at all.

## Install

```bash
# from the repository root
pip install -e .            # core (numpy)
pip install -e .[dev]       # + pytest for the test suite
pip install -e .[usb]       # + opencv-python for USB / webcam acquisition
```

The console script `spectrometerv2` is installed to your Python scripts
directory; make sure that directory is on your `PATH`. You can always run the
app without installing via `PYTHONPATH=src python -m app ...`.

## Platform-specific prerequisites

**Linux** — USB cameras use V4L via OpenCV: `pip install -e .[usb]`. Ensure your
user can access `/dev/video*` (the `video` group).

**Windows** — install Python from python.org, then `pip install -e .[usb]`.
OpenCV opens cameras by index (DirectShow/MSMF); no V4L path is required — this
is the cross-platform fix over the original tool.

**Raspberry Pi** — the Pi camera uses `picamera2`, and it's best to take NumPy
from apt too (the pip wheels can miss the system math library `libopenblas.so.0`
on the Pi). Install the system packages, then use a venv that can see them:

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-numpy libopenblas0
python3 -m venv --system-site-packages .venv   # --system-site-packages: see the apt packages
source .venv/bin/activate
pip install -e .
```

If you still hit `ImportError: libopenblas.so.0: cannot open shared object
file`, pip installed its own NumPy that needs OpenBLAS. Either provide it
(`sudo apt install -y libopenblas0`) or drop the pip copy so the venv falls back
to the apt build (`pip uninstall -y numpy`).

USB cameras also work on the Pi via `[usb]`. The default `camera.backend = auto`
picks the Pi camera when available, else USB.

## Quickstart

```bash
# validate configuration and print the documented schema
spectrometerv2 --config config/default.ini validate-config
spectrometerv2 describe-config

# hardware-free: generate, analyze, and save a synthetic spectrum
spectrometerv2 --set camera.backend=synthetic -o out generate-synthetic

# acquire one spectrum from the configured camera, analyze, and save
spectrometerv2 --config config/default.ini -o out run

# diagnostics
spectrometerv2 test-camera
spectrometerv2 verify-hardware
spectrometerv2 --set calibration.file=caldata.txt check-calibration

# analyze a previously saved spectrum CSV
spectrometerv2 -i out/synthetic.csv analyze
```

Outputs are written through a pluggable persistence sink (CSV + sidecar
metadata JSON today; database/dashboard backends are planned — see `BACKLOG.md`).

## Running the tests

```bash
pip install -e .[dev]
pytest
```
