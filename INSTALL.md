# Installing SpectrometerV2

SpectrometerV2 runs on **Linux, Windows, and Raspberry Pi**. The scientific core
needs only Python and NumPy; camera support is optional and platform-specific.

## Requirements

- Python **3.9+**
- NumPy (installed automatically)
- A camera backend only if you want live acquisition (see below). The synthetic
  backend and all analysis run with no camera at all.

### Raspberry Pi hardware

A **Raspberry Pi 4 running 64-bit Raspberry Pi OS is recommended**. On 64-bit
Pi OS, NumPy, OpenCV, and picamera2 all install from prebuilt `aarch64` wheels,
so setup is fast and none of the 32-bit workarounds below apply. A **Pi 3B
works** too, but expect the slower, 32-bit install path (see the NumPy/OpenBLAS
note under Raspberry Pi prerequisites). The CSI camera stack (e.g. the IMX219)
is identical on both. Per-frame processing is light, so real-time capture runs
comfortably on either.

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

**Raspberry Pi** — one command does everything (system packages, venv, install,
and verification):

```bash
bash scripts/setup_pi.sh
```

That installs the camera stack and the NumPy/OpenBLAS/matplotlib packages from
apt, creates a `--system-site-packages` venv so pip uses the Pi-built NumPy
(avoiding the `libopenblas.so.0` wheel issue entirely), installs SpectrometerV2,
and checks `--version`. It's safe to re-run.

Prefer to do it by hand? That's equivalent to:

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-numpy python3-matplotlib libopenblas0
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e .
```

USB cameras also work on the Pi via `[usb]`. The default `camera.backend = auto`
picks the Pi camera when available, else USB.

> Note: this NumPy/OpenBLAS wrinkle is specific to **32-bit** Raspberry Pi OS.
> On **64-bit** Pi OS the pip NumPy wheels bundle their own math library and
> none of this is needed.

## Quickstart

```bash
# validate configuration and print the documented schema
spectrometerv2 --config config/config.ini.example validate-config
spectrometerv2 describe-config

# hardware-free: generate, analyze, and save a synthetic spectrum
spectrometerv2 --set camera.backend=synthetic -o out generate-synthetic

# acquire one spectrum from the configured camera, analyze, and save
spectrometerv2 --config config/config.ini.example -o out run

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
