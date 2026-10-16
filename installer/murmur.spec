# PyInstaller spec for Murmur.exe, a one-folder (onedir) build in dist/Murmur (dist/arm64/Murmur).
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

# The build is for the architecture of the Python running it: x64 with PySide6 (LGPL), native
# ARM64 with PyQt6 (GPL), as ARM64's PySide6 has no Qt WebEngine (requirements-arm64.txt).
PLATFORM = sysconfig.get_platform()
if PLATFORM not in ("win-amd64", "win-arm64"):
    raise SystemExit(f"Build with x64 or ARM64 Python, not {PLATFORM}")
BINDING = "PyQt6" if PLATFORM == "win-arm64" else "PySide6"
if importlib.util.find_spec(BINDING) is None:
    raise SystemExit(f"{BINDING} isn't installed in the build venv (installer/requirements-build*.txt)")
# Where the binding keeps Qt in the bundle: PySide6 all in its folder, PyQt6 under Qt6/ with the
# DLLs in bin/.
QT_DIR = {"PySide6": "PySide6/", "PyQt6": "PyQt6/Qt6/"}[BINDING]
QT_DLL_DIR = {"PySide6": "PySide6/", "PyQt6": "PyQt6/Qt6/bin/"}[BINDING]

# qtpy imports whichever Qt binding is there, so PyInstaller sees all four. Its hook-qtpy keeps one,
# by QT_API or else in the order PyQt5, PySide2, PyQt6, PySide6: with PyQt6 installed as well it
# kept PyQt6, which the excludes below then dropped, leaving no Qt at all. Pick the binding for the
# hook and exclude the others outright.
os.environ["QT_API"] = BINDING.lower()
OTHER_BINDINGS = [b for b in ("PyQt5", "PySide2", "PyQt6", "PySide6") if b != BINDING]
# And the frozen app sets it too, before anything imports qtpy, so a QT_API left in the user's
# environment (Spyder, IPython) can't send qtpy looking for a binding that isn't there.
Path(workpath).mkdir(parents=True, exist_ok=True)
qt_api_hook = Path(workpath) / "qt_api.py"
qt_api_hook.write_text(f'import os\nos.environ["QT_API"] = "{BINDING.lower()}"\n', encoding="utf-8")

# spacing.py loads UI Automation with comtypes.client.GetModule("UIAutomationCore.dll"), which
# on first use generates wrapper modules into comtypes.gen. Generate them now, in the build
# environment, and bundle them: the frozen app then imports them instead of writing any.
import comtypes.client  # noqa: E402

comtypes.client.GetModule("UIAutomationCore.dll")

# Qt modules Murmur doesn't import. (QtPrintSupport stays: QtWebEngineWidgets imports it.)
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
    runtime_hooks=[str(qt_api_hook)],
    excludes=["tkinter", "pytest"] + OTHER_BINDINGS + ([f"{BINDING}.{m}" for m in UNUSED_QT] if TRIM else []),
)
if not any(dest.replace("\\", "/").startswith(f"{BINDING}/") for dest, _, _ in a.binaries):
    raise SystemExit(f"No {BINDING} in the bundle: check QT_API and hook-qtpy's warnings above")


def unused(dest: str) -> bool:
    """Qt files Murmur doesn't need, by their path in the bundle."""
    d = dest.replace("\\", "/")
    if not d.startswith(QT_DIR):
        return False
    d = d[len(QT_DIR):]
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
    Plugins, .pyd modules, QtWebEngineProcess.exe and everything outside the Qt DLL folder are
    kept and are the roots."""
    def is_qt_dll(dest):
        d, folder = dest.replace("\\", "/").lower(), QT_DLL_DIR.lower()
        return d.startswith(folder + "qt6") and d.endswith(".dll") and "/" not in d[len(folder):]

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
