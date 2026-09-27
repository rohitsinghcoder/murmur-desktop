"""Builds the Windows installer, dist/MurmurSetup-<version>.exe, from a clean checkout.

    py -3.12 scripts\\build_installer.py [--no-test] [--skip-pyinstaller]

1. Creates build-venv/ (with the Python running this script) holding the app's packages and
   PyInstaller (installer/requirements-build.txt). The repo's .venv isn't touched.
2. Freezes Murmur with PyInstaller (installer/murmur.spec) into dist/Murmur.
3. Runs the frozen build's self-test (Murmur.exe --selftest) if the speech model is in models/:
   the model loads, the sample recording transcribes, the window renders. The report and
   screenshots land in build/selftest. It never starts the keyboard hook.
4. Compiles installer/murmur.iss with Inno Setup into dist/MurmurSetup-<version>.exe.

Needs Inno Setup 6 (winget install -e --id JRSoftware.InnoSetup --scope user).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / "build-venv"
VENV_PY = VENV / "Scripts" / "python.exe"
DIST = ROOT / "dist"
MODEL_NAME = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"


def version() -> str:
    text = (ROOT / "murmur" / "ui" / "window.py").read_text(encoding="utf-8")
    return re.search(r'^VERSION = "([\d.]+)"', text, re.M)[1]


def run(*cmd, **kwargs):
    print(">", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kwargs)


def build_venv():
    if not VENV_PY.exists():
        if sys.version_info < (3, 11):
            sys.exit("Run this with Python 3.11 or newer (3.12 recommended): py -3.12 scripts\\build_installer.py")
        run(sys.executable, "-m", "venv", VENV)
        run(VENV_PY, "-m", "pip", "install", "--quiet", "--upgrade", "pip")
    run(VENV_PY, "-m", "pip", "install", "--quiet", "-r", ROOT / "installer" / "requirements-build.txt")


def pyinstaller():
    run(VENV_PY, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
        "--distpath", DIST, "--workpath", ROOT / "build" / "pyinstaller", ROOT / "installer" / "murmur.spec")


def selftest() -> bool:
    """Runs dist/Murmur/Murmur.exe --selftest against models/ (through a temporary home folder, as
    the frozen app looks for the model in ~/.murmur/models). False if it failed."""
    model = ROOT / "models" / MODEL_NAME
    if not (model / "tokens.txt").exists():
        print(f"Skipping the self-test: no model in {model} (scripts/fetch_model.py downloads it).")
        return True
    out = ROOT / "build" / "selftest"
    shutil.rmtree(out, ignore_errors=True)
    home = Path(tempfile.mkdtemp(prefix="murmur-home-"))
    try:
        (home / ".murmur" / "models").mkdir(parents=True)
        # A junction: no copy of the 630 MB model, and no admin rights needed.
        subprocess.run(["cmd", "/c", "mklink", "/J", str(home / ".murmur" / "models" / MODEL_NAME), str(model)],
                       check=True, stdout=subprocess.DEVNULL)
        env = {**os.environ, "USERPROFILE": str(home)}
        t0 = time.perf_counter()
        code = subprocess.run([str(DIST / "Murmur" / "Murmur.exe"), "--selftest", str(out)], env=env).returncode
        print(f"Self-test {'passed' if code == 0 else 'FAILED'} in {time.perf_counter() - t0:.1f} s; "
              f"report and screenshots in {out}")
        return code == 0
    finally:
        # rmdir on the junction removes the link only, never the model it points to.
        subprocess.run(["cmd", "/c", "rmdir", str(home / ".murmur" / "models" / MODEL_NAME)], check=False)
        shutil.rmtree(home, ignore_errors=True)


def find_iscc() -> Path | None:
    """ISCC.exe on PATH, or where a per-user (winget --scope user) or machine install puts it."""
    if found := shutil.which("ISCC"):
        return Path(found)
    env = os.environ.get
    candidates = [Path(env("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
                  Path(env("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
                  Path(env("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe"]
    return next((c for c in candidates if c.is_file()), None)


def folder_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 2**20


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-test", action="store_true", help="skip the frozen self-test")
    parser.add_argument("--skip-pyinstaller", action="store_true", help="reuse dist/Murmur")
    args = parser.parse_args()

    ver = version()
    iscc = find_iscc()
    if iscc is None:
        sys.exit("Inno Setup 6 wasn't found. Install it with\n"
                 "    winget install -e --id JRSoftware.InnoSetup --scope user\n"
                 "or from https://jrsoftware.org/isdl.php, then run this again.")
    print(f"Building Murmur {ver}")
    t0 = time.perf_counter()
    if not args.skip_pyinstaller:
        build_venv()
        pyinstaller()
    print(f"dist/Murmur: {folder_mb(DIST / 'Murmur'):.0f} MB")
    if not args.no_test and not selftest():
        sys.exit("The frozen build failed its self-test; not building the installer.")
    run(iscc, "/Q", f"/DAppVersion={ver}", f"/DSourceDir={DIST / 'Murmur'}", f"/O{DIST}",
        ROOT / "installer" / "murmur.iss")
    setup = DIST / f"MurmurSetup-{ver}.exe"
    print(f"\n{setup}: {setup.stat().st_size / 2**20:.0f} MB (built in {time.perf_counter() - t0:.0f} s)")


if __name__ == "__main__":
    main()
