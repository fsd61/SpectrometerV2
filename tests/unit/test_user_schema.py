"""Tests for the user field manifest (data.user_schema).

The manifest is the only sanctioned way to extend persistence, so these tests
concentrate on the two things it must never allow: shadowing the locked core,
and declaring an InfluxDB tag with unbounded cardinality.
"""

import pytest

from data.user_schema import UserSchema, load_manifest, load_hook, parse_manifest
from errors import ConfigError, PersistenceError
from processing.spectrum import Spectrum


def _spec(**meta):
    return Spectrum(wavelengths=[400.0, 500.0], intensities=[1.0, 2.0], metadata=meta)


# --------------------------------------------------------------------------- #
# Parsing and validation
# --------------------------------------------------------------------------- #
def test_parses_a_minimal_manifest():
    schema = parse_manifest(
        """
        [bench_humidity]
        type = float
        unit = %RH
        doc  = Ambient RH.
        """
    )
    assert len(schema) == 1
    field = schema.fields[0]
    assert field.name == "bench_humidity"
    assert field.type == "float" and field.unit == "%RH"
    assert field.store == "both" and field.role == "field"   # defaults
    assert field.sql_type == "REAL"


def test_reserved_core_names_are_rejected():
    """The core schema is locked: users cannot redefine provenance fields."""
    for name in ("backend", "calibration_id", "source", "n_samples", "uuid"):
        with pytest.raises(ConfigError, match="reserved by the core schema"):
            parse_manifest(f"[{name}]\ntype = str\n")


def test_tag_without_allowed_list_is_rejected():
    """The cardinality guard: an unbounded tag would create a series per point."""
    with pytest.raises(ConfigError, match="requires an 'allowed' list"):
        parse_manifest("[operator]\ntype = str\nrole = tag\n")


def test_tag_with_allowed_list_is_accepted():
    schema = parse_manifest(
        "[operator]\ntype = str\nrole = tag\nallowed = frank, unattended\n"
    )
    assert schema.fields[0].allowed == ("frank", "unattended")
    assert [f.name for f in schema.influx_tags()] == ["operator"]


def test_tag_must_be_a_string():
    with pytest.raises(ConfigError, match="requires type=str"):
        parse_manifest("[shots]\ntype = int\nrole = tag\nallowed = 1, 2\n")


def test_tag_is_meaningless_for_sqlite_only():
    with pytest.raises(ConfigError, match="meaningless with store=sqlite"):
        parse_manifest(
            "[operator]\ntype = str\nrole = tag\nstore = sqlite\nallowed = frank\n"
        )


def test_bad_names_types_and_keys_are_rejected():
    with pytest.raises(ConfigError, match="field names must be lowercase"):
        parse_manifest("[Bench Humidity]\ntype = float\n")
    with pytest.raises(ConfigError, match="type must be one of"):
        parse_manifest("[foo]\ntype = complex\n")
    with pytest.raises(ConfigError, match="unknown key"):
        parse_manifest("[foo]\ntype = float\nwidget = yes\n")


def test_all_problems_reported_together():
    """Same discipline as the config loader: collect, then raise once."""
    with pytest.raises(ConfigError) as excinfo:
        parse_manifest("[backend]\ntype = zzz\n\n[operator]\ntype = str\nrole = tag\n")
    message = str(excinfo.value)
    assert "reserved by the core schema" in message
    assert "type must be one of" in message
    assert "requires an 'allowed' list" in message


def test_missing_manifest_file_is_not_an_error(tmp_path):
    """Core schema alone is a valid configuration."""
    schema = load_manifest(tmp_path / "nope.ini")
    assert len(schema) == 0
    assert load_manifest("") is not None and len(load_manifest("")) == 0


def test_fingerprint_is_stable_and_order_independent():
    a = parse_manifest("[alpha]\ntype = int\n\n[beta]\ntype = str\n")
    b = parse_manifest("[beta]\ntype = str\n\n[alpha]\ntype = int\n")
    assert a.fingerprint() == b.fingerprint()

    changed = parse_manifest("[alpha]\ntype = float\n\n[beta]\ntype = str\n")
    assert changed.fingerprint() != a.fingerprint()


# --------------------------------------------------------------------------- #
# Value resolution
# --------------------------------------------------------------------------- #
def test_from_path_pulls_an_existing_metadata_value():
    """The zero-code case: declare where it goes, name where it comes from."""
    schema = parse_manifest("[sensor_gain]\ntype = float\nfrom = frame.gain\n")
    values = schema.resolve(_spec(frame={"gain": 2.5}))
    assert values == {"sensor_gain": 2.5}


def test_missing_value_is_simply_absent():
    schema = parse_manifest("[sensor_gain]\ntype = float\nfrom = frame.gain\n")
    assert schema.resolve(_spec(frame={})) == {}


def test_hook_output_is_validated_and_coerced():
    schema = parse_manifest("[bench_temp_c]\ntype = float\n")
    values = schema.resolve(_spec(), hook=lambda spectrum: {"bench_temp_c": "21.5"})
    assert values == {"bench_temp_c": 21.5}


def test_undeclared_hook_key_is_surfaced_not_dropped():
    """Silent drops are the failure mode this design exists to prevent."""
    schema = parse_manifest("[bench_temp_c]\ntype = float\n")
    with pytest.raises(PersistenceError, match="undeclared field 'humidity'"):
        schema.resolve(_spec(), hook=lambda s: {"bench_temp_c": 1.0, "humidity": 40})


def test_wrong_type_is_rejected():
    schema = parse_manifest("[shots]\ntype = int\n")
    with pytest.raises(PersistenceError, match="expected int"):
        schema.resolve(_spec(user_fields={"shots": "many"}))


def test_value_outside_allowed_is_rejected():
    schema = parse_manifest(
        "[grating]\ntype = str\nrole = tag\nallowed = 1000lpmm, 1200lpmm\n"
    )
    with pytest.raises(PersistenceError, match="not one of"):
        schema.resolve(_spec(user_fields={"grating": "600lpmm"}))


def test_on_violation_warn_drops_and_continues(caplog):
    schema = parse_manifest("[shots]\ntype = int\n\n[label]\ntype = str\n")
    values = schema.resolve(
        _spec(user_fields={"shots": "many", "label": "ok"}), on_violation="warn"
    )
    assert values == {"label": "ok"}          # good value survives
    assert "expected int" in caplog.text


def test_on_violation_drop_is_silent(caplog):
    schema = parse_manifest("[shots]\ntype = int\n")
    assert schema.resolve(_spec(user_fields={"shots": "many"}), on_violation="drop") == {}
    assert caplog.text == ""


def test_unknown_on_violation_is_rejected():
    with pytest.raises(ConfigError, match="on_violation must be"):
        UserSchema().resolve(_spec(), on_violation="explode")


def test_bools_are_not_silently_numeric():
    schema = parse_manifest("[shots]\ntype = int\n")
    with pytest.raises(PersistenceError, match="expected int, got boolean"):
        schema.resolve(_spec(user_fields={"shots": True}))


# --------------------------------------------------------------------------- #
# Hook loading
# --------------------------------------------------------------------------- #
def test_load_hook_resolves_a_callable():
    hook = load_hook("json:dumps")
    assert callable(hook)
    assert load_hook("") is None


def test_load_hook_rejects_bad_specs():
    with pytest.raises(ConfigError, match="must be 'module:function'"):
        load_hook("json.dumps")
    with pytest.raises(ConfigError, match="cannot import hook module"):
        load_hook("no_such_module_xyz:f")
    with pytest.raises(ConfigError, match="is not a callable"):
        load_hook("json:not_a_real_attribute")
