; Inno Setup script: builds dist\PhoneMouse-Setup.exe. Run build.ps1, not this directly.
#define AppVersion "1.0.1"

[Setup]
AppName=Phone Mouse
AppVersion={#AppVersion}
AppPublisher=ajithshub318
AppPublisherURL=https://github.com/ajithshub318/phone-mouse
DefaultDirName={autopf}\Phone Mouse
DefaultGroupName=Phone Mouse
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=PhoneMouse-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\PhoneMouse.exe
LicenseFile=LICENSE
SetupIconFile=icon.ico

[Files]
Source: "build\app\PhoneMouse\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "build\scrcpy\*"; DestDir: "{app}\scrcpy"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Phone Mouse"; Filename: "{app}\PhoneMouse.exe"
Name: "{group}\Uninstall Phone Mouse"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Phone Mouse"; Filename: "{app}\PhoneMouse.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"

[Run]
Filename: "{app}\PhoneMouse.exe"; Description: "Start Phone Mouse"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/f /im scrcpy.exe"; Flags: runhidden; RunOnceId: "killscrcpy"
Filename: "taskkill"; Parameters: "/f /im PhoneMouse.exe"; Flags: runhidden; RunOnceId: "killapp"
