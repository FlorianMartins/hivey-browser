; Hivey Browser setup wizard (Windows x64, per-user, no administrator rights).
;
; A front end to Chromium's mini_installer, which stays the install and
; update engine: the wizard asks for the options, writes them as initial
; preferences, and runs the embedded mini_installer silently with
;   --do-not-launch-chrome --installerdata=<prefs> [--hivey-install-dir=<dir>]
; Chromium's setup then installs, registers the uninstaller (Settings > Apps)
; and creates the shortcuts. The browser's self-updater keeps downloading the
; bare mini_installer (hivey-browser-windows-x64-update.exe), which updates
; the install in its registered folder.
;
; Built by scripts/hb.py package (makensis runs on Linux too):
;   makensis -V3 -INPUTCHARSET UTF8 \
;     -DVERSION=156.0.8078.4711 \
;     -DMINI_INSTALLER=out/Default/mini_installer.exe \
;     -DICON=chrome/installer/mini_installer/mini_installer.ico \
;     -DLICENSE_FILE=LICENSE \
;     -DADDONS_NSH=<build>/bundled-extensions/setup-addons.nsh \
;     -DOUTFILE=dist/hivey-browser-<version>-windows-x64-installer.exe \
;     installer/windows/hivey-setup.nsi
;
; Command line (silent installs, CI, deployments):
;   /S                       silent, with the defaults below
;   --do-not-launch-chrome   same as /S (the switch the updater and the CI give
;                            mini_installer, so this file can stand in for it)
;   /D=<folder>              install folder of a new install (last, unquoted)
;   /PRIVACY                 privacy mode on (off by default)
;   /NODESKTOP /NOTASKBAR    no desktop shortcut / no taskbar pin
;   /NO-<add-on>             without that add-on, e.g. /NO-hivey-ai
;   /LAUNCH                  start the browser after a silent install
;   --verbose-logging        passed on to the installer
; The exit code is mini_installer's (0 = installed or updated).

Unicode true
ManifestDPIAware true
RequestExecutionLevel user
; mini_installer.exe is already LZMA-compressed: it is stored as is (fast
; build, same size).
SetCompressor lzma

!macro _HiveyRequire NAME
  !ifndef ${NAME}
    !error "Missing -D${NAME}=...: VERSION, MINI_INSTALLER, ICON, LICENSE_FILE, ADDONS_NSH and OUTFILE are required"
  !endif
!macroend
!insertmacro _HiveyRequire VERSION
!insertmacro _HiveyRequire MINI_INSTALLER
!insertmacro _HiveyRequire ICON
!insertmacro _HiveyRequire LICENSE_FILE
!insertmacro _HiveyRequire ADDONS_NSH
!insertmacro _HiveyRequire OUTFILE
!ifndef PRODUCT_NAME
  !define PRODUCT_NAME "Hivey Browser"
!endif
!ifndef COMPANY_NAME
  !define COMPANY_NAME "Hivey"
!endif
; brand.json install.company_path / product_path: Chromium's own default
; folder, and its uninstall key ("<company> <product>").
!ifndef INSTALL_SUBDIR
  !define INSTALL_SUBDIR "Hivey\Browser"
!endif
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Hivey Browser"
!define DEFAULT_DIR "$LOCALAPPDATA\${INSTALL_SUBDIR}\Application"
!define USER_DATA_DIR "$LOCALAPPDATA\${INSTALL_SUBDIR}\User Data"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "Sections.nsh"
!include "WinMessages.nsh"
!include "WinVer.nsh"
!include "x64.nsh"
!include "${ADDONS_NSH}"

Name "${PRODUCT_NAME}"
OutFile "${OUTFILE}"
; The trailing backslash: a folder picked with "Browse" is used as is (no
; "\Application" appended); DirectoryLeave adds a subfolder when needed.
InstallDir "${DEFAULT_DIR}\"
BrandingText "${PRODUCT_NAME} ${VERSION}"
ShowInstDetails hide

Var IsUpdate      ; 1: already installed, its folder is kept
Var Params        ; command line
Var PrefsFile
Var Verbose

;--------------------------------------------------------------------------
; Interface

