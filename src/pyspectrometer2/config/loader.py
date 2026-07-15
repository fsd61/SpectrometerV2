"""Configuration loader and validator (CFG-002, CFG-003, CFG-005, CFG-006).

Resolution order (later overrides earlier):
    1. Schema defaults.
    2. Base INI file (``--config``), if provided.
    3. Profile overlay (``--profile NAME`` -> ``<config_dir>/profiles/NAME.ini``).
    4. Command-line overrides (``--set section.key=value``), which never modify
       any file on disk (CFG-006).

All type/choice/range problems and unknown sections/keys are collected and
reported together, then raised as a single ``ConfigError`` so the application
can terminate gracefully with meaningful diagnostics (CFG-005).
"""

from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from ..errors import ConfigError
from .schema import SCHEMA, Field

_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}


class Config:
    """Validated, typed view of configuration values."""

    def __init__(self, data: Mapping[str, Mapping[str, Any]]):
        self._data = {s: dict(v) for s, v in data.items()}

    def get(self, section: str, key: str) -> Any:
        try:
            return self._data[section][key]
        except KeyError as exc:
            raise ConfigError(f"No such config value: [{section}] {key}") from exc

    def section(self, section: str) -> dict[str, Any]:
        return dict(self._data.get(section, {}))

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return {s: dict(v) for s, v in self._data.items()}

    def __getitem__(self, section: str) -> dict[str, Any]:
        return self.section(section)


def load_config(
    config_path: Optional[str | Path] = None,
    profile: Optional[str] = None,
    overrides: Optional[Iterable[str]] = None,
) -> Config:
    """Load, layer, and validate configuration. See module docstring."""
    # Layer 1: schema defaults (stored as raw strings for uniform coercion).
    raw: dict[str, dict[str, str]] = {
        section: {key: _to_raw(field.default) for key, field in keys.items()}
        for section, keys in SCHEMA.items()
    }

    errors: list[str] = []

    # Layer 2: base config file.
    if config_path is not None:
        _overlay_file(Path(config_path), raw, errors, required=True)

    # Layer 3: profile overlay.
    if profile:
        base_dir = Path(config_path).parent if config_path else Path("config")
        profile_path = base_dir / "profiles" / f"{profile}.ini"
        _overlay_file(profile_path, raw, errors, required=True, what=f"profile '{profile}'")

    # Layer 4: CLI overrides (CFG-006).
    if overrides:
        _apply_overrides(overrides, raw, errors)

    # Validate + coerce everything against the schema.
    typed = _coerce_all(raw, errors)

    if errors:
        raise ConfigError(
            "Invalid configuration:\n  - " + "\n  - ".join(errors)
        )
    return Config(typed)


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _to_raw(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _overlay_file(path: Path, raw: dict, errors: list, *, required: bool, what: str = "configuration file") -> None:
    if not path.exists():
        if required:
            errors.append(f"{what} not found: {path}")
        return
    parser = configparser.ConfigParser()
    try:
        read_ok = parser.read(path, encoding="utf-8")
    except configparser.Error as exc:
        errors.append(f"Could not parse {path}: {exc}")
        return
    if not read_ok:
        errors.append(f"Could not read {what}: {path}")
        return
    for section in parser.sections():
        for key, value in parser.items(section):
            raw.setdefault(section, {})[key] = value


def _apply_overrides(overrides: Iterable[str], raw: dict, errors: list) -> None:
    for item in overrides:
        if "=" not in item or "." not in item.split("=", 1)[0]:
            errors.append(f"Malformed override (expected section.key=value): {item!r}")
            continue
        location, value = item.split("=", 1)
        section, key = location.split(".", 1)
        raw.setdefault(section.strip(), {})[key.strip()] = value.strip()


def _coerce_all(raw: dict, errors: list) -> dict:
    typed: dict[str, dict[str, Any]] = {}
    for section, keys in raw.items():
        if section not in SCHEMA:
            errors.append(f"Unknown configuration section: [{section}]")
            continue
        typed[section] = {}
        for key, value in keys.items():
            field = SCHEMA[section].get(key)
            if field is None:
                errors.append(f"Unknown key in [{section}]: {key}")
                continue
            typed[section][key] = _coerce(field, value, f"[{section}] {key}", errors)
    return typed


def _coerce(field: Field, raw_value: Any, where: str, errors: list) -> Any:
    try:
        if field.type == "int":
            value: Any = int(str(raw_value))
        elif field.type == "float":
            value = float(str(raw_value))
        elif field.type == "bool":
            token = str(raw_value).strip().lower()
            if token in _BOOL_TRUE:
                value = True
            elif token in _BOOL_FALSE:
                value = False
            else:
                raise ValueError(f"expected boolean, got {raw_value!r}")
        elif field.type == "path":
            value = Path(str(raw_value))
        else:
            value = str(raw_value)
    except (ValueError, TypeError) as exc:
        errors.append(f"{where}: {exc}")
        return None

    if field.choices is not None and value not in field.choices:
        errors.append(f"{where}: {value!r} is not one of {list(field.choices)}")
    if field.min is not None and isinstance(value, (int, float)) and not isinstance(value, bool) and value < field.min:
        errors.append(f"{where}: {value} is below minimum {field.min}")
    if field.max is not None and isinstance(value, (int, float)) and not isinstance(value, bool) and value > field.max:
        errors.append(f"{where}: {value} is above maximum {field.max}")
    return value
