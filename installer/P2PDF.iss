; P2PDF — Professional Inno Setup Script
; Generates standalone per-user Windows installer for P2PDF

#define MyAppName "P2PDF"
#define MyAppVersion "1.5.0"
#define MyAppPublisher "Rudraksh Deshmukh"
#define MyAppDescription "Photo to PDF Converter for Windows"
#define MyAppExeName "P2PDF.exe"
#define MyAppId "{{C8E19B1A-7F42-4D66-8A6A-1B8D8F4A841B}}"

[Setup]
; Unique application identifier
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppComments={#MyAppDescription}

; Per-user non-administrative installation
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Destination output
OutputDir=..\dist
OutputBaseFilename=P2PDF-Setup-v{#MyAppVersion}
SetupIconFile=
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} — {#MyAppDescription}

; Compression settings
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; UI & Wizard styling
WizardStyle=modern
DisableWelcomePage=no
CloseApplications=yes
RestartApplications=no

; Windows Version Resource Metadata for Setup executable
VersionInfoVersion=1.5.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup — {#MyAppDescription}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion=1.5.0.0
VersionInfoCopyright=© {#MyAppPublisher} 2026 All rights reserved

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Main executable (overwritten on upgrade)
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Configuration file: installed if missing; PRESERVED on upgrade/reinstall and uninstall
Source: "..\p2pdf.ini"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall

; Documentation
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Registry]
; Windows File Explorer Context Menu Verb for supported image formats
; Installs exclusively to HKCU (per-user, no administrator privileges required)
Root: HKCU; Subkey: "Software\Classes\*\shell\CreatePDF_P2PDF"; ValueType: string; ValueName: ""; ValueData: "Create PDF with P2PDF"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\*\shell\CreatePDF_P2PDF"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\*\shell\CreatePDF_P2PDF"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#MyAppExeName}"",0"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\*\shell\CreatePDF_P2PDF"; ValueType: string; ValueName: "AppliesTo"; ValueData: "System.FileExtension:="".jpg"" OR System.FileExtension:="".jpeg"" OR System.FileExtension:="".png"" OR System.FileExtension:="".webp"" OR System.FileName:=""*.jpg"" OR System.FileName:=""*.jpeg"" OR System.FileName:=""*.png"" OR System.FileName:=""*.webp"""; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\*\shell\CreatePDF_P2PDF\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey

[Icons]
; Send To shortcut for instant alternative access
Name: "{usersendto}\Create PDF with P2PDF"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; IconIndex: 0

[Run]
; Optional post-install action to view Quick Start Guide
Filename: "{app}\{#MyAppExeName}"; Description: "View How to Use P2PDF (Quick Start Guide)"; Flags: postinstall skipifsilent nowait unchecked