!define MUI_ICON "${ICON}"
!define MUI_ABORTWARNING
; The browser's colors (Aura): dark ink, light text; the welcome and finish
; pages, the header and the progress log follow them.
!define MUI_BGCOLOR "13141F"
!define MUI_TEXTCOLOR "F2F3FF"
!define MUI_HEADER_TRANSPARENT_TEXT
!define MUI_LICENSEPAGE_BGCOLOR "1B1C2B"
!define MUI_INSTFILESPAGE_COLORS "E6E7FF 1B1C2B"
!define MUI_INSTFILESPAGE_PROGRESSBAR "colored"
!define MUI_WELCOMEFINISHPAGE_BITMAP_STRETCH "FitControl"
!define MUI_COMPONENTSPAGE_SMALLDESC
!ifdef WELCOME_BMP
  !define MUI_WELCOMEFINISHPAGE_BITMAP "${WELCOME_BMP}"
!endif
!ifdef HEADER_BMP
  !define MUI_HEADERIMAGE
  !define MUI_HEADERIMAGE_RIGHT
  !define MUI_HEADERIMAGE_BITMAP "${HEADER_BMP}"
  !define MUI_HEADERIMAGE_BITMAP_STRETCH "FitControl"
!endif

!define MUI_WELCOMEPAGE_TITLE "$(WelcomeTitle)"
!define MUI_WELCOMEPAGE_TEXT "$(WelcomeText)"
!insertmacro MUI_PAGE_WELCOME

!insertmacro MUI_PAGE_LICENSE "${LICENSE_FILE}"

!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfUpdate
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE ComponentsLeave
!insertmacro MUI_PAGE_COMPONENTS

!define MUI_PAGE_CUSTOMFUNCTION_PRE SkipIfUpdate
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE DirectoryLeave
!insertmacro MUI_PAGE_DIRECTORY

!insertmacro MUI_PAGE_INSTFILES

!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "$(RunText)"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchBrowser
!insertmacro MUI_PAGE_FINISH

; The first language is the fallback for every other Windows language.
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "French"

!insertmacro HIVEY_ADDON_STRINGS

