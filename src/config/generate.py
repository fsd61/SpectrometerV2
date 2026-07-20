"""Generate and discover the single user configuration file.

The user-facing config model is one documented ``config.ini``:
  * ``init-config`` writes it (generated from the schema, so the comments,
    defaults, and allowed values are always correct and never drift).
  * it is auto-discovered at startup — no ``--config`` needed for normal use.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .schema import SCHEMA, Field

APP = "spectrometerv2"


def user_config_path() -> Path:
    """The standard per-user config location (honors XDG_CONFIG_HOME)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / APP / "config.ini"


def discover_config_path() -> Optional[Path]:
    """Return the first config file found in the search order, else None.

    Order: a project-local ``spectrometerv2.ini`` in the current directory,
    then the per-user ``~/.config/spectrometerv2/config.ini``.
    """
    for candidate in (Path.cwd() / f"{APP}.ini", user_config_path()):
        if candidate.is_file():
            return candidate
    return None


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
