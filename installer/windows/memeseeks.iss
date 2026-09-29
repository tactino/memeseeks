; 迷因捕手 · memeseeks — the Windows installer (Inno Setup 6). Built by build.ps1, which passes
; AppVersion, BuildDir (holding app\) and LangFile (the Chinese translation).
;
; A per-user install, no administrator needed. Pages: where the program goes, then where the library and the
; models go. launcher.json in the program folder records the last two; the shortcuts start the app in the
; notification area (memeseeks.tray). Uninstalling removes the program folder (and the models, if they are in it)
; but never the library, which may not be put inside the program folder for that reason.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef BuildDir
  #define BuildDir "build"
#endif

[Setup]
AppId={{6C4E2B9A-3F7D-4E1B-9C5A-7D2E8F4B1A63}
AppName=迷因捕手
AppVersion={#AppVersion}
AppVerName=迷因捕手 {#AppVersion}
AppPublisher=memeseeks
AppPublisherURL=https://github.com/tactino/memeseeks
AppSupportURL=https://github.com/tactino/memeseeks/issues
DefaultDirName={localappdata}\Programs\memeseeks
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#BuildDir}
OutputBaseFilename=memeseeks-windows-setup
SetupIconFile={#BuildDir}\app\memeseeks.ico
UninstallDisplayIcon={app}\memeseeks.ico
UninstallDisplayName=迷因捕手
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
#ifdef LangFile
Name: "chs"; MessagesFile: "{#LangFile}"
#else
Name: "en"; MessagesFile: "compiler:Default.isl"
#endif

[Tasks]
Name: "startmenu"; Description: "在开始菜单里放一个「迷因捕手」"
Name: "desktopicon"; Description: "在桌面放一个「迷因捕手」"
Name: "startup"; Description: "开机时自动启动（在右下角待命）"; Flags: unchecked

[InstallDelete]
; an update starts from a clean Python, so packages the new version dropped (0.4.0: PyTorch) don't linger
Type: filesandordirs; Name: "{app}\python"

[Files]
Source: "{#BuildDir}\app\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{userprograms}\迷因捕手"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m memeseeks.tray"; WorkingDir: "{app}"; IconFilename: "{app}\memeseeks.ico"; Comment: "迷因捕手 · memeseeks"; AppUserModelID: "memeseeks.memeseeks"; Tasks: startmenu
Name: "{userdesktop}\迷因捕手"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m memeseeks.tray"; WorkingDir: "{app}"; IconFilename: "{app}\memeseeks.ico"; Comment: "迷因捕手 · memeseeks"; AppUserModelID: "memeseeks.memeseeks"; Tasks: desktopicon
Name: "{userstartup}\迷因捕手"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m memeseeks.tray"; WorkingDir: "{app}"; IconFilename: "{app}\memeseeks.ico"; AppUserModelID: "memeseeks.memeseeks"; Tasks: startup

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-m memeseeks.tray"; WorkingDir: "{app}"; Description: "现在启动迷因捕手（第一次会下载约 3.9 GB 的模型）"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; everything under the program folder, the models among it when they are there; the library never is
Type: filesandordirs; Name: "{app}"

[Code]
var
  PlacesPage: TInputDirWizardPage;
  DefaultModels: String;

function StopRunningApp(): Boolean;
var
  Code: Integer;
  Cmd: String;
begin
  // the app runs as <program folder>\python\pythonw.exe: stop that one only, never other Python programs
  Cmd := '-NoProfile -Command "Get-CimInstance Win32_Process -Filter ''Name=''''pythonw.exe'''' or Name=''''python.exe'''''' | '
    + 'Where-Object { $_.ExecutablePath -like ''' + ExpandConstant('{app}') + '\*'' } | '
    + 'ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"';
  Result := Exec('powershell.exe', Cmd, '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

procedure InitializeWizard();
var
  Lib: String;
begin
  PlacesPage := CreateInputDirPage(wpSelectDir, '图库和模型放在哪', '可以都放在 C 盘以外',
    '图库：你的图集、索引和采集来的图。卸载迷因捕手时不会删除它；已经有图库的话，选它所在的文件夹。' + #13#10 +
    '模型：第一次启动时下载，约 3.9 GB。已经下载过的话（Hugging Face 缓存），选那个文件夹就不用再下。',
    False, '');
  PlacesPage.Add('图库：');
  PlacesPage.Add('模型：');
  Lib := GetPreviousData('Library', ExpandConstant('{%USERPROFILE}') + '\.memeseeks');
  PlacesPage.Values[0] := ExpandConstant('{param:LIBRARY|' + Lib + '}');
  PlacesPage.Values[1] := GetPreviousData('Models', '');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  // the models follow the program folder unless you chose somewhere else
  if (CurPageID = PlacesPage.ID) and ((PlacesPage.Values[1] = '') or (PlacesPage.Values[1] = DefaultModels)) then begin
    DefaultModels := AddBackslash(WizardDirValue()) + 'models';
    PlacesPage.Values[1] := DefaultModels;
  end;
end;

function Inside(Path, Folder: String): Boolean;
begin
  Result := Pos(AddBackslash(Lowercase(Folder)), AddBackslash(Lowercase(Path))) = 1;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = PlacesPage.ID) and Inside(PlacesPage.Values[0], WizardDirValue()) then begin
    MsgBox('图库不能放在程序文件夹里面：卸载时程序文件夹会被整个删除。请换一个位置。', mbError, MB_OK);
    Result := False;
  end;
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'Library', PlacesPage.Values[0]);
  SetPreviousData(PreviousDataKey, 'Models', PlacesPage.Values[1]);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningApp();  // an update: the running copy holds its files
  Result := '';
end;

function JsonText(S: String): String;
begin
  Result := S;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Lines: TArrayOfString;
  Models: String;
begin
  if CurStep = ssPostInstall then begin
    Models := PlacesPage.Values[1];
    if Models = '' then Models := ExpandConstant('{app}\models');
    SetArrayLength(Lines, 1);
    Lines[0] := '{"library": "' + JsonText(PlacesPage.Values[0]) + '", "models": "' + JsonText(Models) + '"}';
    SaveStringsToUTF8File(ExpandConstant('{app}\launcher.json'), Lines, False);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then StopRunningApp();
end;