LangString WelcomeTitle ${LANG_ENGLISH} "Welcome to ${PRODUCT_NAME}"
LangString WelcomeTitle ${LANG_FRENCH} "Bienvenue dans ${PRODUCT_NAME}"
LangString WelcomeText ${LANG_ENGLISH} "This wizard installs ${PRODUCT_NAME} ${VERSION}, a privacy-first web browser, for your Windows account (no administrator rights needed).$\r$\n$\r$\nIf ${PRODUCT_NAME} is already installed, it is updated in its folder and your profile is kept.$\r$\n$\r$\nClick Next to continue."
LangString WelcomeText ${LANG_FRENCH} "Cet assistant installe ${PRODUCT_NAME} ${VERSION}, un navigateur web respectueux de la vie privée, pour votre compte Windows (sans droits d'administrateur).$\r$\n$\r$\nSi ${PRODUCT_NAME} est déjà installé, il est mis à jour dans son dossier et votre profil est conservé.$\r$\n$\r$\nCliquez sur Suivant pour continuer."
LangString SecBrowserName ${LANG_ENGLISH} "${PRODUCT_NAME} (required)"
LangString SecBrowserName ${LANG_FRENCH} "${PRODUCT_NAME} (requis)"
LangString SecBrowserDesc ${LANG_ENGLISH} "The browser. Updates install by themselves (Hivey Studio > About)."
LangString SecBrowserDesc ${LANG_FRENCH} "Le navigateur. Les mises à jour s'installent d'elles-mêmes (Hivey Studio > À propos)."
LangString GrpAddonsName ${LANG_ENGLISH} "Bundled add-ons"
LangString GrpAddonsName ${LANG_FRENCH} "Modules intégrés"
LangString GrpVpnName ${LANG_ENGLISH} "VPN (optional, free with an account)"
LangString GrpVpnName ${LANG_FRENCH} "VPN (facultatif, gratuit avec un compte)"
LangString GrpAddonsDesc ${LANG_ENGLISH} "Extensions that ship with the browser. An add-on left out is not installed in your profile."
LangString GrpAddonsDesc ${LANG_FRENCH} "Extensions livrées avec le navigateur. Un module décoché n'est pas installé dans votre profil."
LangString SecPrivacyName ${LANG_ENGLISH} "Privacy mode"
LangString SecPrivacyName ${LANG_FRENCH} "Mode confidentialité"
LangString SecPrivacyDesc ${LANG_ENGLISH} "Stricter defaults: armored mode (no JavaScript JIT), WebRTC without your local IP, no search suggestions, no preloading. Some heavy web apps get slower. Changeable in Hivey Studio."
LangString SecPrivacyDesc ${LANG_FRENCH} "Réglages plus stricts : mode blindé (sans JIT JavaScript), WebRTC sans votre IP locale, sans suggestions de recherche ni préchargement. Certaines applications web lourdes ralentissent. Modifiable dans Hivey Studio."
LangString SecDesktopName ${LANG_ENGLISH} "Desktop shortcut"
LangString SecDesktopName ${LANG_FRENCH} "Raccourci sur le bureau"
LangString SecDesktopDesc ${LANG_ENGLISH} "A ${PRODUCT_NAME} shortcut on the desktop (the Start menu always has one)."
LangString SecDesktopDesc ${LANG_FRENCH} "Un raccourci ${PRODUCT_NAME} sur le bureau (le menu Démarrer en a toujours un)."
LangString SecTaskbarName ${LANG_ENGLISH} "Pin to the taskbar"
LangString SecTaskbarName ${LANG_FRENCH} "Épingler à la barre des tâches"
LangString SecTaskbarDesc ${LANG_ENGLISH} "Pins ${PRODUCT_NAME} to the taskbar when Windows allows it."
LangString SecTaskbarDesc ${LANG_FRENCH} "Épingle ${PRODUCT_NAME} à la barre des tâches quand Windows le permet."
LangString RunText ${LANG_ENGLISH} "Start ${PRODUCT_NAME}"
LangString RunText ${LANG_FRENCH} "Lancer ${PRODUCT_NAME}"
LangString Installing ${LANG_ENGLISH} "Installing ${PRODUCT_NAME} ${VERSION}..."
LangString Installing ${LANG_FRENCH} "Installation de ${PRODUCT_NAME} ${VERSION}..."
LangString InstallFailed ${LANG_ENGLISH} "The installation failed (code $1). Details are in the chromium_installer.log file of your temporary folder (%TEMP%)."
LangString InstallFailed ${LANG_FRENCH} "L'installation a échoué (code $1). Les détails sont dans le fichier chromium_installer.log de votre dossier temporaire (%TEMP%)."
LangString InstalledIn ${LANG_ENGLISH} "Installed in $INSTDIR"
LangString InstalledIn ${LANG_FRENCH} "Installé dans $INSTDIR"
LangString OtherDir ${LANG_ENGLISH} "The installer kept the folder $INSTDIR."
LangString OtherDir ${LANG_FRENCH} "L'installateur a gardé le dossier $INSTDIR."
LangString DirSubfolder ${LANG_ENGLISH} "This folder already holds other files, and uninstalling deletes the whole install folder. ${PRODUCT_NAME} will go in its own subfolder:$\r$\n$\r$\n$INSTDIR"
LangString DirSubfolder ${LANG_FRENCH} "Ce dossier contient déjà d'autres fichiers, et la désinstallation supprime tout le dossier d'installation. ${PRODUCT_NAME} ira dans son propre sous-dossier :$\r$\n$\r$\n$INSTDIR"
LangString DirSystem ${LANG_ENGLISH} "Choose a folder outside Program Files and Windows: this per-user install needs no administrator rights and updates itself."
LangString DirSystem ${LANG_FRENCH} "Choisissez un dossier hors de Program Files et de Windows : cette installation par utilisateur se passe de droits d'administrateur et se met à jour seule."
LangString DirInvalid ${LANG_ENGLISH} "Choose a folder on a local drive, not the root of a drive."
LangString DirInvalid ${LANG_FRENCH} "Choisissez un dossier sur un disque local, pas la racine d'un disque."
LangString ProfileExists ${LANG_ENGLISH} "A ${PRODUCT_NAME} profile already exists on this account: the add-on and privacy choices only apply to a new profile. Change them in Hivey Studio and chrome://extensions."
LangString ProfileExists ${LANG_FRENCH} "Un profil ${PRODUCT_NAME} existe déjà sur ce compte : les choix de modules et de confidentialité ne s'appliquent qu'à un nouveau profil. Modifiez-les dans Hivey Studio et chrome://extensions."
LangString NeedWin10 ${LANG_ENGLISH} "${PRODUCT_NAME} needs 64-bit Windows 10 or later."
LangString NeedWin10 ${LANG_FRENCH} "${PRODUCT_NAME} nécessite Windows 10 64 bits ou plus récent."
LangString AlreadyRunning ${LANG_ENGLISH} "The ${PRODUCT_NAME} installer is already running."
LangString AlreadyRunning ${LANG_FRENCH} "L'installateur de ${PRODUCT_NAME} est déjà ouvert."

