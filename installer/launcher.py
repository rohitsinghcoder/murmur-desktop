"""Entry point of the frozen Murmur.exe (PyInstaller runs this instead of `python -m murmur`).

    Murmur.exe [--background]          the app, as `python -m murmur`
    Murmur.exe --selftest [OUT_DIR]    checks the build without the keyboard hook (murmur/selftest.py)
"""
import sys

if __name__ == "__main__":
    if sys.argv[1:2] == ["--selftest"]:
        from murmur.selftest import main
    else:
        from murmur.__main__ import main
    main()
