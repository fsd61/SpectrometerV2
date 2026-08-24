"""Parser for NIST Atomic Spectra Database (ASD) line exports.

Reads the tab-delimited "Lines" output from the ASD web form (``format=3``) or
an equivalent CSV. The parser is deliberately tolerant of ASD's presentation
quirks — quoted fields, bracketed or daggered values, ``?`` accuracy markers,
letter codes appended to intensities, blank columns for lines lacking
transition probabilities — because rejecting a whole atlas over one annotated
row is the wrong failure mode.

**The convention is read from the file, not assumed.** ASD names its wavelength
columns ``obs_wl_air(nm)`` or ``obs_wl_vac(nm)``, so the export declares whether
it is air or vacuum. If a file gives no such signal the parser raises rather
than guessing, since guessing wrong is a ~0.2 nm error that would otherwise
propagate silently into a wavelength solution.

Fetching is out of scope: point this at a **pinned local export**. An atlas that
changes underneath a stored calibration is precisely what
:meth:`linelist.records.LineList.fingerprint` exists to detect.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Optional

from errors import PersistenceError

from .records import LineList, Provenance, SpectralLine, WavelengthConvention

#: Header synonyms -> canonical field. Compared after lowercasing and stripping.
_COLUMNS = {
    "obs_wl_air(nm)": "observed", "obs_wl_vac(nm)": "observed",
    "obs_wl(nm)": "observed", "observed": "observed", "obs_wl": "observed",
    "ritz_wl_air(nm)": "ritz", "ritz_wl_vac(nm)": "ritz",
    "ritz_wl(nm)": "ritz", "ritz": "ritz",
    "intens": "intensity", "rel_int": "intensity", "rel. int.": "intensity",
    "intensity": "intensity",
    "aki(s^-1)": "aki", "aki": "aki", "a_ki": "aki",
    "ei(ev)": "e_lower", "ek(ev)": "e_upper",
    "ei(cm-1)": "e_lower_cm", "ek(cm-1)": "e_upper_cm",
    "g_i": "g_lower", "gi": "g_lower", "g_k": "g_upper", "gk": "g_upper",
    "element": "element", "sp_num": "sp_num", "spectrum": "species",
}

#: ASD annotates values with these; they carry no numeric information.
_NOISE = re.compile(r"[\"'\[\]()*+?:=<>~]|(?<=\d)\s*[a-zA-Z]+\s*$")
_CM1_PER_EV = 8065.543937


def _clean(cell: str) -> str:
    return cell.replace("﻿", "").strip().strip('"').strip()


def _number(cell: str) -> Optional[float]:
    """Coerce an ASD cell to a float, or ``None`` if it carries no value."""
    text = _NOISE.sub("", _clean(cell)).replace(",", "").strip()
    if not text or text in {"-", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _roman(number: int) -> str:
    numerals = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out, n = "", number
    for value, symbol in numerals:
        while n >= value:
            out += symbol
            n -= value
    return out or str(number)


def _detect_convention(header: list[str]) -> WavelengthConvention:
    joined = " ".join(header)
    air, vac = "_air" in joined, "_vac" in joined
    if air and not vac:
        return WavelengthConvention.AIR
    if vac and not air:
        return WavelengthConvention.VACUUM
    raise PersistenceError(
        "cannot determine the wavelength convention from the ASD header "
        f"({header!r}); re-export with the air/vacuum columns intact, or "
        "construct the LineList explicitly with the convention you know applies"
    )


def parse_asd_lines(
    text: str,
    convention: Optional[WavelengthConvention] = None,
    provenance: Optional[Provenance] = None,
) -> LineList:
    """Parse ASD tab-delimited (or CSV) line output into a :class:`LineList`."""
    rows = [r for r in text.splitlines() if r.strip() and not r.lstrip().startswith("#")]
    if not rows:
        raise PersistenceError("line list is empty")

    delimiter = "\t" if "\t" in rows[0] else ","
    header = [_clean(c).lower() for c in rows[0].split(delimiter)]
    mapping = {i: _COLUMNS[name] for i, name in enumerate(header) if name in _COLUMNS}
    if "observed" not in mapping.values() and "ritz" not in mapping.values():
        raise PersistenceError(
            f"no wavelength column found in ASD header: {header!r}"
        )
    if convention is None:
        convention = _detect_convention(header)

    lines = []
    for row in rows[1:]:
        cells = row.split(delimiter)
        record: dict = {}
        for index, key in mapping.items():
            if index < len(cells):
                record[key] = cells[index]

        ritz = _number(record.get("ritz", ""))
        observed = _number(record.get("observed", ""))
        wavelength = ritz if ritz is not None else observed
        if wavelength is None:
            continue                                    # annotation-only row

        species = _clean(record.get("species", ""))
        if not species:
            element = _clean(record.get("element", ""))
            stage = _number(record.get("sp_num", ""))
            if element:
                species = f"{element} {_roman(int(stage))}" if stage else element

        e_lower = _number(record.get("e_lower", ""))
        e_upper = _number(record.get("e_upper", ""))
        if e_lower is None and record.get("e_lower_cm"):
            value = _number(record["e_lower_cm"])
            e_lower = value / _CM1_PER_EV if value is not None else None
        if e_upper is None and record.get("e_upper_cm"):
            value = _number(record["e_upper_cm"])
            e_upper = value / _CM1_PER_EV if value is not None else None

        lines.append(
            SpectralLine(
                wavelength_nm=wavelength,
                convention=convention,
                species=species,
                observed_nm=observed,
                ritz_nm=ritz,
                relative_intensity=_number(record.get("intensity", "")),
                aki_s=_number(record.get("aki", "")),
                e_lower_ev=e_lower,
                e_upper_ev=e_upper,
                g_lower=_number(record.get("g_lower", "")),
                g_upper=_number(record.get("g_upper", "")),
            )
        )

    if not lines:
        raise PersistenceError("ASD export contained no parsable lines")
    return LineList(tuple(lines), convention, provenance or Provenance())


def load_line_list(
    path: str | Path,
    convention: Optional[WavelengthConvention] = None,
) -> LineList:
    """Load a pinned ASD export, hashing its bytes into the provenance record.

    A sibling ``<name>.provenance.json`` — if present — supplies ``source``,
    ``retrieved``, ``query`` and ``notes``. It is optional, but a line list
    without it can only say *what* it contains, never *where it came from*.
    """
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PersistenceError(f"cannot read line list {path}: {exc}") from exc

    digest = hashlib.sha256(raw).hexdigest()
    sidecar = path.with_suffix(path.suffix + ".provenance.json")
    fields = {"source": str(path.name), "content_sha256": digest}
    if sidecar.is_file():
        try:
            declared = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PersistenceError(f"cannot read {sidecar}: {exc}") from exc
        for key in ("source", "retrieved", "query", "notes"):
            if declared.get(key):
                fields[key] = str(declared[key])

    return parse_asd_lines(
        raw.decode("utf-8-sig", errors="replace"),
        convention=convention,
        provenance=Provenance(**fields),
    )