VIProductVersion "${VERSION}"
VIFileVersion "${VERSION}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "CompanyName" "${COMPANY_NAME}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "FileDescription" "${PRODUCT_NAME} Setup"
VIAddVersionKey /LANG=${LANG_ENGLISH} "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "LegalCopyright" "The Hivey Browser contributors"
VIAddVersionKey /LANG=${LANG_FRENCH} "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey /LANG=${LANG_FRENCH} "CompanyName" "${COMPANY_NAME}"
VIAddVersionKey /LANG=${LANG_FRENCH} "FileDescription" "Installation de ${PRODUCT_NAME}"
VIAddVersionKey /LANG=${LANG_FRENCH} "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_FRENCH} "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_FRENCH} "LegalCopyright" "The Hivey Browser contributors"

;--------------------------------------------------------------------------
; Components. The visible sections only carry the choices; the hidden
; "-Install" section, last, does the work.

Section "$(SecBrowserName)" SecBrowser
  SectionIn RO
SectionEnd

SectionGroup /e "$(GrpAddonsName)" SecAddons
  !insertmacro HIVEY_ADDON_SECTIONS
SectionGroupEnd

; Optional add-ons (a VPN): unchecked, the user's choice.
SectionGroup /e "$(GrpVpnName)" SecVpn
  !insertmacro HIVEY_ADDON_OPTIONAL_SECTIONS
SectionGroupEnd

Section "$(SecPrivacyName)" SecPrivacy
SectionEnd

Section "$(SecDesktopName)" SecDesktop
SectionEnd

Section "$(SecTaskbarName)" SecTaskbar
SectionEnd

Section "-Install" SecInstall
  SetDetailsPrint both
  DetailPrint "$(Installing)"
  ${IfNot} ${Silent}
    Call StartMarquee
  ${EndIf}
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  SetCompress off
  File "/oname=hivey-update.exe" "${MINI_INSTALLER}"
  SetCompress auto
  Call WritePrefs

  StrCpy $0 '"$PLUGINSDIR\hivey-update.exe" --do-not-launch-chrome --installerdata="$PrefsFile"'
  ${If} $IsUpdate != 1
    StrCpy $0 '$0 --hivey-install-dir="$INSTDIR"'
  ${EndIf}
  ${If} $Verbose == 1
    StrCpy $0 '$0 --verbose-logging'
  ${EndIf}
  DetailPrint "$0"
  ClearErrors
  ExecWait $0 $1
  ${If} ${Errors}
    StrCpy $1 -1
  ${EndIf}
  SetOutPath "$TEMP"  ; let $PLUGINSDIR go
  ${If} $1 != 0
    SetErrorLevel $1
    DetailPrint "$(InstallFailed)"
    MessageBox MB_ICONSTOP|MB_OK "$(InstallFailed)" /SD IDOK
    Abort
  ${EndIf}

  ; Where setup really installed (it keeps an existing install's folder and
  ; refuses an unsuitable one): the finish page launches that one.
  StrCpy $2 $INSTDIR
  ReadRegStr $0 HKCU "${UNINSTALL_KEY}" "InstallLocation"
  ${If} $0 != ""
  ${AndIf} ${FileExists} "$0\chrome.exe"
    StrCpy $INSTDIR $0
  ${EndIf}
  ${If} $INSTDIR != $2
    DetailPrint "$(OtherDir)"
  ${EndIf}
  DetailPrint "$(InstalledIn)"
  SetErrorLevel 0
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecBrowser} "$(SecBrowserDesc)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecAddons} "$(GrpAddonsDesc)"
  !insertmacro HIVEY_ADDON_DESCRIPTIONS
  !insertmacro MUI_DESCRIPTION_TEXT ${SecPrivacy} "$(SecPrivacyDesc)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "$(SecDesktopDesc)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecTaskbar} "$(SecTaskbarDesc)"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

