"""Unit tests for the persistence sinks (DATA-001/002)."""

from processing.spectrum import Spectrum
from data.sinks import CsvSpectrumSink, NullSink, read_csv_spectrum


def test_csv_roundtrip_calibrated(tmp_path):
    sp = Spectrum(wavelengths=[400.0, 400.5, 401.0], intensities=[1.0, 5.0, 2.0],
                  metadata={"source": "x", "seed": 3})
    p = CsvSpectrumSink(tmp_path).write(sp, name="s")
    assert p.name == "s.csv" and (tmp_path / "s.meta.json").exists()
    assert open(p).readline().strip() == "Wavelength,Intensity"
    sp2 = read_csv_spectrum(p)
    assert sp2.wavelengths == [400.0, 400.5, 401.0]
    assert sp2.intensities == [1.0, 5.0, 2.0]
    assert sp2.metadata["seed"] == 3


def test_csv_uncalibrated_uses_pixel_header(tmp_path):
    sp = Spectrum(wavelengths=[], intensities=[10.0, 20.0, 30.0], metadata={})
    p = CsvSpectrumSink(tmp_path).write(sp, name="p")
    assert open(p).readline().strip() == "Pixel,Intensity"
    sp2 = read_csv_spectrum(p)
    assert sp2.wavelengths == [] and sp2.intensities == [10.0, 20.0, 30.0]


def test_nullsink_returns_none():
    assert NullSink().write(Spectrum(wavelengths=[], intensities=[1.0], metadata={})) is None


def test_auto_name_when_none(tmp_path):
    p = CsvSpectrumSink(tmp_path).write(Spectrum(wavelengths=[], intensities=[1.0, 2.0], metadata={}))
    assert p.exists() and p.suffix == ".csv"


def test_write_metadata_false_skips_json(tmp_path):
    p = CsvSpectrumSink(tmp_path, write_metadata=False).write(
        Spectrum(wavelengths=[], intensities=[1.0], metadata={"a": 1}), name="n")
    assert not (tmp_path / "n.meta.json").exists()
