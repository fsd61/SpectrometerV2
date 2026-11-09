"""Reference emission lines from the NIST Atomic Spectra Database (ASD).

The line lists are plain CSV files shipped inside this package (``nist/``),
one per species, written by ``scripts/fetch_nist_lines.py``. The application
only ever reads these files; it never queries the NIST website at run time, so
a calibration reference cannot change between runs or depend on a remote
server being up.

Wavelengths are in air, nm (ASD's convention between 200 and 2000 nm). Each
line carries ASD's observed and Ritz wavelengths; ``wavelength_nm`` is the Ritz
value when ASD gives one (usually the more accurate) and the observed value
otherwise.

ASD relative intensities come from many different light sources and are only
roughly comparable even within one species. They are good for ranking lines
("which are the strong ones?"), not for predicting peak heights in a given
lamp.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path

from errors import CalibrationError

DATA_DIR = Path(__file__).resolve().parent / "nist"

CSV_COLUMNS = ("wavelength_nm", "observed_nm", "ritz_nm", "intensity",
               "intensity_raw", "aki_per_s", "accuracy")

_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


@dataclass(frozen=True)
class ReferenceLine:
    """One emission line of one species."""

    species: str                 # e.g. "Ar I"
    wavelength_nm: float         # Ritz if available, else observed (air)
    observed_nm: float | None
    ritz_nm: float | None
    intensity: float | None      # ASD relative intensity, numeric part only
    intensity_raw: str = ""      # ASD's string, with any flags ("1000h", "(300)")
    aki_per_s: float | None = None
    accuracy: str = ""

    @property
    def observed(self) -> bool:
        """True when the line has been seen in a laboratory source."""
        return self.observed_nm is not None


# --------------------------------------------------------------------- #
# File naming
# --------------------------------------------------------------------- #
def species_to_filename(species: str) -> str:
    """'Ar I' -> 'Ar_I.csv'."""
    return "_".join(species.split()) + ".csv"


def filename_to_species(name: str) -> str:
    """'Ar_I.csv' -> 'Ar I'."""
    return Path(name).stem.replace("_", " ")


def available_species(data_dir: Path | None = None) -> list[str]:
    """Species with a line file, argon first (the usual calibration lamp)."""
    folder = Path(data_dir) if data_dir is not None else DATA_DIR
    names = sorted(filename_to_species(p.name) for p in folder.glob("*.csv"))
    return sorted(names, key=lambda s: (s != "Ar I", s))


# --------------------------------------------------------------------- #
# Parsing ASD output (used by the fetch script and its tests)
# --------------------------------------------------------------------- #
def _clean(cell: str) -> str:
    """ASD's CSV wraps values Excel-style as ="value"; strip that."""
    cell = (cell or "").strip()
    if cell.startswith('="') and cell.endswith('"'):
        cell = cell[2:-1]
    return cell.strip().strip('"').strip()


def _float_or_none(text: str) -> float | None:
    match = _NUMBER.search(text or "")
    return float(match.group()) if match else None


def parse_asd_csv(text: str, species: str) -> list[ReferenceLine]:
    """Parse ASD ``lines1.pl`` CSV output (format=2) into reference lines."""
    if "obs_wl" not in text and "ritz_wl" not in text:
        raise CalibrationError(
            f"NIST ASD returned no line table for {species!r} "
            "(check the species name and wavelength range)"
        )
    reader = csv.DictReader(io.StringIO(text))
    obs_key = next((k for k in reader.fieldnames or [] if k.startswith("obs_wl")), None)
    ritz_key = next((k for k in reader.fieldnames or [] if k.startswith("ritz_wl")), None)
    lines: list[ReferenceLine] = []
    for row in reader:
        observed = _float_or_none(_clean(row.get(obs_key, ""))) if obs_key else None
        ritz = _float_or_none(_clean(row.get(ritz_key, ""))) if ritz_key else None
        wavelength = ritz if ritz is not None else observed
        if wavelength is None:
            continue
        raw = _clean(row.get("intens", ""))
        lines.append(ReferenceLine(
            species=species,
            wavelength_nm=wavelength,
            observed_nm=observed,
            ritz_nm=ritz,
            intensity=_float_or_none(raw),
            intensity_raw=raw,
            aki_per_s=_float_or_none(_clean(row.get("Aki(s^-1)", ""))),
            accuracy=_clean(row.get("Acc", "")),
        ))
    lines.sort(key=lambda ln: ln.wavelength_nm)
    return lines


