"""Reference line lists (NIST ASD): parsing, files, and the shipped data."""

import pytest

from errors import CalibrationError
from reference import available_species, by_strength, load_lines, nearest, read_header, strength_label
from reference.lines import DATA_DIR, parse_asd_csv, write_line_file

# A trimmed copy of real ASD lines1.pl CSV output (format=2), including a
# calculated-only line (no observed wavelength or intensity) and a flagged
# intensity.
ASD_SAMPLE = (
    "obs_wl_air(nm),ritz_wl_air(nm),intens,Aki(s^-1),Acc,Ei(cm-1),Ek(cm-1),Type,\n"
    '"=""""","=""577.21143""","=""""","=""2.0e+05""",D,"=""1""","=""2""",,\n'
    '"=""810.3693""","=""810.36921""","=""20000""","=""2.5e+07""",B+,"=""1""","=""2""",,\n'
    '"=""811.5311""","=""811.53109""","=""35000""","=""3.31e+07""",AA,"=""1""","=""2""",,\n'
    '"=""763.5106""","=""""","=""25000h""","=""2.45e+07""",B+,"=""1""","=""2""",,\n'
)

# The FS-2 calibration set, Ar I, air, as used throughout the project.
FS2_ARGON = (696.543, 706.722, 738.398, 750.387, 751.465, 763.511, 794.818,
             800.616, 801.479, 810.369, 811.531, 826.452, 840.821, 842.465,
             852.144, 866.794, 912.297, 922.450)


def test_parse_asd_csv():
    lines = parse_asd_csv(ASD_SAMPLE, "Ar I")
    assert [round(ln.wavelength_nm, 3) for ln in lines] == [577.211, 763.511, 810.369, 811.531]
    calc_only, flagged = lines[0], lines[1]
    assert not calc_only.observed and calc_only.intensity is None
    assert flagged.ritz_nm is None and flagged.wavelength_nm == pytest.approx(763.5106)
    assert flagged.intensity == 25000 and flagged.intensity_raw == "25000h"
    assert lines[3].ritz_nm == pytest.approx(811.53109)       # Ritz preferred
    assert lines[3].accuracy == "AA"


def test_parse_rejects_error_page():
    with pytest.raises(CalibrationError):
        parse_asd_csv("<html>No lines are available</html>", "Xx I")


def test_file_round_trip(tmp_path):
    lines = parse_asd_csv(ASD_SAMPLE, "Ar I")
    write_line_file(tmp_path / "Ar_I.csv", "Ar I", lines, {"retrieved": "2026-11-09"})
    assert read_header(tmp_path / "Ar_I.csv") == {"species": "Ar I", "retrieved": "2026-11-09"}
    assert available_species(tmp_path) == ["Ar I"]
    every = load_lines("Ar I", observed_only=False, data_dir=tmp_path)
    assert every == lines
    observed = load_lines("Ar I", data_dir=tmp_path)
    assert len(observed) == 3
    assert [ln.wavelength_nm for ln in load_lines("Ar I", low_nm=800, high_nm=811,
                                                  data_dir=tmp_path)] == [810.36921]


def test_missing_species_raises(tmp_path):
    with pytest.raises(CalibrationError):
        load_lines("Ar I", data_dir=tmp_path)


def test_ranking_helpers():
    lines = [ln for ln in parse_asd_csv(ASD_SAMPLE, "Ar I") if ln.observed]
    top = by_strength(lines)[0]
    assert top.wavelength_nm == pytest.approx(811.53109)
    assert strength_label(top, lines) == "very strong"
    assert nearest(lines, 811.2, 1)[0].wavelength_nm == pytest.approx(811.53109)


# --------------------------------------------------------------------- #
# The shipped data files
# --------------------------------------------------------------------- #
def test_shipped_species():
    species = available_species()
    assert species[0] == "Ar I"
    for expected in ("Hg I", "Ne I", "Na I"):
        assert expected in species


def test_shipped_argon_contains_fs2_calibration_lines():
    lines = load_lines("Ar I")
    for target in FS2_ARGON:
        assert any(abs(ln.wavelength_nm - target) < 0.002 for ln in lines), target
    header = read_header(DATA_DIR / "Ar_I.csv")
    assert "NIST" in header["source"] and header["medium"].startswith("air")


def test_shipped_sodium_d_and_mercury_yellow():
    na = [ln.wavelength_nm for ln in load_lines("Na I")]
    assert any(abs(w - 588.995) < 0.002 for w in na)
    assert any(abs(w - 589.592) < 0.002 for w in na)
    hg = [ln.wavelength_nm for ln in load_lines("Hg I")]
    assert any(abs(w - 576.960) < 0.002 for w in hg)
    assert any(abs(w - 579.066) < 0.002 for w in hg)


# --------------------------------------------------------------------- #
# The ASD version stamp
# --------------------------------------------------------------------- #
def _fetch_script():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "fetch_nist_lines.py"
    spec = importlib.util.spec_from_file_location("fetch_nist_lines", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_asd_version():
    script = _fetch_script()
    page = ('Reader,&nbsp;J. and <a href="#Team">NIST ASD Team</a> (2024).\n'
            '  <i>NIST Atomic Spectra Database</i> (version&nbsp;5.12),\n'
            '  ... <b>Version&nbsp;5.11</b> ... CODATA (Web Version 9.0)')
    assert script.parse_asd_version(page) == "5.12"
    assert script.parse_asd_version("<html>nothing here</html>") == "unknown"


def test_shipped_files_record_asd_version():
    for species in available_species():
        header = read_header(DATA_DIR / (species.replace(" ", "_") + ".csv"))
        assert header.get("asd_version", "unknown") != "unknown", species


# --------------------------------------------------------------------- #
# Line identification
# --------------------------------------------------------------------- #
def test_refine_peak_finds_subpixel_center():
    import numpy as np

    from reference import refine_peak

    x = np.arange(40, dtype=float)
    y = 100.0 * np.exp(-0.5 * ((x - 20.3) / 1.7) ** 2)
    assert refine_peak(y, 20) == pytest.approx(20.3, abs=0.05)
    assert refine_peak(y, 0) == 0.0                     # edge: unchanged
    assert refine_peak([1.0, 1.0, 1.0], 1) == 1.0       # flat: unchanged


def test_wavelength_at_interpolates():
    from reference import wavelength_at

    wl = [600.0 + 0.266 * i for i in range(1280)]
    assert wavelength_at(wl, 793.5) == pytest.approx(600.0 + 0.266 * 793.5)


def test_identify_argon_doublet():
    from reference import identify

    found = identify(811.40, ["Ar I", "Ne I"], tolerance_nm=1.5)
    assert found[0].species == "Ar I"
    assert found[0].wavelength_nm == pytest.approx(811.53109)
    assert found[0].delta_nm == pytest.approx(0.13109, abs=1e-6)
    assert found[0].strength == "very strong"
    assert any(c.wavelength_nm == pytest.approx(810.36921) for c in found)
    deltas = [abs(c.delta_nm) for c in found]
    assert deltas == sorted(deltas)                      # nearest first
    assert all(d <= 1.5 for d in deltas)


def test_identify_edge_cases(tmp_path):
    from reference import identify

    assert identify(811.4, [], 1.0) == []                # nothing ticked
    assert identify(811.4, ["Zz I"], 1.0) == []          # unknown species skipped
    assert identify(811.4, ["Ar I"], 0.01) == []         # nothing that close
