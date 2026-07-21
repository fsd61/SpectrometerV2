"""PySide6 interactive GUI (Migration Plan Phase 7).

This subpackage is the only place the project imports PySide6/pyqtgraph, and it
does so at module import time — so importing ``ui.qt.*`` requires the optional
``[gui]`` extra. The application core (``app.commands.gui``) imports it lazily
and falls back with an actionable message if the extra is not installed.

All real logic lives in the Qt-free ``ui.live`` module; the widgets here only
render what that core produces.
"""
