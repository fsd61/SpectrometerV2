"""Sink assembly — chooses and wires the persistence backends for a run.

Kept out of any individual backend module: a factory that picks between CSV,
SQLite and InfluxDB cannot live inside one of them without inverting the
dependency direction.

Responsibilities, in order:

1. **Assign capture identity once.** A UUID and a nanosecond timestamp are
   stamped on the spectrum *before* fan-out, so every backend records the same
   identity for the same capture. That is what makes an InfluxDB point
   resolvable to its SQLite row — without it, each sink would invent its own id
   and the two stores could never be joined.
2. **Load and validate the user manifest once**, sharing it across backends so
   a field declared once means the same thing in both stores.
3. **Fan out**, with CSV first so callers that print the returned handle keep
   getting a path.
"""

from __future__ import annotations

import logging
import time
import uuid as uuid_mod
from pathlib import Path
from typing import Optional

from processing.spectrum import Spectrum

from .influx import InfluxConfig, InfluxDbSpectrumSink
from .sinks import CsvSpectrumSink, MultiSink, SpectrumSink
from .sqlite import SqliteConfig, SqliteSpectrumSink
from .user_schema import UserSchema, load_hook, load_manifest

logger = logging.getLogger(__name__)


class IdentityStampingSink(SpectrumSink):
    """Assign capture identity, then delegate to the wrapped sink.

    Mutating ``spectrum.metadata`` here (rather than in each backend) is what
    guarantees the stores agree on which capture is which.
    """

    def __init__(self, inner: SpectrumSink):
        self._inner = inner

    def write(self, spectrum: Spectrum, name: Optional[str] = None):
        meta = spectrum.metadata
        if meta is None:                      # defensive: Spectrum defaults to {}
            meta = spectrum.metadata = {}
        meta.setdefault("capture_uuid", str(uuid_mod.uuid4()))
        meta.setdefault("timestamp_ns", time.time_ns())
        return self._inner.write(spectrum, name=name)

    @property
    def inner(self) -> SpectrumSink:
        return self._inner


def load_user_schema(config) -> tuple:
    """Load the user manifest and hook from ``[user_schema]``.

    Returns ``(schema, hook, on_violation)``. An absent manifest is not an
    error — the locked core schema alone is a valid configuration.
    """
    section = config.section("user_schema")
    schema = load_manifest(section.get("manifest", ""))
    hook = load_hook(str(section.get("hook", "")))
    on_violation = str(section.get("on_violation", "error"))
    if len(schema):
        logger.info(
            "Loaded %d user field(s) from %s (fingerprint %s)",
            len(schema), schema.path, schema.fingerprint(),
        )
    return schema, hook, on_violation


def build_sink(config, output: str | Path) -> SpectrumSink:
    """Assemble the run's output sink: CSV, plus SQLite and InfluxDB if enabled."""
    user_schema, hook, on_violation = load_user_schema(config)

    sinks: list = [CsvSpectrumSink(output)]

    sqlite_cfg = SqliteConfig.from_section(config.section("sqlite"))
    if sqlite_cfg.enabled:
        sinks.append(
            SqliteSpectrumSink(
                sqlite_cfg, user_schema=user_schema, hook=hook,
                on_violation=on_violation,
            )
        )

    influx_cfg = InfluxConfig.from_section(config.section("influx"))
    if influx_cfg.enabled:
        sinks.append(
            InfluxDbSpectrumSink(
                influx_cfg, user_schema=user_schema, hook=hook,
                on_violation=on_violation,
            )
        )

    inner: SpectrumSink = sinks[0] if len(sinks) == 1 else MultiSink(sinks)
    return IdentityStampingSink(inner)


def build_user_schema_only(config) -> UserSchema:
    """The validated manifest alone — for ``describe-schema`` and tests."""
    return load_user_schema(config)[0]
