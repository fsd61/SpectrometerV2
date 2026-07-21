"""Generate and discover the project-local configuration file.

The config lives inside the (movable, self-contained) project directory:
``<project>/config/config.ini``. It is resolved relative to the project root —
found by walking up for ``pyproject.toml`` — so it works from any subdirectory,
not just the exact current directory. ``--config PATH`` overrides it, and
alternate full config files can live alongside it in ``config/`` and be selected
with ``--config config/<name>.ini``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .schema import SCHEMA, Field

APP = "spectrometerv2"


def find_project_root(start: Optional[Path] = None) -> Path:
    """Locate the project root (the directory containing ``pyproject.toml``).

    Walks up from ``start`` (default: current directory); falls back to the
    package's own project root, then to ``start``.
    """
    start = Path(start or Path.cwd()).resolve()
    for d in (start, *start.parents):
        if (d / "pyproject.toml").is_file():
            return d
    pkg_root = Path(__file__).resolve().parents[2]  # …/src/config/generate.py -> root
    return pkg_root if (pkg_root / "pyproject.toml").is_file() else start


def config_dir() -> Path:
    """The project's ``config/`` directory (holds config.ini + alternates)."""
    return find_project_root() / "config"


def config_path() -> Path:
    """The default configuration file: ``<project>/config/config.ini``."""
    return config_dir() / "config.ini"


def discover_config_path() -> Optional[Path]:
    """Return ``config/config.ini`` if it exists, else None."""
    p = config_path()
    return p if p.is_file() else None


def _fmt(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def render_ini(schema=SCHEMA) -> str:
    """Render a fully-commented INI (every key documented) from the schema."""
    out = [
        f"# {APP} configuration",
        "#",
        "# Generated from the configuration schema: every key below is listed with",
        "# its purpose, type, default, and allowed values. Edit values as needed —",
        "# invalid or out-of-range values are rejected at startup with a clear message.",
        "# Any value can also be overridden per-run with: --set section.key=value",
        "#",
        "# Alternate setups: keep additional complete config files in this folder",
        "# (e.g. config/lab.ini) and select one with: --config config/lab.ini",
        "",
    ]
    for section, keys in schema.items():
        out.append(f"[{section}]")
        for key, field in keys.items():
            out.append(f"# {field.doc}")
            meta = [f"type={field.type}", f"default={_fmt(field.default)}"]
            if field.choices is not None:
                meta.append("choices=" + ", ".join(map(str, field.choices)))
            if field.min is not None:
                meta.append(f"min={field.min}")
            if field.max is not None:
                meta.append(f"max={field.max}")
            out.append("#   (" + "; ".join(meta) + ")")
            out.append(f"{key} = {_fmt(field.default)}")
            out.append("")
        out.append("")
    return "\n".join(out).rstrip() + "\n"
