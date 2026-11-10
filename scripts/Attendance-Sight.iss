#define AppName "Attendance-Sight"
#define AppVersion "1.3.4"

[Setup]
AppId={{B1A3F4DA-6D42-4A4D-A1D7-CE445C5F74E1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Attendance-Sight
DefaultDirName={localappdata}\Programs\AttendSight
DefaultGroupName=Attendance-Sight
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=Attendance-Sight-Setup-1.3.4
SetupIconFile=..\build\attendsight.ico
UninstallDisplayIcon={app}\Attendance-Sight.exe
CloseApplications=force
RestartApplications=no
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\Attendance-Sight-1.3.4.exe"; DestDir: "{app}"; DestName: "Attendance-Sight.exe"; Flags: ignoreversion

[InstallDelete]
Type: files; Name: "{app}\AttendSight.exe"
Type: files; Name: "{userprograms}\AttendSight\AttendSight.lnk"
Type: files; Name: "{autodesktop}\AttendSight.lnk"

[Icons]
Name: "{group}\Attendance-Sight"; Filename: "{app}\Attendance-Sight.exe"
Name: "{autodesktop}\Attendance-Sight"; Filename: "{app}\Attendance-Sight.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Attendance-Sight.exe"; Description: "Launch Attendance-Sight"; Flags: postinstall nowait skipifsilent
