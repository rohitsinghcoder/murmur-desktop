import subprocess

from murmur import startup


def test_startup_shortcut(tmp_path):
    link = tmp_path / "Murmur.lnk"
    assert not startup.enabled(link)
    startup.set_enabled(True, link)
    assert startup.enabled(link)
    read = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"$l = (New-Object -ComObject WScript.Shell).CreateShortcut('{link}'); $l.TargetPath; $l.Arguments"],
        capture_output=True, text=True, check=True).stdout.splitlines()
    assert read[0].lower() == str(startup.pythonw()).lower()
    assert read[1] == "-m murmur --background"
    startup.set_enabled(False, link)
    assert not startup.enabled(link)


def test_startup_folder():
    assert startup.LINK.parent.name == "Startup"
