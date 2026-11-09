"""Calibration-point dialog: pick a known wavelength from NIST reference lines.

Replaces the bare number box used when clicking an emission line in pick mode.
The user chooses a species (argon first) and a line from its list; typing a
value by hand still works. Without a calibration the list is strongest first;
with one, the lines nearest the clicked pixel's current wavelength come first,
with their distance shown.

The lines come from the files in ``reference/nist`` (see ``reference.lines``);
nothing here touches the network.
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from errors import CalibrationError
from reference import available_species, by_strength, load_lines, nearest, strength_label

_LINE_ROLE = QtCore.Qt.ItemDataRole.UserRole


def line_rows(lines, estimate_nm: float | None = None) -> list[tuple[float, str]]:
    """(wavelength, label) rows for a pick list, in display order.

    Qt-free so it can be tested on its own. ``lines`` is one species' lines.
    """
    ordered = nearest(lines, estimate_nm) if estimate_nm is not None else by_strength(lines)
    rows = []
    for ln in ordered:
        parts = [f"{ln.species}  {ln.wavelength_nm:.3f} nm"]
        label = strength_label(ln, lines)
        if label:
            parts.append(label)
        if estimate_nm is not None:
            parts.append(f"Δ {ln.wavelength_nm - estimate_nm:+.2f} nm")
        rows.append((ln.wavelength_nm, "   ".join(parts)))
    return rows


class ReferenceLineDialog(QtWidgets.QDialog):
    """Ask for the known wavelength of a clicked line."""

    def __init__(self, pixel: int, estimate_nm: float | None = None,
                 species: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibration point")
        self._estimate = estimate_nm
        self._picked: float | None = None

        intro = f"Known wavelength at pixel {pixel}"
        if estimate_nm is not None:
            intro += f"  (currently about {estimate_nm:.2f} nm)"
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(intro + ":"))

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Element:"))
        self._species = QtWidgets.QComboBox()
        self._species.addItems(available_species())
        row.addWidget(self._species, 1)
        layout.addLayout(row)

        self._list = QtWidgets.QListWidget()
        self._list.setMinimumSize(380, 260)
        layout.addWidget(self._list, 1)

        form = QtWidgets.QFormLayout()
        self._value = QtWidgets.QDoubleSpinBox()
        self._value.setRange(0.0, 3000.0)
        self._value.setDecimals(4)
        self._value.setSuffix(" nm")
        self._value.setValue(estimate_nm if estimate_nm is not None else 811.5311)
        form.addRow("Wavelength:", self._value)
        layout.addLayout(form)

        self._note = QtWidgets.QLabel(
            "Lines from the NIST Atomic Spectra Database (air wavelengths). "
            "Pick one, or type a value."
        )
        self._note.setWordWrap(True)
        layout.addWidget(self._note)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._species.currentTextChanged.connect(self._fill)
        self._list.currentItemChanged.connect(self._on_select)
        self._list.itemDoubleClicked.connect(lambda _item: self.accept())

        if species and self._species.findText(species) >= 0:
            self._species.setCurrentText(species)
        self._fill(self._species.currentText())

    # ------------------------------------------------------------------ #
    def _fill(self, species: str) -> None:
        self._list.clear()
        if not species:
            self._note.setText("No reference line files found. Type the wavelength.")
            return
        try:
            lines = load_lines(species)
        except CalibrationError as exc:
            self._note.setText(f"{exc}. Type the wavelength.")
            return
        for wavelength, text in line_rows(lines, self._estimate):
            item = QtWidgets.QListWidgetItem(text)
            item.setData(_LINE_ROLE, wavelength)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _on_select(self, item, _previous=None) -> None:
        if item is not None:
            self._picked = float(item.data(_LINE_ROLE))
            self._value.setValue(self._picked)

    # ------------------------------------------------------------------ #
    def wavelength(self) -> float:
        """The chosen wavelength. A picked line returns its full-precision NIST
        value (the box shows it rounded); an edited box returns what was typed."""
        typed = float(self._value.value())
        picked = self._picked
        if picked is not None and abs(typed - round(picked, self._value.decimals())) < 1e-9:
            return picked
        return typed

    def species(self) -> str:
        return self._species.currentText()

    @classmethod
    def get_wavelength(cls, parent, pixel: int, estimate_nm: float | None = None,
                       species: str | None = None) -> tuple[float, bool, str]:
        """Show the dialog modally. Returns (wavelength, accepted, species)."""
        dialog = cls(pixel, estimate_nm=estimate_nm, species=species, parent=parent)
        accepted = dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted
        return dialog.wavelength(), accepted, dialog.species()
