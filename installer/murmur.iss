; Inno Setup script for Murmur Desktop: MurmurSetup-<version>.exe.
; Built by scripts/build_installer.py, which passes /DAppVersion (from murmur/ui/window.py) and
; /DSourceDir (the PyInstaller folder, dist\Murmur).
;
; - Installs for the current user only (no admin prompt) into %LOCALAPPDATA%\Programs\Murmur.
; - Downloads the speech model (460 MB, SHA-256 checked) into %USERPROFILE%\.murmur\models, next
;   to the history, unless it's already there, so updates and reinstalls don't download it again.
; - Start menu shortcut, and optionally one in Startup running "Murmur.exe --background", like
;   scripts/shortcuts.ps1 (same shortcut names, so it replaces a setup.bat install's shortcuts).
; - The uninstaller asks before deleting %USERPROFILE%\.murmur (history, settings, model).

#ifndef AppVersion
  #error Pass /DAppVersion=x.y.z (scripts/build_installer.py does)
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\Murmur"
#endif

#define ModelName "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
#define ModelUrl "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/" + ModelName + ".tar.bz2"
; From the GitHub release asset's digest (gh api repos/k2-fsa/sherpa-onnx/releases/tags/asr-models).
#define ModelSha256 "157c157bc51155e03e37d2466522a3a737dd9c72bb25f36eb18912964161e1ad"
; Unpacked (the download itself is 482 MB).
#define ModelBytes 661000000

[Setup]
AppId={{8C49DE49-04A4-4AC5-A4FE-4EA5920FC63C}
AppName=Murmur
AppVersion={#AppVersion}
AppVerName=Murmur {#AppVersion}
AppPublisher=Murmur
AppPublisherURL=https://github.com/rohitsinghcoder/murmur-desktop
AppSupportURL=https://github.com/rohitsinghcoder/murmur-desktop/issues
AppComments=Private, on-device voice typing. Hold Right Ctrl, speak, let go.
VersionInfoVersion={#AppVersion}
VersionInfoProductName=Murmur Desktop
VersionInfoDescription=Murmur Setup
; Per user: no admin prompt, installed into %LOCALAPPDATA%\Programs\Murmur.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\Murmur
DisableDirPage=yes
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Windows 10 1809 or later (tar.exe, which unpacks the model, is in Windows since 1803).
MinVersion=10.0.17763
WizardStyle=modern dynamic
WizardSmallImageFile=..\assets\murmur.png
SetupIconFile=..\assets\murmur.ico
UninstallDisplayIcon={app}\Murmur.exe
UninstallDisplayName=Murmur
OutputBaseFilename=MurmurSetup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
; Room for the unpacked model, which isn't one of the [Files] (it also makes the size in
; Settings > Apps right: about 1 GB with the model).
ExtraDiskSpaceRequired={#ModelBytes}
; If Murmur.exe is still running (the [Code] below asks to quit it first), close it rather than
; fail on files in use.
CloseApplications=force
RestartApplications=no

[Tasks]
Name: startup; Description: "Start Murmur when Windows starts (in the tray)"

[InstallDelete]
; A clean runtime folder on updates, so files an older version had don't linger.
Type: filesandordirs; Name: "{app}\_internal"
; The Startup shortcut is kept only while the task is chosen (it may also be setup.bat's).
Type: files; Name: "{userstartup}\Murmur.lnk"; Tasks: not startup

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; The same AppUserModelID Murmur sets for itself, so Windows groups its windows and
; notifications under this shortcut.
Name: "{userprograms}\Murmur"; Filename: "{app}\Murmur.exe"; WorkingDir: "{app}"; \
  Comment: "Murmur: private voice typing. Hold Right Ctrl to dictate."; AppUserModelID: "Murmur.Desktop"
Name: "{userstartup}\Murmur"; Filename: "{app}\Murmur.exe"; Parameters: "--background"; WorkingDir: "{app}"; \
  Comment: "Starts Murmur in the tray."; Tasks: startup

[Run]
Filename: "{app}\Murmur.exe"; Description: "Start Murmur"; Flags: nowait postinstall skipifsilent

[Code]
const
  ModelName = '{#ModelName}';
  // Held by a running Murmur (murmur/__main__.py), installed or run from source.
  MurmurMutex = 'Local\MurmurDictation';
  QuitMurmur = 'Murmur is running. Quit it first: right-click its icon in the system tray ' +
               '(bottom right, maybe under the ^ arrow) and click Quit Murmur. Then click Retry.';

var
  DownloadPage: TDownloadWizardPage;
  UnpackPage: TOutputProgressWizardPage;

function MurmurDir: String;
begin
  // Python's Path.home() / ".murmur", where Murmur keeps history and settings.
  Result := ExpandConstant('{%USERPROFILE}\.murmur');
end;

function ModelsDir: String;
begin
  Result := MurmurDir + '\models';
end;

function ModelDir: String;
begin
  Result := ModelsDir + '\' + ModelName;
end;

function ModelInstalled: Boolean;
begin
  Result := FileExists(ModelDir + '\tokens.txt') and FileExists(ModelDir + '\encoder.int8.onnx') and
            FileExists(ModelDir + '\decoder.int8.onnx') and FileExists(ModelDir + '\joiner.int8.onnx');
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  while Result and CheckForMutexes(MurmurMutex) do begin
    if WizardSilent then begin
      Log('Murmur is running; CloseApplications will close it if its files are in use.');
      Break;
    end;
    Result := MsgBox(QuitMurmur, mbInformation, MB_RETRYCANCEL) = IDRETRY;
  end;
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage('Downloading the speech model',
    'Murmur recognises speech on this computer with NVIDIA''s Parakeet model. It is downloaded ' +
    'once (460 MB) and kept for future updates.', nil);
  DownloadPage.ShowBaseNameInsteadOfUrl := True;
  UnpackPage := CreateOutputProgressPage('Unpacking the speech model', 'This takes a minute or two.');
end;

// Unpacks the downloaded model into ModelDir. Returns '' or what went wrong.
function UnpackModel(Archive: String): String;
var
  Temp: String;
  Code: Integer;
begin
  Result := '';
  Temp := ModelsDir + '\.unpacking';
  DelTree(Temp, True, True, True);
  if not ForceDirectories(Temp) then
    Result := 'Couldn''t create ' + Temp
  else if not Exec(ExpandConstant('{sys}\tar.exe'), '-xjf "' + Archive + '" -C "' + Temp + '"', '',
                   SW_HIDE, ewWaitUntilTerminated, Code) then
    Result := 'Couldn''t run tar.exe: ' + SysErrorMessage(Code)
  else if Code <> 0 then
    Result := Format('tar.exe failed (exit code %d)', [Code])
  else begin
    // Moved into place only once complete, so a half-unpacked model never looks installed.
    DelTree(ModelDir, True, True, True);
    if not RenameFile(Temp + '\' + ModelName, ModelDir) then
      Result := 'Couldn''t move the model into ' + ModelDir;
  end;
  DelTree(Temp, True, True, True);
end;

function DownloadModel: Boolean;
var
  Archive, Error: String;
begin
  Result := False;
  DownloadPage.Clear;
  DownloadPage.Add('{#ModelUrl}', 'murmur-model.tar.bz2', '{#ModelSha256}');
  DownloadPage.Show;
  try
    try
      DownloadPage.Download;  // into {tmp}, checking the SHA-256
      Result := True;
    except
      if DownloadPage.AbortedByUser then
        Log('Model download cancelled.')
      else
        SuppressibleMsgBox('Couldn''t download the speech model: ' + AddPeriod(GetExceptionMessage) + #13#10#13#10 +
          'Check your internet connection, then click Install to try again.',
          mbError, MB_OK, IDOK);
    end;
  finally
    DownloadPage.Hide;
  end;
  if not Result then
    Exit;

  Archive := ExpandConstant('{tmp}\murmur-model.tar.bz2');
  UnpackPage.SetText('Unpacking the speech model into ' + ModelsDir + '...', '');
  UnpackPage.ProgressBar.Style := npbstMarquee;
  UnpackPage.Show;
  try
    Error := UnpackModel(Archive);
  finally
    UnpackPage.Hide;
    DeleteFile(Archive);
  end;
  if Error <> '' then begin
    SuppressibleMsgBox('Couldn''t unpack the speech model: ' + AddPeriod(Error) + #13#10#13#10 +
      'Click Install to try again.', mbError, MB_OK, IDOK);
    Result := False;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  // Before installing anything, get the model, unless it's already there. On failure Setup
  // stays on the Ready page so the user can retry (a silent install exits with an error).
  Result := True;
  if (CurPageID = wpReady) and not ModelInstalled then
    Result := DownloadModel;
end;

function InitializeUninstall: Boolean;
begin
  Result := True;
  while Result and CheckForMutexes(MurmurMutex) do begin
    if UninstallSilent then
      Break;
    Result := MsgBox(QuitMurmur, mbInformation, MB_RETRYCANCEL) = IDRETRY;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and DirExists(MurmurDir) and not UninstallSilent then
    if MsgBox('Also delete your Murmur data? This removes your dictation history and settings, ' +
              'and the speech model (about 630 MB), from ' + MurmurDir + '.' + #13#10#13#10 +
              'Click No to keep them for when you install Murmur again.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(MurmurDir, True, True, True);
end;
