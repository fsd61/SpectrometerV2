"""User-declared field manifest — the sanctioned way to extend persistence.

The core schema (:mod:`data.schema_core`) is closed. Everything a user wants to
collect *beyond* it is declared in a small INI manifest, kept deliberately
outside ``config.ini`` because the main configuration loader is closed-world:
it rejects unknown sections and keys, which is what keeps the core locked.

One declaration serves both stores. A field becomes a typed column in the
SQLite ``capture_ext`` table (via a generated migration) *and* an InfluxDB
field or tag, so users describe intent once::

    # config/user_fields.ini

    [bench_humidity]
    type    = float
    unit    = %RH
    store   = both
    doc     = Ambient relative humidity at the optical bench.

    [operator]
    type    = str
    role    = tag
    allowed = frank, catherine, unattended
    doc     = Who ran the capture.

    [sensor_gain]
    type    = float
    from    = frame.gain          ; pull a value already in metadata
    doc     = Camera gain reported by the adapter.

Two rules do real work:

**``role = tag`` requires an ``allowed`` list.** An InfluxDB tag is indexed;
a tag whose value varies per capture creates one series per capture and
destroys the database. Requiring an enumerated domain makes unbounded
cardinality unrepresentable rather than merely discouraged.

**``from`` makes the zero-code case work.** A manifest declares *where a value
goes*, not where it comes from. When the value already flows through the
pipeline, ``from`` names its dotted path in ``Spectrum.metadata`` and no user
code is needed. For genuinely new quantities the user supplies a hook
(``[user_schema] hook = mypkg.mymod:collect``) returning a dict per capture,
which is then validated against these declarations — unknown keys and wrong
types are surfaced, not silently dropped.
"""

from __future__ import annotations

import configparser
import hashlib
import importlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from errors import ConfigError, PersistenceError

from .schema_core import RESERVED_NAMES

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

TYPES = ("int", "float", "bool", "str")
STORES = ("sqlite", "influx", "both")
ROLES = ("field", "tag")

#: Manifest type -> SQLite column affinity.
_SQL_TYPE = {"int": "INTEGER", "float": "REAL", "bool": "INTEGER", "str": "TEXT"}

_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}

_VALID_KEYS = {"type", "unit", "store", "role", "from", "allowed", "doc"}


@dataclass(frozen=True)
class UserField:
    """One user-declared field."""

    name: str
    type: str
    store: str = "both"
    role: str = "field"
    unit: str = ""
    source_path: str = ""          # dotted path into Spectrum.metadata ("from")
    allowed: tuple = ()
    doc: str = ""

    @property
    def sql_type(self) -> str:
        return _SQL_TYPE[self.type]

    def goes_to_sqlite(self) -> bool:
        return self.store in ("sqlite", "both")

    def goes_to_influx(self) -> bool:
        return self.store in ("influx", "both")

    def canonical(self) -> dict:
        """Stable representation used for the manifest fingerprint."""
        return {
            "name": self.name, "type": self.type, "store": self.store,
            "role": self.role, "unit": self.unit, "from": self.source_path,
            "allowed": list(self.allowed),
        }


