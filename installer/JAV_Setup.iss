#define MyAppName "JAV"
#define MyAppVersion "15.3"
#define MyAppPublisher "JAV Project"
#define MyAppExeName "JAV.exe"
#define MyConsoleExeName "JAV-Console.exe"

[Setup]
AppId={{A6C9D6E9-1F77-4F82-8A7C-3D579ABBCB15}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableDirPage=no
UsePreviousAppDir=yes
AllowNoIcons=yes
PrivilegesRequired=lowest
OutputDir=..\installer_output
OutputBaseFilename=JAV_Setup_PortableAware
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start JAV with Windows"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "portabledata"; Description: "Store memory/workspace/screenshots inside the installation folder (portable/movable)"; GroupDescription: "Data location:"; Flags: checkedonce

[Files]
Source: "..\dist\JAV\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\data\brain\logs"; Tasks: portabledata
Name: "{app}\data\workspace"; Tasks: portabledata
Name: "{app}\data\screenshots"; Tasks: portabledata

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\JAV Doctor"; Filename: "{app}\{#MyConsoleExeName}"; Parameters: "--doctor"; WorkingDir: "{app}"
Name: "{group}\JAV Chat"; Filename: "{app}\{#MyConsoleExeName}"; Parameters: "--chat"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: startup

[Run]
; Create/update .env and portable folders after files are installed. Relative paths make the folder movable.
Filename: "{app}\{#MyConsoleExeName}"; Parameters: "--init-portable ""{app}"""; WorkingDir: "{app}"; Flags: runhidden; Tasks: portabledata
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Do not delete data/brain by default; the user's memory should survive uninstall unless removed manually.
Type: files; Name: "{app}\desktop_crash.log"
