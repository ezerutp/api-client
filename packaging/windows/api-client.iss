; Inno Setup script for API Client (Windows).
;
; Builds a per-user installer: no admin rights needed, nothing is written outside
; the current user's profile. It registers the "api-client" command on the user's
; PATH and creates Desktop + Start Menu shortcuts, mirroring what install.sh does
; on Linux.
;
; Build with packaging\windows\build.ps1, or manually:
;   pyinstaller api_client.spec
;   ISCC packaging\windows\api-client.iss

; Keep in sync with APP_VERSION in app\__init__.py and the version in pyproject.toml
; (the PyInstaller build has no embedded version resource to read it from).
#define MyAppName "API Client"
#define MyAppId "api-client"
#define MyAppVersion "1.0.0"
#define MyAppExeName "api-client.exe"
#define MyAppGuiExeName "api-clientw.exe"
#define MyAppPublisher "ezerutp"
#define MyAppURL "https://github.com/ezerutp/api-client"

[Setup]
AppId={{B2B3C9C4-9C2F-4B7A-8E53-6B6A6D1A9F10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; Per-user install, no UAC prompt, nothing written outside the user's profile.
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist_installer
OutputBaseFilename=api-client-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
; Lets Inno Setup broadcast WM_SETTINGCHANGE after the [Registry] PATH edit below.
ChangesEnvironment=yes
SetupIconFile=..\..\assets\api-client.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\api-client\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppGuiExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppGuiExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
    ValueData: "{olddata};{app}"; Flags: preservestringtype; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\{#MyAppGuiExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;

procedure RemovePath(Param: string);
var
  Path, OutPath, Part: string;
  P: Integer;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Path) then
    exit;

  { Split on ';', drop the entry that matches Param (case-insensitive) and empty
    leftovers, then rejoin -- simpler and safer than computing delete offsets. }
  OutPath := '';
  while Length(Path) > 0 do
  begin
    P := Pos(';', Path);
    if P = 0 then
    begin
      Part := Path;
      Path := '';
    end
    else
    begin
      Part := Copy(Path, 1, P - 1);
      Path := Copy(Path, P + 1, Length(Path));
    end;
    if (Trim(Part) <> '') and (CompareText(Part, Param) <> 0) then
    begin
      if OutPath <> '' then
        OutPath := OutPath + ';';
      OutPath := OutPath + Part;
    end;
  end;

  RegWriteStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OutPath);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemovePath(ExpandConstant('{app}'));
end;
