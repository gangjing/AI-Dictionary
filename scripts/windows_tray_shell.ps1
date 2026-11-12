# AI Dictionary v1.0 — Windows Native System Tray & Close-to-Tray Shell (`scripts/windows_tray_shell.ps1`)
# Implements Youdao Dictionary style Windows Notification Area (System Tray) resident app:
# - Closing the main window (X) hides to the Windows System Tray instead of quitting.
# - Left-click tray icon: Toggles the Youdao-style Mini Lookup Popover window near the taskbar clock.
# - Double-click tray icon: Restores the Main AI Dictionary window.
# - Right-click tray icon: Opens the full Youdao-style ContextMenuStrip (Screen Selection, Clipboard Capture, OCR, Privacy Mode, Settings, Explicit Exit).

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppRoot   = Split-Path -Parent $ScriptDir
$IconPath  = Join-Path $AppRoot "icon.ico"
if (-not (Test-Path $IconPath)) {
    $IconPath = Join-Path $AppRoot "src-tauri\icons\icon.ico"
}

$Port = 14205
$MainUrl = "http://127.0.0.1:$Port/"
$TrayUrl = "http://127.0.0.1:$Port/?mode=tray"

# Keep mutable databases outside the installation directory across upgrades.
$UserDir = Join-Path $env:LOCALAPPDATA "AIDictionary"
New-Item -ItemType Directory -Force -Path $UserDir | Out-Null
foreach ($Db in @("dictionary.db", "user_data.db")) {
    if (-not (Test-Path (Join-Path $UserDir $Db))) {
        Copy-Item -LiteralPath (Join-Path $AppRoot "data\$Db") -Destination (Join-Path $UserDir $Db)
    }
}
$env:AIDICT_DATA_DIR = $UserDir
$env:AIDICT_USER_DATA_DIR = $UserDir
$env:AIDICT_APP_ROOT = $AppRoot
$env:PORT = "$Port"
$BackendExe = Join-Path $AppRoot "backend\AIDictionaryServer.exe"
$ServerProc = Start-Process -FilePath $BackendExe -ArgumentList "--port $Port" -WindowStyle Hidden -PassThru
$Ready = $false
for ($Attempt = 0; $Attempt -lt 100; $Attempt++) {
    if ($ServerProc.HasExited) { throw "AI Dictionary backend exited before startup. Check port $Port." }
    try {
        Invoke-RestMethod -Uri "${MainUrl}api/dict/stats" -TimeoutSec 1 | Out-Null
        $Ready = $true
        break
    } catch { Start-Sleep -Milliseconds 100 }
}
if (-not $Ready) { Stop-Process -Id $ServerProc.Id; throw "Backend startup timed out." }
$WebViewDir = Join-Path $AppRoot "webview2"
Add-Type -Path (Join-Path $WebViewDir "Microsoft.Web.WebView2.Core.dll")
Add-Type -Path (Join-Path $WebViewDir "Microsoft.Web.WebView2.WinForms.dll")
$env:PATH = "$WebViewDir;$env:PATH"
function New-AppBrowser($Url) {
    $Browser = New-Object Microsoft.Web.WebView2.WinForms.WebView2
    $Browser.Dock = "Fill"
    $Browser.CreationProperties = New-Object Microsoft.Web.WebView2.WinForms.CoreWebView2CreationProperties
    $Browser.CreationProperties.UserDataFolder = Join-Path $UserDir "WebView2"
    $Browser.Add_WebMessageReceived({
        param($sender, $eventArgs)
        $Message = $eventArgs.WebMessageAsJson | ConvertFrom-Json
        switch ($Message.action) {
            'hideToTray' { $MainForm.Hide() }
            'showMainWindow' {
                Show-MainWindow
                if ($Message.tab -in @('dictionary','translate','ocr','wordbook','history','models','settings')) {
                    $null = $MainBrowser.ExecuteScriptAsync("window.switchTab('$($Message.tab)')")
                }
            }
            'closeMiniPopover' { $MiniForm.Hide() }
            'setCloseToTray' { $script:CloseToTray = [bool]$Message.enabled }
            'quitApp' { $ItemExit.PerformClick() }
            'syncState' {
                $script:SelectionOn = [bool]$Message.screen_selection_enabled
                $script:ClipboardOn = [bool]$Message.clipboard_capture_enabled
                $ItemSelection.Checked = $script:SelectionOn
                $ItemClipboard.Checked = $script:ClipboardOn
            }
        }
    })
    $Browser.Source = [Uri]$Url
    return $Browser
}

