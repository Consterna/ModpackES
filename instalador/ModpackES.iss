; Instalador de ModpackES (Inno Setup 6.3 o superior). Lo arma scripts/construir_exe.py --instalador, que pasa:
;   /DVersion=2.1.0  /DOrigen=<carpeta onedir de PyInstaller>  /DSalida=<carpeta del instalador>
;   /DIcono=<.ico>   /DLicencia=<LICENSE>
; Se instala para el usuario actual (sin pedir permisos de administrador).

#ifndef Version
  #error Falta /DVersion
#endif

[Setup]
AppId={{6B8F2C1E-4D7A-4E59-9A3B-2F1C8D6E0A47}
AppName=ModpackES
AppVersion={#Version}
AppVerName=ModpackES {#Version}
AppPublisher=Cristian
AppPublisherURL=https://github.com/Consterna/ModpackES
AppSupportURL=https://github.com/Consterna/ModpackES/issues
AppUpdatesURL=https://github.com/Consterna/ModpackES/releases
DefaultDirName={autopf}\ModpackES
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Salida}
OutputBaseFilename=ModpackES-instalador
SetupIconFile={#Icono}
UninstallDisplayIcon={app}\ModpackES.exe
UninstallDisplayName=ModpackES {#Version}
LicenseFile={#Licencia}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
VersionInfoVersion={#Version}
VersionInfoCompany=Cristian
VersionInfoDescription=Instalador de ModpackES
VersionInfoCopyright=© 2026 Cristian. Licencia GPL-3.0-or-later

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#Origen}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ModpackES"; Filename: "{app}\ModpackES.exe"
Name: "{autodesktop}\ModpackES"; Filename: "{app}\ModpackES.exe"; Tasks: escritorio

[Run]
Filename: "{app}\ModpackES.exe"; Description: "{cm:LaunchProgram,ModpackES}"; Flags: nowait postinstall skipifsilent
