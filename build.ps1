# Builds dist\PhoneMouse-Setup.exe: the app as an .exe plus scrcpy, wrapped in an installer.
# Needs: Python 3 (py launcher) and Inno Setup 6 (winget install JRSoftware.InnoSetup).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$scrcpyVersion = "5.0.1"

if (-not (Test-Path .venv-build)) { py -3 -m venv .venv-build }
.\.venv-build\Scripts\python -m pip install -q --disable-pip-version-check pyinstaller pillow
.\.venv-build\Scripts\python phone_mouse.py --test

# 1. app -> build\app\PhoneMouse\PhoneMouse.exe (no console window)
.\.venv-build\Scripts\python -m PyInstaller --noconfirm --windowed --name PhoneMouse `
    --icon ..\icon.ico --add-data "..\icon.ico;." `
    --distpath build\app --workpath build\work --specpath build phone_mouse.py

# 2. scrcpy (includes adb) -> build\scrcpy
if (-not (Test-Path build\scrcpy\scrcpy.exe)) {
    $zip = "build\scrcpy.zip"
    Invoke-WebRequest "https://github.com/Genymobile/scrcpy/releases/download/v$scrcpyVersion/scrcpy-win64-v$scrcpyVersion.zip" -OutFile $zip
    Expand-Archive $zip build\scrcpy-tmp -Force
    Move-Item (Get-ChildItem build\scrcpy-tmp -Directory)[0].FullName build\scrcpy
    Remove-Item build\scrcpy-tmp, $zip -Recurse
}

# 3. installer -> dist\PhoneMouse-Setup.exe
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
& $iscc /Q installer.iss
Get-Item dist\PhoneMouse-Setup.exe
