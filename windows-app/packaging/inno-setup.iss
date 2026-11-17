; BillFlow Inno Setup 6 script. 64-bit, per-user install (no admin required).
; Paths are relative to this .iss file; build.ps1 stages them first.

#define MyAppName "BillFlow"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "BillFlow"
#define MyAppExeName "billflow.exe"
#define MyAppId "{{7F3A9C2E-5B14-4D8A-9E63-2C1B0A7F6D45}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=staged\BillFlow\LICENSE.txt
OutputDir=.
OutputBaseFilename=BillFlow-{#MyAppVersion}-setup
SetupIconFile=staged\BillFlow\icon.ico
UninstallDisplayIcon={app}\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "staged\BillFlow\billflow.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "staged\BillFlow\icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "staged\BillFlow\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "staged\BillFlow\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
