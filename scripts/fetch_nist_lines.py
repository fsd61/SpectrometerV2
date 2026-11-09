"""Download reference line lists from the NIST Atomic Spectra Database (ASD).

Writes one CSV per species into ``src/reference/nist/``. The application reads
only those files; run this script by hand when you want to refresh them or add
a species, then review the diff and commit it like any other change.

    .venv\\Scripts\\python.exe scripts\\fetch_nist_lines.py
    .venv\\Scripts\\python.exe scripts\\fetch_nist_lines.py --species "Kr I" --low 500 --high 1100

Wavelengths are in air (ASD's default between 200 and 2000 nm).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference.lines import (  # noqa: E402
    DATA_DIR, parse_asd_csv, species_to_filename, write_line_file,
)

ASD_URL = "https://physics.nist.gov/cgi-bin/ASD/lines1.pl"

# Argon is the FS-2 calibration lamp; mercury comes from fluorescent tubes;
# neon and sodium cover indicator lamps and the planned 575 nm extension;
# krypton, xenon and helium are common pen-ray / discharge sources.
DEFAULT_SPECIES = ("Ar I", "Hg I", "Ne I", "Na I", "Kr I", "Xe I", "He I")
DEFAULT_LOW_NM = 500.0
DEFAULT_HIGH_NM = 1100.0


def build_query(species: str, low_nm: float, high_nm: float) -> str:
    params = {
        "spectra": species,
        "low_w": f"{low_nm:g}",
        "upp_w": f"{high_nm:g}",
        "unit": "1",            # nm
        "format": "2",          # CSV
        "line_out": "0",        # all lines
        "remove_js": "on",
        "en_unit": "0",
        "output": "0",          # entire list, no paging
        "show_obs_wl": "1",
        "show_calc_wl": "1",
        "order_out": "0",       # sort by wavelength
        "show_av": "2",         # vacuum < 200 nm, air 200-2000 nm
        "A_out": "0",
        "intens_out": "on",
        "allowed_out": "1",
        "forbid_out": "1",
        "submit": "Retrieve Data",
    }
    return ASD_URL + "?" + urllib.parse.urlencode(params)


def fetch(url: str, timeout: float = 60.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "SpectrometerV2 line fetch"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
        return response.read().decode("utf-8", errors="replace")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--species", action="append",
                        help='ASD spectrum name, e.g. "Ar I" (repeatable). Default: '
                             + ", ".join(DEFAULT_SPECIES))
    parser.add_argument("--low", type=float, default=DEFAULT_LOW_NM, help="lower bound, nm")
    parser.add_argument("--high", type=float, default=DEFAULT_HIGH_NM, help="upper bound, nm")
    parser.add_argument("--out", type=Path, default=DATA_DIR, help="output folder")
    args = parser.parse_args(argv)

    today = dt.date.today().isoformat()
    failures = 0
    for species in args.species or DEFAULT_SPECIES:
        url = build_query(species, args.low, args.high)
        try:
            lines = parse_asd_csv(fetch(url), species)
        except Exception as exc:  # noqa: BLE001 - report and carry on with the rest
            print(f"{species}: FAILED - {exc}", file=sys.stderr)
            failures += 1
            continue
        observed = sum(1 for ln in lines if ln.observed)
        path = write_line_file(args.out / species_to_filename(species), species, lines, {
            "source": "NIST Atomic Spectra Database (ASD), https://physics.nist.gov/asd",
            "retrieved": today,
            "range_nm": f"{args.low:g}-{args.high:g}",
            "medium": "air (ASD convention, 200-2000 nm)",
            "wavelength_nm": "Ritz wavelength when given, else observed",
            "query": url,
        })
        print(f"{species}: {len(lines)} lines ({observed} observed) -> {path.relative_to(ROOT)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