# --------------------------------------------------------------------- #
# Line files
# --------------------------------------------------------------------- #
def _fmt(value) -> str:
    return "" if value is None else repr(float(value))


def write_line_file(path: Path, species: str, lines, header: dict[str, str]) -> Path:
    """Write ``lines`` as a commented CSV. ``header`` becomes '# key: value' lines."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = io.StringIO()
    out.write(f"# species: {species}\n")
    for key, value in header.items():
        out.write(f"# {key}: {value}\n")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for ln in lines:
        writer.writerow([_fmt(ln.wavelength_nm), _fmt(ln.observed_nm), _fmt(ln.ritz_nm),
                         _fmt(ln.intensity), ln.intensity_raw, _fmt(ln.aki_per_s),
                         ln.accuracy])
    path.write_text(out.getvalue(), encoding="utf-8", newline="\n")
    return path


def read_header(path: Path) -> dict[str, str]:
    """The '# key: value' lines at the top of a line file."""
    header: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            break
        key, _, value = line[1:].partition(":")
        header[key.strip()] = value.strip()
    return header


def load_lines(species: str, *, observed_only: bool = True,
               low_nm: float | None = None, high_nm: float | None = None,
               data_dir: Path | None = None) -> list[ReferenceLine]:
    """Load one species' lines, sorted by wavelength.

    ``observed_only`` (default) drops lines ASD lists only as calculated (Ritz)
    transitions with no laboratory observation; those are rarely visible in a
    real lamp and only clutter a pick list.
    """
    folder = Path(data_dir) if data_dir is not None else DATA_DIR
    path = folder / species_to_filename(species)
    if not path.exists():
        raise CalibrationError(f"no reference line file for {species!r} ({path.name})")
    rows = [ln for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]
    lines = []
    for row in csv.DictReader(rows):
        lines.append(ReferenceLine(
            species=species,
            wavelength_nm=float(row["wavelength_nm"]),
            observed_nm=_float_or_none(row["observed_nm"]),
            ritz_nm=_float_or_none(row["ritz_nm"]),
            intensity=_float_or_none(row["intensity"]),
            intensity_raw=row.get("intensity_raw", ""),
            aki_per_s=_float_or_none(row.get("aki_per_s", "")),
            accuracy=row.get("accuracy", ""),
        ))
    if observed_only:
        lines = [ln for ln in lines if ln.observed]
    if low_nm is not None:
        lines = [ln for ln in lines if ln.wavelength_nm >= low_nm]
    if high_nm is not None:
        lines = [ln for ln in lines if ln.wavelength_nm <= high_nm]
    return sorted(lines, key=lambda ln: ln.wavelength_nm)


# --------------------------------------------------------------------- #
# Ranking helpers for pick lists
# --------------------------------------------------------------------- #
def strength_label(line: ReferenceLine, lines) -> str:
    """'very strong' / 'strong' / 'medium' / 'weak' by intensity rank among
    ``lines`` (the same species, same window). Empty when ASD gives none."""
    if line.intensity is None:
        return ""
    values = sorted(ln.intensity for ln in lines if ln.intensity is not None)
    if not values:
        return ""
    below = sum(1 for v in values if v < line.intensity)
    rank = below / max(len(values) - 1, 1)       # 0 = weakest, 1 = strongest
    if rank >= 0.9:
        return "very strong"
    if rank >= 0.7:
        return "strong"
    if rank >= 0.4:
        return "medium"
    return "weak"


def by_strength(lines) -> list[ReferenceLine]:
    """Strongest first; lines without an intensity go last, by wavelength."""
    return sorted(lines, key=lambda ln: (ln.intensity is None,
                                         -(ln.intensity or 0.0), ln.wavelength_nm))


def nearest(lines, wavelength_nm: float, count: int | None = None) -> list[ReferenceLine]:
    """Lines ordered by distance from ``wavelength_nm``."""
    ordered = sorted(lines, key=lambda ln: abs(ln.wavelength_nm - wavelength_nm))
    return ordered if count is None else ordered[:count]