;--------------------------------------------------------------------------
; Functions

; Push haystack, push needle; pops 1 if needle is in haystack (any case).
; Registers are kept.
Function StrContains
  Exch $R1  ; needle
  Exch
  Exch $R2  ; haystack
  Push $R3  ; result
  Push $R4  ; position
  Push $R5
  Push $R6  ; needle length
  StrLen $R6 $R1
  StrCpy $R4 0
  StrCpy $R3 0
  ${Do}
    StrCpy $R5 $R2 $R6 $R4
    ${If} $R5 == ""
      ${Break}
    ${EndIf}
    ${If} $R5 == $R1
      StrCpy $R3 1
      ${Break}
    ${EndIf}
    IntOp $R4 $R4 + 1
  ${Loop}
  Pop $R6
  Pop $R5
  Pop $R4
  StrCpy $R1 $R3
  Pop $R3
  Pop $R2
  Exch $R1
FunctionEnd

; Push path, push dir; pops 1 if path is dir or inside it (any case).
; Registers are kept.
Function IsInsideDir
  Exch $R1  ; dir
  Exch
  Exch $R2  ; path
  Push $R3  ; result
  Push $R4
  Push $R5
  StrCpy $R3 0
  ${If} $R1 != ""
    StrLen $R5 $R1
    StrCpy $R4 $R2 $R5
    ${If} $R4 == $R1
      StrCpy $R4 $R2 1 $R5
      ${If} $R4 == ""
      ${OrIf} $R4 == "\"
        StrCpy $R3 1
      ${EndIf}
    ${EndIf}
  ${EndIf}
  Pop $R5
  Pop $R4
  StrCpy $R1 $R3
  Pop $R3
  Pop $R2
  Exch $R1
FunctionEnd

!macro _HiveyRefuseInside DIR
  ${If} $R0 == ""
    Push $INSTDIR
    Push "${DIR}"
    Call IsInsideDir
    Pop $R1
    ${If} $R1 == 1
      StrCpy $R0 "system"
    ${EndIf}
  ${EndIf}
!macroend