class UserSchema:
    """A validated set of :class:`UserField` declarations."""

    def __init__(self, fields: Sequence[UserField] = (), path: Optional[Path] = None):
        self._fields = tuple(fields)
        self._by_name = {f.name: f for f in self._fields}
        self.path = path

    # -- introspection ---------------------------------------------------- #
    def __len__(self) -> int:
        return len(self._fields)

    def __iter__(self):
        return iter(self._fields)

    def __contains__(self, name) -> bool:
        return name in self._by_name

    @property
    def fields(self) -> tuple:
        return self._fields

    def sqlite_fields(self) -> tuple:
        return tuple(f for f in self._fields if f.goes_to_sqlite())

    def influx_fields(self) -> tuple:
        return tuple(f for f in self._fields if f.goes_to_influx() and f.role == "field")

    def influx_tags(self) -> tuple:
        return tuple(f for f in self._fields if f.goes_to_influx() and f.role == "tag")

    def fingerprint(self) -> str:
        """Stable hash of the declarations; changes force a schema check."""
        payload = json.dumps(
            [f.canonical() for f in sorted(self._fields, key=lambda x: x.name)],
            sort_keys=True, separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    # -- value resolution -------------------------------------------------- #
    def resolve(
        self,
        spectrum,
        hook: Optional[Callable] = None,
        on_violation: str = "error",
    ) -> dict:
        """Collect and validate this capture's user values.

        Returns ``{name: coerced_value}``, omitting fields with no value
        available. ``on_violation`` selects what happens on a type error, a
        value outside ``allowed``, or an undeclared key returned by ``hook``:
        ``error`` raises, ``warn`` logs and drops, ``drop`` drops silently.
        """
        if on_violation not in ("error", "warn", "drop"):
            raise ConfigError(
                f"[user_schema] on_violation must be one of error/warn/drop, "
                f"got {on_violation!r}"
            )
        metadata = dict(spectrum.metadata or {})
        supplied: dict = dict(metadata.get("user_fields") or {})

        if hook is not None:
            produced = hook(spectrum)
            if produced is None:
                produced = {}
            if not isinstance(produced, Mapping):
                raise PersistenceError(
                    f"user_schema hook must return a mapping, got {type(produced).__name__}"
                )
            supplied.update(produced)

        problems: list = []
        # An undeclared key is a mistake worth surfacing: the user believes
        # they are collecting something that would otherwise vanish silently.
        for key in supplied:
            if key not in self._by_name:
                problems.append(
                    f"value supplied for undeclared field {key!r} "
                    f"(add a [{key}] section to the manifest)"
                )

        out: dict = {}
        for field in self._fields:
            raw = (
                _dotted_get(metadata, field.source_path)
                if field.source_path
                else supplied.get(field.name)
            )
            if raw is None:
                continue
            try:
                out[field.name] = _coerce_value(field, raw)
            except ValueError as exc:
                problems.append(f"[{field.name}] {exc}")

        if problems:
            message = "user field violations:\n  - " + "\n  - ".join(problems)
            if on_violation == "error":
                raise PersistenceError(message)
            if on_violation == "warn":
                logger.warning("%s", message)
        return out


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _dotted_get(mapping: Mapping, path: str):
    """Fetch ``a.b.c`` from nested mappings; ``None`` if any hop is missing."""
    node: Any = mapping
    for part in path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node


def _coerce_value(field: UserField, raw):
    """Coerce ``raw`` to the declared type, enforcing ``allowed``."""
    if field.type == "bool":
        if isinstance(raw, bool):
            value: Any = raw
        else:
            token = str(raw).strip().lower()
            if token in _BOOL_TRUE:
                value = True
            elif token in _BOOL_FALSE:
                value = False
            else:
                raise ValueError(f"expected boolean, got {raw!r}")
    elif field.type == "int":
        if isinstance(raw, bool):
            raise ValueError(f"expected int, got boolean {raw!r}")
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise ValueError(f"expected int, got {raw!r}") from None
    elif field.type == "float":
        if isinstance(raw, bool):
            raise ValueError(f"expected float, got boolean {raw!r}")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"expected float, got {raw!r}") from None
    else:
        value = str(raw)

    if field.allowed and str(value) not in field.allowed:
        raise ValueError(
            f"{value!r} is not one of {list(field.allowed)}"
        )
    return value


