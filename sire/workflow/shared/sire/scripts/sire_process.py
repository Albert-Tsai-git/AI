"""Helpers for starting SIRE child processes without opening console windows."""
from __future__ import annotations

import os
import subprocess


def no_console_kwargs(extra_flags: int = 0) -> dict:
    """Hide console-subsystem children on Windows; no-op on other platforms."""
    if os.name != "nt":
        return {}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW | extra_flags,
        "startupinfo": startup,
    }
