"""Line-list records and the container that carries their provenance.

A :class:`SpectralLine` is one atomic transition as published. A
:class:`LineList` is a set of them *plus* the identity of the file they came
from, because a wavelength atlas is calibration input: the same argument that
puts capture-backend identity in the persistence core (see
:mod:`data.schema_core`) puts line-list identity here. A calibration fitted
against one atlas revision, in one wavelength convention, is not interchangeable
with another.

:meth:`LineList.fingerprint` is the value meant to be stamped into a calibration
record alongside ``calibration_id``. It covers the source bytes *and* the
convention, so both a revised atlas and a silent air/vacuum flip change it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable, Iterator, Optional, Sequence

from .airvacuum import air_to_vacuum, vacuum_to_air


class WavelengthConvention(str, Enum):
    """Medium a wavelength is quoted in. Never inferred — always carried."""

    AIR = "air"
    VACUUM = "vacuum"


@dataclass(frozen=True)
class SpectralLine:
    """One published transition.

    ``wavelength_nm`` is the value to use; it is the Ritz wavelength when ASD
    supplied one (typically ~1e-4 nm, far tighter than any instrument function
    here) and the observed wavelength otherwise. ``observed_nm`` and ``ritz_nm``
    are retained so that choice stays auditable.

    ``relative_intensity`` is ASD's ``Rel. Int.`` — a *qualitative*,
    source-dependent number on an arbitrary per-publication scale. It is parsed
    and preserved for reference but must not be used as a photometric
    amplitude; use :mod:`linelist.intensity` instead.
    """

    wavelength_nm: float
    convention: WavelengthConvention
    species: str = ""
    observed_nm: Optional[float] = None
    ritz_nm: Optional[float] = None
    relative_intensity: Optional[float] = None
    aki_s: Optional[float] = None                 # Einstein A, s^-1
    e_lower_ev: Optional[float] = None
    e_upper_ev: Optional[float] = None
    g_lower: Optional[float] = None
    g_upper: Optional[float] = None

    def to_convention(self, convention: WavelengthConvention) -> "SpectralLine":
        """Return this line expressed in ``convention`` (identity if unchanged)."""
        if convention is self.convention:
            return self
        if convention is WavelengthConvention.VACUUM:
            converted = air_to_vacuum(self.wavelength_nm)
        else:
            converted = vacuum_to_air(self.wavelength_nm)
        return replace(self, wavelength_nm=converted, convention=convention)

    def has_boltzmann_terms(self) -> bool:
        """True when A_ki, g_k and E_k are all present (see :mod:`intensity`)."""
        return None not in (self.aki_s, self.g_upper, self.e_upper_ev)


@dataclass(frozen=True)
class Provenance:
    """Where a line list came from, and what exactly was read.

    ``content_sha256`` is over the raw source bytes, so editing the file — even
    whitespace — invalidates any calibration that cited it.
    """

    source: str = "unknown"
    retrieved: str = ""
    query: str = ""
    notes: str = ""
    content_sha256: str = ""

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "retrieved": self.retrieved,
            "query": self.query,
            "notes": self.notes,
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True)
class LineList:
    """An ordered, convention-tagged set of lines with its provenance."""

    lines: Sequence[SpectralLine] = field(default_factory=tuple)
    convention: WavelengthConvention = WavelengthConvention.AIR
    provenance: Provenance = field(default_factory=Provenance)

    def __post_init__(self):
        mismatched = [ln for ln in self.lines if ln.convention is not self.convention]
        if mismatched:
            raise ValueError(
                f"{len(mismatched)} line(s) disagree with the list convention "
                f"{self.convention.value!r}; convert before constructing"
            )
        object.__setattr__(self, "lines", tuple(sorted(self.lines, key=lambda l: l.wavelength_nm)))

    def __len__(self) -> int:
        return len(self.lines)

    def __iter__(self) -> Iterator[SpectralLine]:
        return iter(self.lines)

    def __getitem__(self, index):
        return self.lines[index]

    def to_convention(self, convention: WavelengthConvention) -> "LineList":
        """Return the whole list expressed in ``convention``."""
        if convention is self.convention:
            return self
        return LineList(
            lines=tuple(ln.to_convention(convention) for ln in self.lines),
            convention=convention,
            provenance=self.provenance,
        )

    def filtered(
        self,
        wavelength_min: Optional[float] = None,
        wavelength_max: Optional[float] = None,
        species: Optional[Iterable[str]] = None,
        min_relative_intensity: Optional[float] = None,
    ) -> "LineList":
        """Restrict by band, species, or intensity, preserving provenance.

        The band is applied in *this list's* current convention — convert first
        if the bounds are quoted in the other one.
        """
        wanted = {s.strip().lower() for s in species} if species else None
        selected = []
        for ln in self.lines:
            if wavelength_min is not None and ln.wavelength_nm < wavelength_min:
                continue
            if wavelength_max is not None and ln.wavelength_nm > wavelength_max:
                continue
            if wanted is not None and ln.species.strip().lower() not in wanted:
                continue
            if min_relative_intensity is not None:
                if ln.relative_intensity is None or ln.relative_intensity < min_relative_intensity:
                    continue
            selected.append(ln)
        return LineList(tuple(selected), self.convention, self.provenance)

    def wavelengths(self) -> list[float]:
        """Line centers, ascending, in this list's convention."""
        return [ln.wavelength_nm for ln in self.lines]

    def species_present(self) -> list[str]:
        return sorted({ln.species for ln in self.lines if ln.species})

    def fingerprint(self) -> str:
        """Short stable id for the calibration record.

        Covers the source content hash and the convention. Two lists that differ
        only by air-vs-vacuum produce different fingerprints, which is the whole
        point.
        """
        payload = json.dumps(
            {
                "sha256": self.provenance.content_sha256,
                "source": self.provenance.source,
                "convention": self.convention.value,
                "n_lines": len(self.lines),
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]

    def describe(self) -> dict:
        """Summary suitable for embedding in spectrum metadata."""
        return {
            "linelist_fingerprint": self.fingerprint(),
            "linelist_convention": self.convention.value,
            "linelist_source": self.provenance.source,
            "linelist_sha256": self.provenance.content_sha256,
            "linelist_n_lines": len(self.lines),
            "linelist_species": self.species_present(),
        }
