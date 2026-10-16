"""Entry point of the frozen Murmur.exe (PyInstaller runs this instead of `python -m murmur`).

    Murmur.exe [--background]          the app, as `python -m murmur`
    Murmur.exe --selftest [OUT_DIR]    checks the build without the keyboard hook (murmur/selftest.py)
"""
import os
import sys

# The build bundles PySide6 only (murmur.spec). Set before qtpy is imported, so a QT_API left in
# the user's environment (Spyder, IPython) can't send qtpy looking for another binding.
os.environ["QT_API"] = "pyside6"

if __name__ == "__main__":
    if sys.argv[1:2] == ["--selftest"]:
        from murmur.selftest import main
    else:
        from murmur.__main__ import main
    main()
