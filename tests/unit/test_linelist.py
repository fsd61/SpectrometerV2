"""Tests for the NIST line-list provider (:mod:`linelist`)."""

from pathlib import Path

import pytest

from errors import PersistenceError
from linelist import (
    LineList,
    Provenance,
    SpectralLine,
    WavelengthConvention,
    air_to_vacuum,
    boltzmann_intensities,
    load_line_list,
    parse_asd_lines,
    usable_lines,
    vacuum_to_air,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "nist_ar_i_sample.tsv"
AIR = WavelengthConvention.AIR
VACUUM = WavelengthConvention.VACUUM


# --------------------------------------------------------------------- air/vac

def test_known_ar_i_air_to_vacuum():
    # Ar I 811.5311 nm (air) is 811.7542 nm in vacuum per NIST ASD.
    assert air_to_vacuum(811.5311) == pytest.approx(811.7542, abs=5e-4)


def test_air_vacuum_round_trip_is_exact_to_a_picometre():
    for air in (600.0, 696.5431, 811.5311, 940.0):
        assert vacuum_to_air(air_to_vacuum(air)) == pytest.approx(air, abs=1e-6)


def test_conversion_offset_is_large_enough_to_matter():
    # ~0.22 nm at 810 nm — the same order as the instrument's best resolution,
    # which is why the convention is carried rather than assumed.
    assert 0.2 < air_to_vacuum(810.0) - 810.0 < 0.25


def test_conversion_rejects_nonpositive():
    with pytest.raises(ValueError):
        air_to_vacuum(0.0)


# ----------------------------------------------------------------------- parse

def test_parses_fixture_and_detects_air_convention():
    lines = load_line_list(FIXTURE)
    assert lines.convention is AIR
    assert len(lines) == 13                      # the all-blank row is skipped
    assert lines.species_present() == ["Ar I"]


def test_parser_tolerates_quotes_and_letter_codes():
    lines = load_line_list(FIXTURE)
    quoted = [l for l in lines if abs(l.wavelength_nm - 794.8176) < 1e-3]
    assert len(quoted) == 1
    assert quoted[0].aki_s == pytest.approx(1.86e7)
    assert quoted[0].relative_intensity == pytest.approx(2000.0)


def test_ritz_is_preferred_over_observed():
    lines = load_line_list(FIXTURE)
    line = next(l for l in lines if abs(l.wavelength_nm - 696.543) < 1e-2)
    assert line.wavelength_nm == pytest.approx(696.54308)
    assert line.observed_nm == pytest.approx(696.5431)


def test_missing_transition_data_is_none_not_zero():
    lines = load_line_list(FIXTURE)
    line = next(l for l in lines if abs(l.wavelength_nm - 866.7944) < 1e-2)
    assert line.aki_s is None
    assert not line.has_boltzmann_terms()


def test_vacuum_header_detected():
    text = "element\tsp_num\tobs_wl_vac(nm)\tritz_wl_vac(nm)\nAr\t1\t811.7542\t811.7542\n"
    assert parse_asd_lines(text).convention is VACUUM


def test_ambiguous_convention_raises_rather_than_guessing():
    text = "element\tsp_num\tobs_wl(nm)\nAr\t1\t811.5311\n"
    with pytest.raises(PersistenceError, match="convention"):
        parse_asd_lines(text)


def test_missing_wavelength_column_raises():
    with pytest.raises(PersistenceError, match="wavelength column"):
        parse_asd_lines("element\tsp_num\tintens\nAr\t1\t100\n")


def test_empty_input_raises():
    with pytest.raises(PersistenceError):
        parse_asd_lines("   \n\n")


def test_unreadable_path_raises_persistence_error():
    with pytest.raises(PersistenceError, match="cannot read"):
        load_line_list(FIXTURE.parent / "does_not_exist.tsv")


# ------------------------------------------------------------------- container

def test_lines_are_sorted_by_wavelength():
    lines = load_line_list(FIXTURE)
    assert lines.wavelengths() == sorted(lines.wavelengths())


def test_construction_rejects_mixed_conventions():
    with pytest.raises(ValueError, match="disagree"):
        LineList(
            lines=(
                SpectralLine(800.0, AIR),
                SpectralLine(810.0, VACUUM),
            ),
            convention=AIR,
        )


def test_filtered_by_band_and_species():
    lines = load_line_list(FIXTURE)
    band = lines.filtered(wavelength_min=750.0, wavelength_max=815.0)
    assert all(750.0 <= w <= 815.0 for w in band.wavelengths())
    assert len(band.filtered(species=["Kr I"])) == 0
    assert len(band.filtered(species=["ar i"])) == len(band)


def test_filter_preserves_provenance():
    lines = load_line_list(FIXTURE)
    assert lines.filtered(700.0, 800.0).provenance == lines.provenance


def test_fingerprint_changes_with_convention():
    lines = load_line_list(FIXTURE)
    assert lines.fingerprint() != lines.to_convention(VACUUM).fingerprint()


def test_fingerprint_changes_with_content():
    base = Provenance(source="a", content_sha256="deadbeef")
    other = Provenance(source="a", content_sha256="cafebabe")
    line = (SpectralLine(811.5311, AIR),)
    assert LineList(line, AIR, base).fingerprint() != LineList(line, AIR, other).fingerprint()


def test_describe_carries_identity_for_the_calibration_record():
    described = load_line_list(FIXTURE).describe()
    assert described["linelist_convention"] == "air"
    assert described["linelist_n_lines"] == 13
    assert len(described["linelist_sha256"]) == 64


def test_to_convention_is_identity_when_unchanged():
    lines = load_line_list(FIXTURE)
    assert lines.to_convention(AIR) is lines


# ------------------------------------------------------------------- intensity

def test_strongest_modelled_line_is_the_ar_i_811_nm():
    lines = load_line_list(FIXTURE).filtered(600.0, 940.0)
    wavelengths, amplitudes = usable_lines(lines, temperature_ev=1.0)
    strongest = wavelengths[amplitudes.index(max(amplitudes))]
    assert strongest == pytest.approx(811.5311, abs=1e-3)


def test_normalized_intensities_peak_at_one():
    lines = load_line_list(FIXTURE)
    values = [v for v in boltzmann_intensities(lines) if v is not None]
    assert max(values) == pytest.approx(1.0)
    assert all(0.0 < v <= 1.0 for v in values)


def test_lines_without_terms_are_dropped_not_defaulted():
    lines = load_line_list(FIXTURE)
    wavelengths, _ = usable_lines(lines)
    assert len(wavelengths) == len(lines) - 1
    assert not any(abs(w - 866.7944) < 1e-2 for w in wavelengths)


def test_hotter_plasma_favours_higher_upper_levels():
    lines = load_line_list(FIXTURE)
    cold = dict(zip(*usable_lines(lines, temperature_ev=0.5)))
    hot = dict(zip(*usable_lines(lines, temperature_ev=2.0)))
    # 696.5431 has the highest E_k in the fixture; relative to the 811 nm
    # reference line it must strengthen as temperature rises.
    assert hot[696.54308] > cold[696.54308]


def test_temperature_must_be_positive():
    lines = load_line_list(FIXTURE)
    with pytest.raises(ValueError):
        boltzmann_intensities(lines, temperature_ev=0.0)


# ----------------------------------------------------------------- integration

def test_feeds_the_synthetic_generator_and_peaks_come_back():
    """The payoff: real NIST positions in, recoverable peaks out."""
    import numpy as np
    from synthetic.generator import SyntheticSpectrumSpec, generate

    lines = load_line_list(FIXTURE).filtered(780.0, 850.0)
    wavelengths, amplitudes = usable_lines(lines, temperature_ev=1.0)

    spectrum = generate(
        SyntheticSpectrumSpec(
            center_wavelengths=wavelengths,
            amplitudes=[100.0 * a for a in amplitudes],
            fwhm=0.4,
            wavelength_min=780.0,
            wavelength_max=850.0,
            sample_interval=0.05,
            snr=200.0,
            seed=11,
        )
    )

    axis = np.asarray(spectrum.wavelengths)
    values = np.asarray(spectrum.intensities)
    for expected in wavelengths:
        window = np.abs(axis - expected) <= 0.5
        recovered = axis[window][int(np.argmax(values[window]))]
        assert recovered == pytest.approx(expected, abs=0.1)


def test_generator_metadata_can_carry_linelist_identity():
    from synthetic.generator import SyntheticSpectrumSpec, generate

    lines = load_line_list(FIXTURE).filtered(800.0, 820.0)
    wavelengths, amplitudes = usable_lines(lines)
    spectrum = generate(
        SyntheticSpectrumSpec(
            center_wavelengths=wavelengths,
            amplitudes=amplitudes,
            wavelength_min=800.0,
            wavelength_max=820.0,
            sample_interval=0.1,
        )
    )
    spectrum.metadata.update(lines.describe())
    assert spectrum.metadata["backend"] == "synthetic-generator"
    assert spectrum.metadata["linelist_convention"] == "air"


# ------------------------------------------------------------------ provenance

def test_sidecar_provenance_is_loaded(tmp_path):
    import json
    import shutil

    data = tmp_path / "ar_i.tsv"
    shutil.copy(FIXTURE, data)
    (tmp_path / "ar_i.tsv.provenance.json").write_text(
        json.dumps(
            {
                "source": "NIST ASD Lines, Ar I, 600-940 nm",
                "retrieved": "2026-08-24",
                "query": "https://physics.nist.gov/cgi-bin/ASD/lines1.pl?spectra=Ar+I",
                "notes": "air wavelengths; Ritz preferred",
            }
        ),
        encoding="utf-8",
    )
    lines = load_line_list(data)
    assert lines.provenance.retrieved == "2026-08-24"
    assert "ASD" in lines.provenance.source
    assert len(lines.provenance.content_sha256) == 64


def test_editing_the_pinned_file_changes_the_fingerprint(tmp_path):
    import shutil

    first = tmp_path / "a.tsv"
    shutil.copy(FIXTURE, first)
    original = load_line_list(first).fingerprint()

    second = tmp_path / "b.tsv"
    second.write_text(FIXTURE.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert load_line_list(second).fingerprint() != original


def test_corrupt_sidecar_raises(tmp_path):
    import shutil

    data = tmp_path / "ar_i.tsv"
    shutil.copy(FIXTURE, data)
    (tmp_path / "ar_i.tsv.provenance.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PersistenceError, match="cannot read"):
        load_line_list(data)


def test_provenance_absent_still_hashes_content(tmp_path):
    import shutil

    data = tmp_path / "bare.tsv"
    shutil.copy(FIXTURE, data)
    provenance = load_line_list(data).provenance
    assert provenance.source == "bare.tsv"
    assert provenance.retrieved == ""
    assert len(provenance.content_sha256) == 64
