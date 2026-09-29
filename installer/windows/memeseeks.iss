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
; a trial build (/DPreview) is another app to Windows: its own id, no shortcuts, nothing started afterwards
#ifdef Preview
  #define AppGuid "{{0B1D6A2E-5C3F-4A7B-8E9D-1F2A3B4C5D6E}"
#else
  #define AppGuid "{{6C4E2B9A-3F7D-4E1B-9C5A-7D2E8F4B1A63}"
#endif

[Setup]
AppId={#AppGuid}
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
; the app's look (docs/design.md): warm paper, the cat, black Mondrian lines (pictures drawn by art/make.py)
WizardStyle=modern light hidebevels includetitlebar
WizardBackColor=#F3EFE4
WizardImageFile=art\wizard-202.png,art\wizard-336.png,art\wizard-534.png
WizardImageBackColor=#F3EFE4
WizardSmallImageFile=art\small-58.png,art\small-97.png,art\small-159.png
WizardSmallImageBackColor=#F3EFE4
DisableWelcomePage=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
#ifdef LangFile
Name: "chs"; MessagesFile: "{#LangFile}"
#else
Name: "en"; MessagesFile: "compiler:Default.isl"
#endif

[Messages]
WelcomeLabel1=欢迎安装迷因捕手
WelcomeLabel2=把存过的梗图收进一个地方，以后用你记得的那句话把它找回来。%n%n不需要管理员权限，装好约占 400 MB；第一次启动时还会下载约 1 GB 的模型。
FinishedHeadingLabel=装好了
FinishedLabelNoIcons=迷因捕手已经装好。
FinishedLabel=迷因捕手已经装好，开始菜单或桌面上的「迷因捕手」都能打开它。关掉窗口后它会待在屏幕右下角，点那只猫就回来。

[Tasks]
Name: "startmenu"; Description: "在开始菜单里放一个「迷因捕手」"
Name: "desktopicon"; Description: "在桌面放一个「迷因捕手」"
Name: "startup"; Description: "开机时自动启动（在右下角待命）"; Flags: unchecked

[InstallDelete]
; an update starts from a clean Python, so packages the new version dropped (0.4.0: PyTorch) don't linger
Type: filesandordirs; Name: "{app}\python"

[Files]
Source: "{#BuildDir}\app\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

#ifndef Preview
[Icons]
Name: "{userprograms}\迷因捕手"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m memeseeks.tray"; WorkingDir: "{app}"; IconFilename: "{app}\memeseeks.ico"; Comment: "迷因捕手 · memeseeks"; AppUserModelID: "memeseeks.memeseeks"; Tasks: startmenu
Name: "{userdesktop}\迷因捕手"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m memeseeks.tray"; WorkingDir: "{app}"; IconFilename: "{app}\memeseeks.ico"; Comment: "迷因捕手 · memeseeks"; AppUserModelID: "memeseeks.memeseeks"; Tasks: desktopicon
Name: "{userstartup}\迷因捕手"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m memeseeks.tray"; WorkingDir: "{app}"; IconFilename: "{app}\memeseeks.ico"; AppUserModelID: "memeseeks.memeseeks"; Tasks: startup

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-m memeseeks.tray"; WorkingDir: "{app}"; Description: "现在启动迷因捕手（第一次会下载约 1 GB 的模型）"; Flags: postinstall nowait skipifsilent
#endif

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
    '模型：第一次启动时下载，约 1 GB。已经下载过的话（Hugging Face 缓存），选那个文件夹就不用再下。',
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

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo,
  MemoGroupInfo, MemoTasksInfo: String): String;
begin
  // the ready page lists the library and the models too, not only the program folder
  Result := MemoDirInfo + NewLine + NewLine + '图库：' + NewLine + Space + PlacesPage.Values[0] + NewLine + NewLine +
    '模型：' + NewLine + Space + PlacesPage.Values[1];
  if MemoTasksInfo <> '' then Result := Result + NewLine + NewLine + MemoTasksInfo;
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
