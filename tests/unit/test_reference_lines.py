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