; Checks $INSTDIR (the same rules as setup's --hivey-install-dir):
; $R0 = "" (fine), "invalid", "system" or "notempty".
Function CheckDir
  Push $R1
  ${Do}
    StrCpy $R1 $INSTDIR 1 -1
    ${If} $R1 != "\"
      ${Break}
    ${EndIf}
    StrCpy $INSTDIR $INSTDIR -1
  ${Loop}
  StrCpy $R0 ""
  StrCpy $R1 $INSTDIR 2
  ${If} $R1 == "\\"
    StrCpy $R0 "invalid"
  ${EndIf}
  StrCpy $R1 $INSTDIR 1 1
  ${If} $R1 != ":"
    StrCpy $R0 "invalid"
  ${EndIf}
  StrLen $R1 $INSTDIR
  ${If} $R1 < 4
    StrCpy $R0 "invalid"
  ${EndIf}
  !insertmacro _HiveyRefuseInside "$PROGRAMFILES64"
  !insertmacro _HiveyRefuseInside "$PROGRAMFILES32"
  !insertmacro _HiveyRefuseInside "$WINDIR"
  ${If} $R0 == ""
  ${AndIf} ${FileExists} "$INSTDIR\*.*"
  ${AndIfNot} ${FileExists} "$INSTDIR\chrome.exe"
    ${DirState} "$INSTDIR" $R1
    ${If} $R1 == 1  ; not empty
      StrCpy $R0 "notempty"
    ${EndIf}
  ${EndIf}
  Pop $R1
FunctionEnd

Function .onInit
  System::Call 'kernel32::CreateMutex(p 0, i 0, t "HiveyBrowserSetup") p .r1 ?e'
  Pop $0
  ${If} $0 == 183  ; ERROR_ALREADY_EXISTS
    MessageBox MB_ICONEXCLAMATION|MB_OK "$(AlreadyRunning)" /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  ; x64 Windows 10+, or Windows on Arm (x64 emulation).
  StrCpy $0 1
  ${IfNot} ${AtLeastWin10}
    StrCpy $0 0
  ${ElseIfNot} ${IsNativeAMD64}
  ${AndIfNot} ${IsNativeARM64}
    StrCpy $0 0
  ${EndIf}
  ${If} $0 == 0
    MessageBox MB_ICONSTOP|MB_OK "$(NeedWin10)" /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}

  ${GetParameters} $Params
  ; The updater and the CI give mini_installer --do-not-launch-chrome: the
  ; same switch makes this wizard silent.
  Push $Params
  Push "--do-not-launch-chrome"
  Call StrContains
  Pop $0
  ${If} $0 == 1
    SetSilent silent
  ${EndIf}
  Push $Params
  Push "--verbose-logging"
  Call StrContains
  Pop $Verbose

  ; Already installed: update in place, in its folder.
  StrCpy $IsUpdate 0
  ReadRegStr $0 HKCU "${UNINSTALL_KEY}" "InstallLocation"
  ${If} $0 != ""
  ${AndIf} ${FileExists} "$0\chrome.exe"
    StrCpy $INSTDIR $0
    StrCpy $IsUpdate 1
  ${Else}
    Call CheckDir  ; no trailing backslash on the directory page
  ${EndIf}

  ${If} ${Silent}
    ; Silent (scripts, CI): privacy mode only when asked, as before; the
    ; wizard checks it.
    !insertmacro UnselectSection ${SecPrivacy}
    ClearErrors
    ${GetOptions} $Params "/PRIVACY" $0
    ${IfNot} ${Errors}
      !insertmacro SelectSection ${SecPrivacy}
    ${EndIf}
    ClearErrors
    ${GetOptions} $Params "/NODESKTOP" $0
    ${IfNot} ${Errors}
      !insertmacro UnselectSection ${SecDesktop}
    ${EndIf}
    ClearErrors
    ${GetOptions} $Params "/NOTASKBAR" $0
    ${IfNot} ${Errors}
      !insertmacro UnselectSection ${SecTaskbar}
    ${EndIf}
    !insertmacro HIVEY_ADDON_SILENT_OPTIONS
    ${If} $IsUpdate != 1
      Call CheckDir
      ${If} $R0 == "notempty"
        StrCpy $INSTDIR "$INSTDIR\${PRODUCT_NAME}"
        Call CheckDir
      ${EndIf}
      ${If} $R0 != ""
        StrCpy $INSTDIR "${DEFAULT_DIR}"
      ${EndIf}
    ${EndIf}
  ${EndIf}
FunctionEnd

Function SkipIfUpdate
  ${If} $IsUpdate == 1
    Abort
  ${EndIf}
FunctionEnd

Function ComponentsLeave
  ${IfNot} ${FileExists} "${USER_DATA_DIR}\Local State"
    Return
  ${EndIf}
  StrCpy $R9 ""
  !insertmacro HIVEY_ADDON_UNSELECTED_IDS
  ${If} $R9 != ""
  ${OrIf} ${SectionIsSelected} ${SecPrivacy}
    MessageBox MB_ICONINFORMATION|MB_OK "$(ProfileExists)"
  ${EndIf}
FunctionEnd

Function DirectoryLeave
  Call CheckDir
  ${If} $R0 == "notempty"
    StrCpy $INSTDIR "$INSTDIR\${PRODUCT_NAME}"
    Call CheckDir
    ${If} $R0 == ""
      MessageBox MB_ICONINFORMATION|MB_OK "$(DirSubfolder)"
      FindWindow $R1 "#32770" "" $HWNDPARENT
      GetDlgItem $R1 $R1 1019
      SendMessage $R1 ${WM_SETTEXT} 0 "STR:$INSTDIR"
      Abort
    ${EndIf}
  ${EndIf}
  ${If} $R0 == "system"
    MessageBox MB_ICONEXCLAMATION|MB_OK "$(DirSystem)"
    Abort
  ${ElseIf} $R0 != ""
    MessageBox MB_ICONEXCLAMATION|MB_OK "$(DirInvalid)"
    Abort
  ${EndIf}