def parse_manifest(text: str, path: Optional[Path] = None) -> UserSchema:
    """Parse and validate a manifest. All problems are reported together."""
    # interpolation=None is required, not cosmetic: units and docs are free text
    # and legitimately contain '%' (e.g. unit = %RH), which the default
    # BasicInterpolation would treat as a broken substitution and reject.
    parser = configparser.ConfigParser(interpolation=None)
    # Preserve case in values but keep keys lowercase (configparser default).
    try:
        parser.read_string(text)
    except configparser.Error as exc:
        raise ConfigError(f"cannot parse user field manifest ({path}): {exc}") from exc

    errors: list = []
    fields: list = []

    for name in parser.sections():
        section = parser[name]
        unknown = set(section.keys()) - _VALID_KEYS
        if unknown:
            errors.append(
                f"[{name}]: unknown key(s) {sorted(unknown)}; "
                f"valid keys are {sorted(_VALID_KEYS)}"
            )
        if not _NAME_RE.match(name):
            errors.append(
                f"[{name}]: field names must be lowercase letters, digits and "
                f"underscores, starting with a letter"
            )
        if name in RESERVED_NAMES:
            errors.append(
                f"[{name}]: reserved by the core schema and cannot be redeclared"
            )

        ftype = section.get("type", "").strip().lower()
        if ftype not in TYPES:
            errors.append(f"[{name}]: type must be one of {list(TYPES)}, got {ftype or '(missing)'!r}")

        store = section.get("store", "both").strip().lower()
        if store not in STORES:
            errors.append(f"[{name}]: store must be one of {list(STORES)}, got {store!r}")

        role = section.get("role", "field").strip().lower()
        if role not in ROLES:
            errors.append(f"[{name}]: role must be one of {list(ROLES)}, got {role!r}")

        allowed_raw = section.get("allowed", "").strip()
        allowed = tuple(v.strip() for v in allowed_raw.split(",") if v.strip())

        if role == "tag":
            # The cardinality guard. See module docstring.
            if not allowed:
                errors.append(
                    f"[{name}]: role=tag requires an 'allowed' list. An InfluxDB "
                    f"tag is indexed, so an unbounded tag creates one series per "
                    f"capture. Enumerate the permitted values, or use role=field."
                )
            if ftype and ftype != "str":
                errors.append(f"[{name}]: role=tag requires type=str, got {ftype!r}")
            if store == "sqlite":
                errors.append(
                    f"[{name}]: role=tag is meaningless with store=sqlite; "
                    f"use store=influx or store=both"
                )
        if allowed and ftype and ftype != "str":
            errors.append(f"[{name}]: 'allowed' is only supported for type=str")

        if not errors:
            fields.append(
                UserField(
                    name=name,
                    type=ftype,
                    store=store,
                    role=role,
                    unit=section.get("unit", "").strip(),
                    source_path=section.get("from", "").strip(),
                    allowed=allowed,
                    doc=section.get("doc", "").strip(),
                )
            )

    if errors:
        raise ConfigError(
            f"Invalid user field manifest ({path or '<string>'}):\n  - "
            + "\n  - ".join(errors)
        )
    return UserSchema(fields, path=path)


def load_manifest(path: Optional[str | Path]) -> UserSchema:
    """Load a manifest file. A missing/blank path yields an empty schema."""
    if not path:
        return UserSchema()
    p = Path(path)
    if not p.is_file():
        # Absent manifest is not an error: the core schema alone is valid.
        logger.info("No user field manifest at %s; core schema only.", p)
        return UserSchema(path=p)
    return parse_manifest(p.read_text(encoding="utf-8"), path=p)


def load_hook(spec: str) -> Optional[Callable]:
    """Import a ``module:function`` hook. Blank spec yields ``None``."""
    spec = (spec or "").strip()
    if not spec:
        return None
    if ":" not in spec:
        raise ConfigError(
            f"[user_schema] hook must be 'module:function', got {spec!r}"
        )
    module_name, func_name = spec.split(":", 1)
    try:
        module = importlib.import_module(module_name.strip())
    except ImportError as exc:
        raise ConfigError(f"[user_schema] cannot import hook module {module_name!r}: {exc}") from exc
    func = getattr(module, func_name.strip(), None)
    if func is None or not callable(func):
        raise ConfigError(
            f"[user_schema] {func_name!r} is not a callable in {module_name!r}"
        )
    return func
