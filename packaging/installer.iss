#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef SourceDir
  #error SourceDir is required
#endif
#ifndef BuildOutput
  #error BuildOutput is required
#endif
[Setup]
AppId={{D93AC78A-55E8-46C9-B014-517D5B2B6A32}
AppName=Director Calendar
AppVersion={#AppVersion}
AppPublisher=ACS
DefaultDirName={localappdata}\Programs\DirectorCalendar
DisableDirPage=yes
DefaultGroupName=Director Calendar
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#BuildOutput}
OutputBaseFilename=DirectorCalendar-{#AppVersion}-Setup-x64
SetupIconFile={#SourceDir}\_internal\director_control\assets\director-calendar.ico
UninstallDisplayIcon={app}\DirectorCalendar.exe
AppMutex=Local\DirectorCalendar.Running
CloseApplications=no
RestartApplications=no
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
VersionInfoVersion={#AppVersion}
[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userdesktop}\Director Calendar"; Filename: "{app}\DirectorCalendar.exe"; WorkingDir: "{app}"
Name: "{userprograms}\Director Calendar"; Filename: "{app}\DirectorCalendar.exe"; WorkingDir: "{app}"
[Run]
Filename: "{app}\DirectorCalendar.exe"; Description: "Открыть Director Calendar"; Flags: nowait postinstall skipifsilent
; No data files, Vault credentials or backup directories are installed/deleted.
[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var InstalledVersion, TargetVersion: Int64;
begin
  Result := '';
  if GetPackedVersion(ExpandConstant('{app}\DirectorCalendar.exe'), InstalledVersion) then
    if StrToVersion('{#AppVersion}', TargetVersion) and (ComparePackedVersion(InstalledVersion, TargetVersion) > 0) then
      Result := 'Установлена более новая версия Director Calendar. Понижение версии запрещено.';
end;
