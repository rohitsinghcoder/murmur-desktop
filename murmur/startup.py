"""Starting Murmur with Windows: a shortcut in the Startup folder, the same one setup.bat makes
(scripts/shortcuts.ps1). The shortcut on disk is the setting, so it's never out of step.
"""
import ctypes
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICON = ROOT / "assets" / "murmur.ico"

# Made by WScript.Shell in PowerShell, like shortcuts.ps1; the paths come in environment variables
# so no quoting can go wrong.
_CREATE = """
$link = (New-Object -ComObject WScript.Shell).CreateShortcut($env:MURMUR_LINK)
$link.TargetPath = $env:MURMUR_PYTHON
$link.Arguments = $env:MURMUR_ARGS
$link.IconLocation = $env:MURMUR_ICON
$link.WorkingDirectory = $env:MURMUR_ROOT
$link.Description = "Murmur: private voice typing. Hold Right Ctrl to dictate."
$link.Save()
"""


def _startup_folder() -> Path:
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 7, None, 0, buf)  # CSIDL_STARTUP
    return Path(buf.value or Path(os.environ.get("APPDATA", Path.home())) /
                "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")


LINK = _startup_folder() / "Murmur.lnk"


FROZEN = getattr(sys, "frozen", False)  # the installed Murmur.exe, not Python running the source


def pythonw() -> Path:
    """The running Python's windowless twin, so no console opens at login (or Murmur.exe)."""
    exe = Path(sys.executable)
    if FROZEN:
        return exe
    twin = exe.with_name("pythonw.exe")
    return twin if twin.exists() else exe


def enabled(link: Path = LINK) -> bool:
    return link.exists()


def enable(link: Path = LINK):
    exe = pythonw()
    env = {**os.environ, "MURMUR_LINK": str(link), "MURMUR_PYTHON": str(exe),
           "MURMUR_ARGS": "--background" if FROZEN else "-m murmur --background",
           "MURMUR_ICON": str(exe if FROZEN else ICON), "MURMUR_ROOT": str(exe.parent if FROZEN else ROOT)}
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                    "-Command", _CREATE], env=env, check=True, capture_output=True, timeout=30,
                   creationflags=subprocess.CREATE_NO_WINDOW)


def disable(link: Path = LINK):
    link.unlink(missing_ok=True)


def set_enabled(on: bool, link: Path = LINK):
    if on:
        enable(link)
    else:
        disable(link)