$script:IsExplicitQuit = $false
$script:CloseToTray    = $true
$script:SelectionOn    = $true
$script:ClipboardOn    = $false
$script:PrivacyOn      = $false

# Load custom application icon
$AppIcon = [System.Drawing.SystemIcons]::Application
if (Test-Path $IconPath) {
    try { $AppIcon = New-Object System.Drawing.Icon($IconPath) } catch {}
}

# 1. Create Main Window with Close-to-Tray Interception
$MainForm = New-Object System.Windows.Forms.Form
$MainForm.Text = "AI Dictionary — 本地离线词典与翻译 (关闭窗口将最小化至右下角系统托盘)"
$MainForm.Size = New-Object System.Drawing.Size(1120, 750)
$MainForm.MinimumSize = New-Object System.Drawing.Size(860, 560)
$MainForm.StartPosition = "CenterScreen"
$MainForm.Icon = $AppIcon

$MainBrowser = New-AppBrowser $MainUrl
$MainForm.Controls.Add($MainBrowser)

# 2. Create Youdao-style Tray Mini Lookup Popover Window (anchored near taskbar notification area)
$MiniForm = New-Object System.Windows.Forms.Form
$MiniForm.Text = "AI 词典 — 迷你查词栏"
$MiniForm.Size = New-Object System.Drawing.Size(395, 510)
$MiniForm.FormBorderStyle = "FixedToolWindow"
$MiniForm.TopMost = $true
$MiniForm.ShowInTaskbar = $false
$MiniForm.StartPosition = "Manual"
$MiniForm.Icon = $AppIcon

$WorkArea = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$MiniForm.Location = New-Object System.Drawing.Point(($WorkArea.Right - 410), ($WorkArea.Bottom - 525))

$MiniBrowser = New-AppBrowser $TrayUrl
$MiniForm.Controls.Add($MiniBrowser)

$MiniForm.Add_FormClosing({
    param($sender, $e)
    if (-not $script:IsExplicitQuit) {
        $e.Cancel = $true
        $MiniForm.Hide()
    }
})

# 3. Create Windows Notification Area (System Tray) Icon & Youdao-style Context Menu
$NotifyIcon = New-Object System.Windows.Forms.NotifyIcon
$NotifyIcon.Icon = $AppIcon
$NotifyIcon.Text = "AI 词典 (常驻托盘)`n左键：迷你查词小窗 | 双击：主窗口 | 右键：快捷菜单"
$NotifyIcon.Visible = $true

$TrayMenu = New-Object System.Windows.Forms.ContextMenuStrip

$ItemMini = $TrayMenu.Items.Add("🔍 打开迷你查词小窗 (Mini 查词栏)")
$ItemMain = $TrayMenu.Items.Add("📖 显示 AI 词典主窗口")
$TrayMenu.Items.Add("-") | Out-Null

$ItemSelection = New-Object System.Windows.Forms.ToolStripMenuItem("屏幕划词翻译 (Screen Capture)")
$ItemSelection.Checked = $script:SelectionOn
$TrayMenu.Items.Add($ItemSelection) | Out-Null

$ItemClipboard = New-Object System.Windows.Forms.ToolStripMenuItem("剪贴板自动查词 (Clipboard Monitor)")
$ItemClipboard.Checked = $script:ClipboardOn
$TrayMenu.Items.Add($ItemClipboard) | Out-Null

$ItemOcr = $TrayMenu.Items.Add("📸 区域截图 OCR 翻译")

$ItemPrivacy = New-Object System.Windows.Forms.ToolStripMenuItem("🛡️ 私密无痕查词模式")
$ItemPrivacy.Checked = $script:PrivacyOn
$TrayMenu.Items.Add($ItemPrivacy) | Out-Null

$TrayMenu.Items.Add("-") | Out-Null
$ItemSettings = $TrayMenu.Items.Add("⚙️ 偏好设置与词库管理...")
$TrayMenu.Items.Add("-") | Out-Null
$ItemExit = $TrayMenu.Items.Add("🚪 完全退出 AI 词典 (Exit)")

