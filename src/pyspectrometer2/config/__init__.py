"""Configuration service (CFG-001..CFG-006).

Externalized INI configuration with a documented schema, profile overlays,
command-line overrides, and meaningful validation diagnostics.
"""

from .schema import SCHEMA, Field
from .loader import Config, load_config

__all__ = ["SCHEMA", "Field", "Config", "load_config"]
