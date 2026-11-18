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
AppPublisher=Director Calendar
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

function HasNewerPackage(Cache: String; Target: Int64): Boolean;
var Item: TFindRec; Version: Int64; Folder: String;
begin
  Result := False;
  if not FileExists(Cache + '\.owner') then Exit;
  if FindFirst(Cache + '\v*', Item) then begin
    try
      repeat
        Folder := Cache + '\' + Item.Name;
        if ((Item.Attributes and $10) <> 0) and FileExists(Folder + '\.ready') and
           GetPackedVersion(Folder + '\DirectorCalendar.exe', Version) and
           (ComparePackedVersion(Version, Target) > 0) then begin
          Result := True;
          Exit;
        end;
      until not FindNext(Item);
    finally
      FindClose(Item);
    end;
  end;
end;

{ Walk real children. The receipt identifies package files but never supplies a deletion path. }
function RemovePackageFiles(Folder, Prefix: String; Files: TStringList): Boolean;
var Item: TFindRec; Path, Relative: String;
begin
  Result := False;
  if FindFirst(Folder + '\*', Item) then begin
    try
      repeat
        if (Item.Name <> '.') and (Item.Name <> '..') and ((Item.Attributes and $400) = 0) then begin
          Path := Folder + '\' + Item.Name;
          Relative := Prefix + Item.Name;
          if (Item.Attributes and $10) <> 0 then begin
            if RemovePackageFiles(Path, Relative + '/', Files) then begin
              Result := True;
              RemoveDir(Path);
            end;
          end else if Files.IndexOf(Relative) >= 0 then begin
            if DeleteFile(Path) then Result := True;
          end;
        end;
      until not FindNext(Item);
    finally
      FindClose(Item);
    end;
  end;
end;

function SmallFile(Path: String; Limit: LongWord): Boolean;
var Item: TFindRec;
begin
  Result := False;
  if FindFirst(Path, Item) then begin
    try
      Result := ((Item.Attributes and $410) = 0) and (Item.SizeHigh = 0) and (Item.SizeLow <= Limit);
    finally
      FindClose(Item);
    end;
  end;
end;

function OwnedCache(Folder: String): Boolean;
var Contents: AnsiString;
begin
  Result := SmallFile(Folder + '\.owner', 64) and LoadStringFromFile(Folder + '\.owner', Contents) and
            (Trim(String(Contents)) = 'Director Calendar update cache v1');
end;

function OnlyCacheMarker(Cache: String): Boolean;
var Item: TFindRec;
begin
  Result := True;
  if FindFirst(Cache + '\*', Item) then begin
    try
      repeat
        if (Item.Name <> '.') and (Item.Name <> '..') and (Item.Name <> '.owner') then begin
          Result := False;
          Exit;
        end;
      until not FindNext(Item);
    finally
      FindClose(Item);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var Cache, Folder: String; Item: TFindRec; Files: TStringList; Version: Int64;
begin
  if CurUninstallStep <> usUninstall then Exit;
  Cache := ExpandConstant('{app}\.director-updates');
  if HasReparsePoint(Cache) or not OwnedCache(Cache) or ContainsReparsePoint(Cache) then Exit;
  if FindFirst(Cache + '\*', Item) then begin
    try
      repeat
        Folder := Cache + '\' + Item.Name;
        if (Item.Attributes and $10) <> 0 then begin
          if (Copy(Item.Name, 1, 1) = 'v') and StrToVersion(Copy(Item.Name, 2, Length(Item.Name)), Version)
              and SmallFile(Folder + '\.ready', 64) and SmallFile(Folder + '\.files', 8192 * 610) then begin
            Files := TStringList.Create;
            try
              try
                Files.LoadFromFile(Folder + '\.files');
                Files.Add('.files');
                Files.Add('.ready');
                Files.Sorted := True;
                RemovePackageFiles(Folder, '', Files);
              except
                Log('Skipped an unreadable update receipt.');
              end;
            finally
              Files.Free;
            end;
            RemoveDir(Folder);
          end else if (Copy(Item.Name, 1, 6) = 'stage-') and OwnedCache(Folder) then
            DelTree(Folder, True, True, True);
        end;
      until not FindNext(Item);
    finally
      FindClose(Item);
    end;
  end;
  DeleteFile(Cache + '\.lock');
  if OnlyCacheMarker(Cache) then begin
    DeleteFile(Cache + '\.owner');
    RemoveDir(Cache);
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
  if StrToVersion('{#AppVersion}', TargetVersion) then
    if (GetPackedVersion(ExpandConstant('{app}\DirectorCalendar.exe'), InstalledVersion) and
        (ComparePackedVersion(InstalledVersion, TargetVersion) > 0)) or
        HasNewerPackage(ExpandConstant('{app}\.director-updates'), TargetVersion) then
      Result := 'Установлена более новая версия Director Calendar. Понижение версии запрещено.';
end;
