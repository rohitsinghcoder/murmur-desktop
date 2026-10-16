"""Entry point of the frozen Murmur.exe (PyInstaller runs this instead of `python -m murmur`).

    Murmur.exe [--background]          the app, as `python -m murmur`
    Murmur.exe --selftest [OUT_DIR]    checks the build without the keyboard hook (murmur/selftest.py)
"""
import sys

# QT_API, which tells qtpy to use the one Qt binding bundled, is set by murmur.spec's runtime hook,
# before this runs.

if __name__ == "__main__":
    if sys.argv[1:2] == ["--selftest"]:
        from murmur.selftest import main
    else:
        from murmur.__main__ import main
    main()
