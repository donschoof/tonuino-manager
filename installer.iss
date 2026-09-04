; Inno Setup Skript fuer Tonuino-Manager
; Erstellt einen Windows-Installer, der sich korrekt unter "Apps & Features"
; (Windows-Einstellungen) registriert und dort auch wieder deinstallieren laesst.
; Installation erfolgt pro Maschine unter Program Files (benoetigt Administrator/UAC).

#define MyAppName "Tonuino-Manager"
; MyAppVersion wird von build_exe.py per /DMyAppVersion=... aus
; src/core/__init__.py (__version__) uebergeben, damit es nur eine Quelle fuer
; die Versionsnummer im Projekt gibt. Der Wert hier ist nur ein Fallback fuer
; einen direkten "iscc installer.iss"-Aufruf ohne das Build-Skript.
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppExeName "Tonuino-Manager.exe"

[Setup]
; Feste AppId (GUID) - wichtig, damit Windows Updates/Deinstallation ueber
; Versionen hinweg konsistent demselben Programm zuordnet. Nicht aendern.
AppId={{9BB90457-5891-44D4-8BC7-4D7B3595037F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppName}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=src\resources\icon.ico
OutputDir=dist
OutputBaseFilename={#MyAppName}-{#MyAppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
