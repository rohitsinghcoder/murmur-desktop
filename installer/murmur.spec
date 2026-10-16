# PyInstaller spec for Murmur.exe, a one-folder (onedir) build in dist/Murmur.
# Run it through scripts/build_installer.py, which also builds the installer around it.
#
# Trimmed of the parts of Qt that Murmur doesn't use (QML, Qt Quick modules, translations, the
# Chromium dev tools, debug resources, software OpenGL): about 645 MB untrimmed -> 376 MB.
# Set MURMUR_NO_TRIM=1 to build without trimming, to rule it out when something is missing.
import importlib.util
import os
import re
import sysconfig
from pathlib import Path

import pefile
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
TRIM = os.environ.get("MURMUR_NO_TRIM") != "1"
VERSION = re.search(r'^VERSION = "([\d.]+)"', (ROOT / "murmur" / "ui" / "window.py").read_text("utf-8"), re.M)[1]

# The installer is the x64 PySide6 (LGPL) build. ARM64's PySide6 has no Qt WebEngine, and PyQt6
# (GPL) isn't shipped; an ARM64 PC builds it with x64 Python (py -V:3.12), which runs emulated.
if sysconfig.get_platform() != "win-amd64":
    raise SystemExit(f"Build the installer with x64 Python, not {sysconfig.get_platform()} "
                     "(see docs/INSTALLER.md)")
if importlib.util.find_spec("PySide6") is None:
    raise SystemExit("PySide6 isn't installed in the build venv (requirements.txt has it)")

# qtpy imports whichever Qt binding is there, so PyInstaller sees all four. Its hook-qtpy keeps one,
# by QT_API or else in the order PyQt5, PySide2, PyQt6, PySide6: with PyQt6 installed as well it
# kept PyQt6, which the excludes below then dropped, leaving no Qt at all. Pick PySide6 for the
# hook and exclude the others outright.
os.environ["QT_API"] = "pyside6"
OTHER_BINDINGS = ["PyQt5", "PySide2", "PyQt6"]

# spacing.py loads UI Automation with comtypes.client.GetModule("UIAutomationCore.dll"), which
# on first use generates wrapper modules into comtypes.gen. Generate them now, in the build
# environment, and bundle them: the frozen app then imports them instead of writing any.
import comtypes.client  # noqa: E402

comtypes.client.GetModule("UIAutomationCore.dll")

# PySide6 modules Murmur doesn't import. (QtPrintSupport stays: QtWebEngineWidgets imports it.)
# qtpy tries QtDataVisualization (on import) and QtOpenGLWidgets (qtpy.QtWidgets) and does
# without them.
UNUSED_QT = ["QtOpenGL", "QtPositioning", "QtQml", "QtQuick", "QtQuickWidgets",
             "QtDataVisualization", "QtOpenGLWidgets"]

a = Analysis(
    [str(ROOT / "installer" / "launcher.py")],
    pathex=[str(ROOT)],
    # Next to the murmur package, where the code finds them (Path(__file__) resolves inside
    # _internal): ui/web for the window, assets/ for sounds.py (start/stop.wav) and startup.py
    # (murmur.ico for the Startup shortcut Settings makes).
    datas=[(str(ROOT / "murmur" / "ui" / "web"), "murmur/ui/web"),
           (str(ROOT / "assets"), "assets")],
    hiddenimports=collect_submodules("comtypes.gen"),
    excludes=["tkinter", "pytest"] + OTHER_BINDINGS + ([f"PySide6.{m}" for m in UNUSED_QT] if TRIM else []),
)
if not any(dest.replace("\\", "/").startswith("PySide6/") for dest, _, _ in a.binaries):
    raise SystemExit("No PySide6 in the bundle: check QT_API and hook-qtpy's warnings above")


def unused(dest: str) -> bool:
    """Qt files Murmur doesn't need, by their path in the bundle."""
    d = dest.replace("\\", "/")
    if not d.startswith("PySide6/"):
        return False
    d = d[len("PySide6/"):]
    name = d.rsplit("/", 1)[-1]
    return (
        d.startswith("qml/")  # QML modules: the window is a widget, not Qt Quick
        or (d.startswith("translations/") and not d.endswith("/en-US.pak"))  # English only
        or ".debug." in name  # Chromium debug resources
        or name == "qtwebengine_devtools_resources.pak"  # no dev tools
        or name == "opengl32sw.dll"  # software OpenGL: Qt uses Direct3D on Windows
        or d.startswith(("plugins/qmltooling/", "plugins/position/", "plugins/generic/"))
        or name in ("qpdf.dll", "qtvirtualkeyboardplugin.dll", "qdirect2d.dll", "qminimal.dll")
    )


def prune_unlinked_qt(binaries, datas):
    """Drops Qt DLLs that nothing kept loads, now that QML and the unused modules are gone.
    Plugins, .pyd modules, QtWebEngineProcess.exe and everything outside PySide6/ are kept and
    are the roots."""
    def is_qt_dll(dest):
        d = dest.replace("\\", "/").lower()
        return d.startswith("pyside6/qt6") and d.endswith(".dll") and "/" not in d[len("pyside6/"):]

    def imports(path):
        pe = pefile.PE(path, fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                                               pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"]])
        names = {e.dll.decode().lower() for attr in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT")
                 for e in getattr(pe, attr, [])}
        pe.close()
        return names

    qt = {Path(dest).name.lower(): (dest, src) for dest, src, _ in binaries if is_qt_dll(dest)}
    todo = [src for dest, src, _ in binaries if not is_qt_dll(dest)]
    todo += [src for dest, src, _ in datas if dest.lower().endswith((".exe", ".dll", ".pyd"))]
    keep = set()
    while todo:
        for dll in imports(todo.pop()):
            if dll in qt and dll not in keep:
                keep.add(dll)
                todo.append(qt[dll][1])
    dropped = sorted(set(qt) - keep)
    print("Dropped unlinked Qt DLLs:", ", ".join(dropped))
    return [b for b in binaries if not (is_qt_dll(b[0]) and Path(b[0]).name.lower() in dropped)]


if TRIM:
    a.binaries = [b for b in a.binaries if not unused(b[0])]
    a.datas = [d for d in a.datas if not unused(d[0])]
    a.binaries = prune_unlinked_qt(a.binaries, a.datas)

# Version resource, so Windows shows "Murmur" and the version in Task Manager and file properties.
nums = tuple(int(n) for n in (VERSION.split(".") + ["0"] * 4)[:4])
version_file = Path(workpath) / "version_info.txt"
version_file.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Murmur'),
    StringStruct('FileDescription', 'Murmur'),
    StringStruct('FileVersion', '{VERSION}'),
    StringStruct('InternalName', 'Murmur'),
    StringStruct('OriginalFilename', 'Murmur.exe'),
    StringStruct('ProductName', 'Murmur Desktop'),
    StringStruct('ProductVersion', '{VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""", encoding="utf-8")

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Murmur",
    console=False,  # like pythonw: no console window
    icon=str(ROOT / "assets" / "murmur.ico"),
    version=str(version_file),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Murmur", upx=False)
