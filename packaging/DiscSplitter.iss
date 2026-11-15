; Inno Setup script for the DiscSplitter installer.
; Built by packaging/build_installer.py, which passes /DAppVersion=... /DSourceDir=... /DOutputDir=...

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\build\installer\DiscSplitter"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
AppId={{6F1C2B7E-3D4A-4C8B-9E21-5A7D0C9B4F13}
AppName=DiscSplitter
AppVersion={#AppVersion}
AppVerName=DiscSplitter {#AppVersion}
AppPublisher=DiscSplitter
DefaultDirName={autopf}\DiscSplitter
DefaultGroupName=DiscSplitter
DisableProgramGroupPage=yes
; Installs for the current user without admin rights; the user can still choose "all users".
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=DiscSplitter-Setup-{#AppVersion}
SetupIconFile=..\disc_splitter.ico
UninstallDisplayIcon={app}\DiscSplitter.exe
; ultra64's 1 GB dictionary runs the (32-bit) compiler out of memory; max with a separate
; compressor process is safe and almost as small.
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
; Simplified Chinese is an unofficial Inno Setup translation, not installed with it: drop
; ChineseSimplified.isl (from the issrc repository, Files/Languages/Unofficial) next to this script.
#if FileExists(AddBackslash(SourcePath) + "ChineseSimplified.isl")
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; An upgrade over the app's first name (DiscTrackSplitter, same AppId) installs into the same folder:
; take the old program file and shortcuts away so only DiscSplitter is left.
Type: files; Name: "{app}\DiscTrackSplitter.exe"
Type: files; Name: "{group}\DiscTrackSplitter.lnk"
Type: files; Name: "{autodesktop}\DiscTrackSplitter.lnk"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DiscSplitter"; Filename: "{app}\DiscSplitter.exe"
Name: "{group}\{cm:UninstallProgram,DiscSplitter}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\DiscSplitter"; Filename: "{app}\DiscSplitter.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\DiscSplitter.exe"; Description: "{cm:LaunchProgram,DiscSplitter}"; Flags: nowait postinstall skipifsilent
