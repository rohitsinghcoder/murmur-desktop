# Creates (or with -Remove, deletes) the Start menu shortcut and, with -Startup 1, one that
# starts Murmur with Windows. Used by setup.bat and uninstall.bat.
param([int]$Startup = 0, [switch]$Remove)

$root = Split-Path -Parent $PSScriptRoot
$startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "Murmur.lnk"
$startupLink = Join-Path ([Environment]::GetFolderPath("Startup")) "Murmur.lnk"

if ($Remove) {
    Remove-Item $startMenu, $startupLink -ErrorAction SilentlyContinue
    Write-Host " Removed the Murmur shortcuts."
    exit 0
}

function New-Link($path) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($path)
    # pythonw runs without a console window.
    $link.TargetPath = Join-Path $root ".venv\Scripts\pythonw.exe"
    $link.Arguments = "-m murmur"
    $link.WorkingDirectory = $root
    $link.Description = "Murmur: private voice typing. Hold Right Ctrl to dictate."
    $link.Save()
}

New-Link $startMenu
Write-Host " Added Murmur to the Start menu."
if ($Startup -eq 1) {
    New-Link $startupLink
    Write-Host " Murmur will start when Windows starts."
} else {
    Remove-Item $startupLink -ErrorAction SilentlyContinue
}
