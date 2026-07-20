"""Configuration service (CFG-001..CFG-006).

Externalized INI configuration with a documented schema, profile overlays,
command-line overrides, and meaningful validation diagnostics.
"""

from .schema import SCHEMA, Field
from .loader import Config, load_config
from .generate import render_ini, discover_config_path, user_config_path

__all__ = ["SCHEMA", "Field", "Config", "load_config",
           "render_ini", "discover_config_path", "user_config_path"]