FunctionEnd

; Initial preferences: read by setup (shortcuts), copied next to chrome.exe
; on a first install, and turned into the profile's prefs on the browser's
; first run (chrome/browser/first_run). An add-on left out is recorded as
; removed by the user (extensions.external_uninstalls): the bundled loader
; then never installs it, exactly as after a removal in chrome://extensions.
Function WritePrefs
  StrCpy $PrefsFile "$PLUGINSDIR\initial_preferences.json"
  StrCpy $R9 ""
  !insertmacro HIVEY_ADDON_UNSELECTED_IDS
  ${If} $R9 != ""
    StrCpy $R9 $R9 -1  ; trailing comma
  ${EndIf}
  StrCpy $R8 ""
  !insertmacro HIVEY_ADDON_SELECTED_OPTIONAL
  ${If} $R8 != ""
    StrCpy $R8 $R8 -1  ; trailing comma
  ${EndIf}
  StrCpy $R1 "true"
  ${If} ${SectionIsSelected} ${SecDesktop}
    StrCpy $R1 "false"
  ${EndIf}
  StrCpy $R2 "true"
  ${If} ${SectionIsSelected} ${SecTaskbar}
    StrCpy $R2 "false"
  ${EndIf}
  FileOpen $0 $PrefsFile w
  FileWrite $0 '{$\r$\n'
  FileWrite $0 '  "distribution": {$\r$\n'
  FileWrite $0 '    "do_not_create_desktop_shortcut": $R1,$\r$\n'
  FileWrite $0 '    "do_not_create_quick_launch_shortcut": true,$\r$\n'
  FileWrite $0 '    "do_not_create_taskbar_shortcut": $R2$\r$\n'
  FileWrite $0 '  },$\r$\n'
  FileWrite $0 '  "extensions": { "external_uninstalls": [$R9] },$\r$\n'
  FileWrite $0 '  "hivey": { "optional_addons": [$R8] }'
  ${If} ${SectionIsSelected} ${SecPrivacy}
    FileWrite $0 ',$\r$\n'
    FileWrite $0 '  "profile": {$\r$\n'
    FileWrite $0 '    "cookie_controls_mode": 1,$\r$\n'
    FileWrite $0 '    "default_content_setting_values": { "javascript_optimizer": 2 }$\r$\n'
    FileWrite $0 '  },$\r$\n'
    FileWrite $0 '  "webrtc": { "ip_handling_policy": "disable_non_proxied_udp" },$\r$\n'
    FileWrite $0 '  "search": { "suggest_enabled": false },$\r$\n'
    FileWrite $0 '  "net": { "network_prediction_options": 2 },$\r$\n'
    FileWrite $0 '  "enable_do_not_track": true'
  ${EndIf}
  FileWrite $0 '$\r$\n}$\r$\n'
  FileClose $0
FunctionEnd

; mini_installer shows no progress: a moving bar meanwhile.
Function StartMarquee
  FindWindow $R1 "#32770" "" $HWNDPARENT
  GetDlgItem $R1 $R1 1004
  System::Call 'user32::GetWindowLong(p R1, i -16) i .R2'
  IntOp $R2 $R2 | 0x08  ; PBS_MARQUEE
  System::Call 'user32::SetWindowLong(p R1, i -16, i R2)'
  SendMessage $R1 0x040A 1 30  ; PBM_SETMARQUEE
FunctionEnd

Function LaunchBrowser
  Exec '"$INSTDIR\chrome.exe"'
FunctionEnd

Function .onInstSuccess
  ${If} ${Silent}
    ClearErrors
    ${GetOptions} $Params "/LAUNCH" $0
    ${IfNot} ${Errors}
      Call LaunchBrowser
    ${EndIf}
  ${EndIf}
FunctionEnd
