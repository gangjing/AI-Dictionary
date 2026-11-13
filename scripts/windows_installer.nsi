Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
Name "AI Dictionary 1.0.5"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\AI Dictionary"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Icon "${PAYLOAD}\app\icon.ico"
UninstallIcon "${PAYLOAD}\app\icon.ico"
VIProductVersion "1.0.5.0"
VIAddVersionKey "ProductName" "AI Dictionary"
VIAddVersionKey "FileDescription" "AI Dictionary Setup"
VIAddVersionKey "FileVersion" "1.0.5"
VIAddVersionKey "LegalCopyright" "AI Dictionary"
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

!macro CheckRunning
  System::Call 'kernel32::OpenMutexW(i 0x100000, i 0, w "Local\AIDictionaryDesktop") p.r0'
  ${If} $0 != 0
    System::Call 'kernel32::CloseHandle(p r0)'
    MessageBox MB_OK|MB_ICONEXCLAMATION "请先从系统托盘完全退出 AI Dictionary，再继续安装或卸载。" /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
!macroend

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_OK "此安装包需要 64 位 Windows。" /SD IDOK
    Abort
  ${EndIf}
  SetShellVarContext current
  !insertmacro CheckRunning
FunctionEnd

Function un.onInit
  SetShellVarContext current
  !insertmacro CheckRunning
FunctionEnd

Section "Install"
  ; Install WebView2 only when its runtime is absent. This step requires internet.
  SetRegView 32
  ReadRegStr $0 HKLM "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${If} $0 == ""
  ${OrIf} $0 == "0.0.0.0"
    ReadRegStr $0 HKCU "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${EndIf}
  ${If} $0 == ""
  ${OrIf} $0 == "0.0.0.0"
    InitPluginsDir
    SetOutPath "$PLUGINSDIR"
    File "${BOOTSTRAPPER}"
    ExecWait '"$PLUGINSDIR\MicrosoftEdgeWebview2Setup.exe" /silent /install' $1
    ${If} $1 != 0
      MessageBox MB_OK|MB_ICONSTOP "WebView2 安装失败。请连接网络后重试。错误码：$1" /SD IDOK
      SetErrorLevel 3
      Abort
    ${EndIf}
  ${EndIf}
  SetRegView 64
  SetOutPath "$INSTDIR"
  File "${PAYLOAD}\AI Dictionary.exe"
  SetOutPath "$INSTDIR\app"
  File /r "${PAYLOAD}\app\*"
  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateShortcut "$SMPROGRAMS\AI Dictionary.lnk" "$INSTDIR\AI Dictionary.exe" "" "$INSTDIR\app\icon.ico"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIDictionary" "DisplayName" "AI Dictionary"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIDictionary" "DisplayVersion" "1.0.5"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIDictionary" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIDictionary" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIDictionary" "DisplayIcon" "$INSTDIR\AI Dictionary.exe"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIDictionary" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIDictionary" "NoRepair" 1
SectionEnd

Section "Uninstall"
  SetRegView 64
  ; Delete only files in the build manifest. Never recursively delete user directories.
  !include "${UNINSTALL_MANIFEST}"
  Delete "$INSTDIR\AI Dictionary.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\AI Dictionary.lnk"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\AIDictionary"
  ; User data in $LOCALAPPDATA\AIDictionary is deliberately retained.
SectionEnd