$NotifyIcon.ContextMenuStrip = $TrayMenu

function Show-MainWindow {
    if ($MiniForm.Visible) { $MiniForm.Hide() }
    if (-not $MainForm.Visible) { $MainForm.Show() }
    $MainForm.WindowState = "Normal"
    $MainForm.Activate()
    $null = $MainBrowser.ExecuteScriptAsync("window.onRestoreFromTray && window.onRestoreFromTray()")
}

function Toggle-MiniWindow {
    if ($MiniForm.Visible) {
        $MiniForm.Hide()
    } else {
        $WorkArea = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
        $MiniForm.Location = New-Object System.Drawing.Point(($WorkArea.Right - 410), ($WorkArea.Bottom - 525))
        $MiniForm.Show()
        $MiniForm.Activate()
    }
}

$ItemMini.Add_Click({ Toggle-MiniWindow })
$ItemMain.Add_Click({ Show-MainWindow })

$ItemSelection.Add_Click({
    $script:SelectionOn = -not $script:SelectionOn
    $ItemSelection.Checked = $script:SelectionOn
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/settings" -Method Post -ContentType "application/json" -Body (@{screen_selection_enabled=$script:SelectionOn} | ConvertTo-Json) | Out-Null
    } catch {}
})

$ItemClipboard.Add_Click({
    $script:ClipboardOn = -not $script:ClipboardOn
    $ItemClipboard.Checked = $script:ClipboardOn
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/settings" -Method Post -ContentType "application/json" -Body (@{clipboard_capture_enabled=$script:ClipboardOn} | ConvertTo-Json) | Out-Null
    } catch {}
})

$ItemOcr.Add_Click({
    Show-MainWindow
    try { $MainBrowser.ExecuteScriptAsync("window.switchTab('ocr')") | Out-Null } catch {}
})

$ItemPrivacy.Add_Click({
    $script:PrivacyOn = -not $script:PrivacyOn
    $ItemPrivacy.Checked = $script:PrivacyOn
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/privacy" -Method Post -ContentType "application/json" -Body (@{enabled=$script:PrivacyOn} | ConvertTo-Json) | Out-Null
    } catch {}
})

$ItemSettings.Add_Click({
    Show-MainWindow
    try { $MainBrowser.ExecuteScriptAsync("window.switchTab('settings')") | Out-Null } catch {}
})

$ItemExit.Add_Click({
    $script:IsExplicitQuit = $true
    $NotifyIcon.Visible = $false
    $NotifyIcon.Dispose()
    if ($ServerProc -and -not $ServerProc.HasExited) {
        Stop-Process -Id $ServerProc.Id -Force -ErrorAction SilentlyContinue
    }
    [System.Windows.Forms.Application]::Exit()
})

# Left-click toggles Youdao Mini Lookup Window; Double-click restores Main Window
$NotifyIcon.Add_MouseClick({
    param($sender, $e)
    if ($e.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
        Toggle-MiniWindow
    }
})

$NotifyIcon.Add_MouseDoubleClick({
    param($sender, $e)
    Show-MainWindow
})

# Intercept Main Window Close Button (X): Hide to System Tray instead of exiting!
$MainForm.Add_FormClosing({
    param($sender, $e)
    if (-not $script:IsExplicitQuit -and $script:CloseToTray) {
        $e.Cancel = $true
        $MainForm.Hide()
        $NotifyIcon.ShowBalloonTip(
            2500,
            "AI 词典仍在后台运行",
            "已最小化到系统托盘（信息栏）。左键点击图标可快速查词，双击恢复主窗口，右键菜单可完全退出。",
            [System.Windows.Forms.ToolTipIcon]::Info
        )
    } else {
        $NotifyIcon.Visible = $false
        if ($ServerProc -and -not $ServerProc.HasExited) {
            Stop-Process -Id $ServerProc.Id -Force -ErrorAction SilentlyContinue
        }
    }
})

try { [System.Windows.Forms.Application]::Run($MainForm) }
finally {
    $NotifyIcon.Dispose()
    $MiniForm.Dispose()
    $MainForm.Dispose()
    if ($ServerProc -and -not $ServerProc.HasExited) { Stop-Process -Id $ServerProc.Id -ErrorAction SilentlyContinue }
}
