"""
display.py
----------
Terminal display helper for mixed Hebrew / English / emoji output.

The core problem:
  Windows PowerShell / cmd render characters strictly left-to-right.
  Hebrew Unicode is stored in logical (right-to-left) order, so it
  appears reversed on LTR-only terminals.

Detection logic:
  • Windows Terminal (WT) sets the  WT_SESSION  environment variable.
    WT has native RTL/bidi rendering → no transformation needed.
  • Old PowerShell / cmd.exe do NOT set WT_SESSION.
    They are pure LTR → we must apply the Unicode Bidi Algorithm via
    python-bidi's get_display() to produce a visually-ordered string
    that looks correct when printed left-to-right.
  • Non-Windows systems: leave text unchanged.

Usage:
    from display import format_bidi
    print(format_bidi("🚨 חלון החילופים נסגר בעוד שעה!"))
"""

import os
import sys

# Detect once at import time to avoid repeated env lookups
_ON_WINDOWS       = sys.platform == "win32"
_WINDOWS_TERMINAL = bool(os.environ.get("WT_SESSION"))   # set by Windows Terminal

# Try to import python-bidi
try:
    from bidi.algorithm import get_display as _get_display
    _BIDI_AVAILABLE = True
except ImportError:
    _BIDI_AVAILABLE = False


def _has_hebrew(text: str) -> bool:
    """True if the string contains at least one Hebrew character."""
    return any("\u0590" <= c <= "\u05ff" or "\ufb1d" <= c <= "\ufb4f" for c in text)


def format_bidi(text: str) -> str:
    """
    Returns a terminal-safe version of *text*:

    ┌─────────────────────┬──────────────────────────────────────────────┐
    │ Environment         │ Action                                       │
    ├─────────────────────┼──────────────────────────────────────────────┤
    │ Windows Terminal    │ No-op — WT renders Hebrew natively           │
    │ PowerShell / cmd    │ Apply bidi visual reorder per Hebrew line    │
    │ Non-Windows         │ No-op — most Unix terminals handle bidi      │
    └─────────────────────┴──────────────────────────────────────────────┘

    Lines that contain no Hebrew characters are never transformed.
    """
    if not _ON_WINDOWS or _WINDOWS_TERMINAL:
        return text                     # terminal handles RTL natively

    if not _BIDI_AVAILABLE:
        return text                     # bidi library not installed → best effort

    fixed_lines = []
    for line in text.split("\n"):
        if _has_hebrew(line):
            fixed_lines.append(_get_display(line))
        else:
            fixed_lines.append(line)   # English / digits / emoji → unchanged

    return "\n".join(fixed_lines)
