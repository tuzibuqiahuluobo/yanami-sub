#ifndef AppSource
  #error AppSource must point to the packaged Yanami Sub application directory.
#endif

#ifndef AppVersion
  #define AppVersion "0.1.0-rc.6.post8"
#endif

#ifndef OutputDir
  #define OutputDir "."
#endif

#ifndef SetupIcon
  #error SetupIcon must point to the Yanami Sub .ico file.
#endif

#ifndef ChineseLanguageFile
  #error ChineseLanguageFile must point to the installer language file.
#endif

#define AppPublisher "tuzibuqiahuluobo"
#define AppExeName "Yanami Sub.exe"

[Setup]
AppId={{D4C7C84D-3037-4CF5-B9CA-9EA30265414F}
AppName=Yanami Sub
AppVersion={#AppVersion}
AppVerName=Yanami Sub {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\Yanami Sub
DefaultGroupName=Yanami Sub
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=Yanami-Sub-{#AppVersion}-Setup
SetupIconFile={#SetupIcon}
UninstallDisplayIcon={app}\Yanami Sub.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
; Do not inherit the old FineSub Desktop directory. New installs should use
; the Yanami Sub folder; an in-place migration can still choose the old path.
UsePreviousAppDir=no
UsePreviousTasks=yes
CloseApplications=yes
RestartApplications=no
; Yanami Sub ships a single installer language, so every Windows locale
; receives the same Simplified Chinese interface without a language picker.
ShowLanguageDialog=no

[Languages]
; Simplified Chinese is not one of the translations Inno Setup ships, so it is
; vendored beside this script (see ChineseSimplified.isl for its provenance).
; Keep this as the only entry so automatic locale detection cannot select the
; compiler's English default on a non-Chinese Windows installation.
Name: "chinesesimp"; MessagesFile: "{#ChineseLanguageFile}"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Keep the original AppId so RC3 can migrate an existing installation. Remove
; obsolete launchers and shortcuts so only the Yanami Sub entry points remain.
Type: files; Name: "{app}\FineSub Desktop.exe"
Type: files; Name: "{app}\updater\FineSub Desktop Updater.exe"
Type: files; Name: "{autoprograms}\FineSub Desktop.lnk"
Type: files; Name: "{autodesktop}\FineSub Desktop.lnk"

[Icons]
Name: "{autoprograms}\Yanami Sub"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"
Name: "{autodesktop}\Yanami Sub"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,Yanami Sub}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop Yanami Sub and its worker children before their installed files vanish.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM ""{#AppExeName}"""; Flags: runhidden waituntilterminated; RunOnceId: "StopYanamiSub"

[Code]
{ The marker separates an installed copy (personal data in
  %LOCALAPPDATA%\FineSub) from a portable one (everything beside the exe).
  Only this installer writes it; update payloads never contain it and the
  in-app updater preserves it. }
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SaveStringToFile(ExpandConstant('{app}\installed.marker'), '', False);
end;

{ Inno only removes files it installed, so the state FineSub creates beside the
  exe has to go explicitly - but only the half that can be recreated (managed
  Python, models, download caches). The two kinds that cannot are each asked
  about separately, matching `finesub uninstall`: finished subtitles under
  tasks\, and personal data (settings, API keys, knowledge base) which lives
  outside the install directory and is shared with the CLI and portable copies.
  Models or subtitles that were moved elsewhere with `finesub relocate` are not
  touched at all: another installation is probably reading them. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Subtitles: String;
  PersonalData: String;
begin
  if CurUninstallStep <> usPostUninstall then
    exit;
  DelTree(ExpandConstant('{app}\runtime'), True, True, True);
  DelTree(ExpandConstant('{app}\models'), True, True, True);
  DelTree(ExpandConstant('{app}\cache'), True, True, True);
  DelTree(ExpandConstant('{app}\app'), True, True, True);
  DelTree(ExpandConstant('{app}\.update'), True, True, True);
  DeleteFile(ExpandConstant('{app}\installed.marker'));
  { Neither of the two irreplaceable kinds is touched when nobody can answer
    for them. Under /SUPPRESSMSGBOXES Inno answers a MsgBox with its *default*
    button, and the default for MB_YESNO is Yes -- so a silent uninstall used
    to agree to deleting a user's finished subtitles and their whole data
    folder, including API keys and the knowledge base, without anyone ever
    being asked. The comment above already says these two are asked about
    separately because they cannot be recreated; not being able to ask is a
    reason to keep them, not to assume consent. }
  Subtitles := ExpandConstant('{app}\tasks');
  if DirExists(Subtitles) and not UninstallSilent() then
  begin
    if MsgBox(
      '是否同时删除 Yanami Sub 已生成的字幕？'
        + #13#10 + Subtitles,
      mbConfirmation, MB_YESNO
    ) = IDYES then
      DelTree(Subtitles, True, True, True);
  end;
  RemoveDir(ExpandConstant('{app}'));
  PersonalData := ExpandConstant('{localappdata}\FineSub');
  if DirExists(PersonalData) and not UninstallSilent() then
  begin
    if MsgBox(
      '是否同时删除 FineSub 数据目录（设置、API Key、知识库和任务历史）？'
        + '此目录与 FineSub CLI 及本机便携版共享。'
        + #13#10 + PersonalData,
      mbConfirmation, MB_YESNO
    ) = IDYES then
      DelTree(PersonalData, True, True, True);
  end;
end;
