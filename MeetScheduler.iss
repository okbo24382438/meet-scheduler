#define MyAppVersion "0.6.0"

[Setup]
AppId={{A2B148A9-7073-43D3-8E87-7C5ACF97EE63}
AppName=Meet Scheduler
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\MeetScheduler
DefaultGroupName=Meet Scheduler
PrivilegesRequired=lowest
OutputDir=release\installer
OutputBaseFilename=MeetScheduler-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\MeetScheduler.exe

[Files]
Source: "release\v0.6.0\MeetScheduler.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "release\v0.6.0\scheduler.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "release\v0.6.0\broadcast_runner.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "release\v0.6.0\img\bg_3.jpg"; DestDir: "{app}\img"; Flags: ignoreversion
Source: "release\v0.6.0\schedule.json"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "release\v0.6.0\img\icon_meet_scheduler.ico"; DestDir: "{app}\img"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Meet Scheduler"; Filename: "{app}\MeetScheduler.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Meet Scheduler"; Filename: "{app}\MeetScheduler.exe"; WorkingDir: "{app}"; IconFilename: "{app}\img\icon_meet_scheduler.ico"
Name: "{autoprograms}\Meet Scheduler"; Filename: "{app}\MeetScheduler.exe"; WorkingDir: "{app}"; IconFilename: "{app}\img\icon_meet_scheduler.ico"

[Run]
Filename: "{app}\MeetScheduler.exe"; Description: "Meet Scheduler 실행"; Flags: postinstall nowait skipifsilent