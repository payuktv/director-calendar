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
#include "retired-files.iss"
[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userdesktop}\Director Calendar"; Filename: "{app}\DirectorCalendar.exe"; WorkingDir: "{app}"
Name: "{userprograms}\Director Calendar"; Filename: "{app}\DirectorCalendar.exe"; WorkingDir: "{app}"
[Run]
Filename: "{app}\DirectorCalendar.exe"; Description: "Открыть Director Calendar"; Flags: nowait postinstall skipifsilent
; No data files, Vault credentials or backup directories are installed/deleted.
[Code]
function GetFileAttributesW(FileName: String): LongWord;
  external 'GetFileAttributesW@kernel32.dll stdcall';

function HasReparsePoint(Path: String): Boolean;
var Attributes: LongWord; Parent: String;
begin
  Result := False;
  while Path <> '' do begin
    Attributes := GetFileAttributesW(Path);
    if (Attributes <> $FFFFFFFF) and ((Attributes and $400) <> 0) then begin
      Result := True;
      Exit;
    end;
    Parent := ExtractFileDir(Path);
    if Parent = Path then Exit;
    Path := Parent;
  end;
end;

function RetiredFileIsSafe(RelativePath: String): Boolean;
begin
  Result := not HasReparsePoint(ExpandConstant('{app}\') + RelativePath);
  if not Result then
    RaiseException('Обновление остановлено: путь устаревшего файла содержит ссылку на другой каталог.');
end;

function ContainsReparsePoint(Path: String): Boolean;
var Item: TFindRec;
begin
  Result := False;
  if FindFirst(AddBackslash(Path) + '*', Item) then begin
    try
      repeat
        if (Item.Name <> '.') and (Item.Name <> '..') then begin
          if (Item.Attributes and $400) <> 0 then Result := True
          else if (Item.Attributes and $10) <> 0 then
            Result := ContainsReparsePoint(AddBackslash(Path) + Item.Name);
          if Result then Exit;
        end;
      until not FindNext(Item);
    finally
      FindClose(Item);
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var InstalledVersion, TargetVersion: Int64;
begin
  Result := '';
  if HasReparsePoint(ExpandConstant('{app}')) or ContainsReparsePoint(ExpandConstant('{app}')) then begin
    Result := 'Обновление остановлено: каталог приложения содержит ссылку на другой каталог.';
    Exit;
  end;
  if GetPackedVersion(ExpandConstant('{app}\DirectorCalendar.exe'), InstalledVersion) then
    if StrToVersion('{#AppVersion}', TargetVersion) and (ComparePackedVersion(InstalledVersion, TargetVersion) > 0) then
      Result := 'Установлена более новая версия Director Calendar. Понижение версии запрещено.';
end;
