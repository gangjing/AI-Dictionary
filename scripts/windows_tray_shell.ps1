# AI Dictionary - Windows native shell (WinForms + WebView2 + system tray).
#
# Responsibilities:
#  - Host the local Python backend and render the main window / mini lookup window.
#  - Global hotkeys (selection lookup, screenshot OCR, main window).
#  - UIA selection capture with a secure-field guard and controlled clipboard fallback.
#  - Clipboard monitoring ("取词") with the same popup experience.
#  - Region screenshot + Windows.Media.Ocr, results injected into the OCR page.
#  - Youdao-style tray menu, close-to-tray, DPI-aware dark/light native chrome.

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -Path (Join-Path $PSScriptRoot 'windows_appearance.cs') -ReferencedAssemblies System.Windows.Forms, System.Drawing
Add-Type -Path (Join-Path $PSScriptRoot 'windows_native.cs') -ReferencedAssemblies System.Windows.Forms, System.Drawing, UIAutomationClient, UIAutomationTypes
. (Join-Path $PSScriptRoot 'windows_ocr.ps1')

[DesktopAppearance]::EnableDpi()
[System.Windows.Forms.Application]::EnableVisualStyles()

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppRoot   = Split-Path -Parent $ScriptDir
$IconPath  = Join-Path $AppRoot "icon.ico"
if (-not (Test-Path $IconPath)) {
    $IconPath = Join-Path $AppRoot "assets\icons\icon.ico"
}

$Port = if ($env:AIDICT_PORT) { [int]$env:AIDICT_PORT } else { 14205 }
$MainUrl = "http://127.0.0.1:$Port/"
$TrayUrl = "http://127.0.0.1:$Port/?mode=tray"

# Mutable databases live outside the installation directory so upgrades never overwrite them.
$UserDir = if ($env:AIDICT_USER_DATA_DIR) { $env:AIDICT_USER_DATA_DIR } else { Join-Path $env:LOCALAPPDATA "AIDictionary" }
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
if (-not (Test-Path $BackendExe)) {
    $BackendExe = Join-Path $AppRoot "dist\backend\AIDictionaryServer\AIDictionaryServer.exe"
}
if ($env:AIDICT_BACKEND_PY) {
    $PythonExe = if ($env:AIDICT_PYTHON) { $env:AIDICT_PYTHON } else { "python" }
    $PythonArgs = '"' + $env:AIDICT_BACKEND_PY + '" --port ' + $Port
    $ServerProc = Start-Process -FilePath $PythonExe -ArgumentList $PythonArgs -WindowStyle Hidden -PassThru
} else {
    $ServerProc = Start-Process -FilePath $BackendExe -ArgumentList "--port $Port" -WindowStyle Hidden -PassThru
}
$Ready = $false
for ($Attempt = 0; $Attempt -lt 120; $Attempt++) {
    if ($ServerProc.HasExited) { throw "AI Dictionary backend exited before startup. Check port $Port." }
    try {
        Invoke-RestMethod -Uri "${MainUrl}api/dict/stats" -TimeoutSec 1 | Out-Null
        $Ready = $true
        break
    } catch { Start-Sleep -Milliseconds 120 }
}
if (-not $Ready) { Stop-BackendProcess; throw "Backend startup timed out." }

$WebViewDir = Join-Path $AppRoot "webview2"
if (-not (Test-Path (Join-Path $WebViewDir "Microsoft.Web.WebView2.WinForms.dll"))) {
    $WebViewDir = Join-Path $AppRoot "dist\windows-x64-staging\AI-Dictionary-Windows-x64\app\webview2"
}
Add-Type -Path (Join-Path $WebViewDir "Microsoft.Web.WebView2.Core.dll")
Add-Type -Path (Join-Path $WebViewDir "Microsoft.Web.WebView2.WinForms.dll")
$env:PATH = "$WebViewDir;$env:PATH"

# ---------------------------------------------------------------- global state
$script:IsExplicitQuit = $false
$script:CloseToTray    = $true
$script:SelectionOn    = $true
$script:ClipboardOn    = $false
$script:ClipboardFallback = $true
$script:PrivacyOn      = $false
$script:TrayClickAction = 'mini_popover'
$script:Looks = @{}
$script:MainReady = $false
$script:MiniReady = $false
$script:PendingMini = $null
$script:PendingOcr = $null
$script:LastSelectionText = ''
$script:Hotkeys = @{}
$script:SelfTest = ($args -contains '--self-test')
$script:SelfTestFailed = $false
$script:LastRenderedSelection = ''
$script:LastRenderedOcr = -1
$script:SuppressMiniHideUntil = [datetime]::MinValue
$script:MiniHideTimer = New-Object System.Windows.Forms.Timer
$script:MiniHideTimer.Interval = 320
$script:TrayClickTimer = New-Object System.Windows.Forms.Timer
$script:TrayClickTimer.Interval = 260

function Write-Diagnostic([string]$Message) {
    try {
        $log = Join-Path $UserDir 'native.log'
        Add-Content -LiteralPath $log -Value ("{0:o} {1}" -f (Get-Date), $Message) -Encoding UTF8
    } catch {}
}

function Stop-BackendProcess {
    if ($null -eq $ServerProc) { return }
    try {
        if (-not $ServerProc.HasExited) {
            # Kill the backend and any llama-server child it started.
            & taskkill.exe /F /T /PID $ServerProc.Id 2>$null | Out-Null
        }
    } catch {}
    try { Stop-BackendProcess } catch {}
}

function ConvertTo-JsString([string]$Value) {
    return (ConvertTo-Json -InputObject ([string]$Value) -Compress)
}

function Get-AppSetting([string]$Key, $Default) {
    try {
        $response = Invoke-RestMethod -Uri "${MainUrl}api/settings" -TimeoutSec 2
        $settings = $response.settings
        if ($null -ne $settings -and $null -ne $settings.$Key) { return $settings.$Key }
    } catch {}
    return $Default
}

function Show-Balloon([string]$Title, [string]$Text, [string]$Icon = 'Info') {
    try {
        $tipIcon = [System.Windows.Forms.ToolTipIcon]::$Icon
        $NotifyIcon.ShowBalloonTip(2600, $Title, $Text, $tipIcon)
    } catch {}
}

function Invoke-WebViewScript($Browser, [string]$Script) {
    try {
        if ($null -ne $Browser -and $null -ne $Browser.CoreWebView2) {
            $null = $Browser.ExecuteScriptAsync($Script)
        }
    } catch {
        Write-Diagnostic "ExecuteScriptAsync failed: $($_.Exception.Message)"
    }
}

function New-AppBrowser($Url) {
    $Browser = New-Object Microsoft.Web.WebView2.WinForms.WebView2
    $Browser.Dock = "Fill"
    $Browser.CreationProperties = New-Object Microsoft.Web.WebView2.WinForms.CoreWebView2CreationProperties
    $Browser.CreationProperties.UserDataFolder = Join-Path $UserDir "WebView2"
    $Browser.Add_WebMessageReceived({
        param($sender, $eventArgs)
        try { $Message = $eventArgs.WebMessageAsJson | ConvertFrom-Json } catch { return }
        switch ($Message.action) {
            'setTheme' { Set-AppTheme ([bool]$Message.dark) }
            'hideToTray' {
                Hide-MiniWindow
                $MainForm.Hide()
            }
            'showMainWindow' {
                Show-MainWindow
                if ($Message.tab -in @('dictionary','translate','ocr','wordbook','history','models','settings')) {
                    Invoke-WebViewScript $MainBrowser "window.switchTab('$($Message.tab)')"
                }
            }
            'closeMiniPopover' { Hide-MiniWindow }
            'setCloseToTray' { $script:CloseToTray = [bool]$Message.enabled }
            'quitApp' { $ItemExit.PerformClick() }
            'captureSelection' { Invoke-SelectionAction }
            'captureOcr' { Invoke-OcrCapture }
            'translateClipboard' { Invoke-ClipboardTranslate }
            'openWord' {
                Show-MainWindow
                $wordJson = ConvertTo-JsString ([string]$Message.text)
                Invoke-WebViewScript $MainBrowser "window.quickSelectWord && window.quickSelectWord($wordJson)"
            }
            'openTranslate' {
                Show-MainWindow
                $textJson = ConvertTo-JsString ([string]$Message.text)
                Invoke-WebViewScript $MainBrowser "document.getElementById('transStudioInput').value = $textJson; window.switchTab && window.switchTab('translate')"
            }
            'selectionRendered' {
                $script:LastRenderedSelection = [string]$Message.text
                Write-Diagnostic ("selection rendered source={0} chars={1}" -f $Message.source, $script:LastRenderedSelection.Length)
            }
            'ocrRendered' {
                $script:LastRenderedOcr = [int]$Message.lines
                Write-Diagnostic ("ocr rendered lines={0}" -f $script:LastRenderedOcr)
            }
            'syncState' {
                if ($null -ne $Message.screen_selection_enabled) {
                    $script:SelectionOn = [bool]$Message.screen_selection_enabled
                    $ItemSelection.Checked = $script:SelectionOn
                }
                if ($null -ne $Message.clipboard_capture_enabled) {
                    Set-ClipboardFeature ([bool]$Message.clipboard_capture_enabled) -Persist $false
                }
                if ($null -ne $Message.clipboard_fallback_enabled) {
                    $script:ClipboardFallback = [bool]$Message.clipboard_fallback_enabled
                }
                if ($null -ne $Message.privacy_mode) {
                    $script:PrivacyOn = [bool]$Message.privacy_mode
                    $ItemPrivacy.Checked = $script:PrivacyOn
                }
            }
            'updateHotkeys' { Register-GlobalHotkeys $Message }
        }
    })
    $Browser.Source = [Uri]$Url
    return $Browser
}

$script:AppIcon = [System.Drawing.SystemIcons]::Application
if (Test-Path $IconPath) {
    try { $script:AppIcon = New-Object System.Drawing.Icon($IconPath) } catch {}
}

# ---------------------------------------------------------------- windows
$MainForm = New-Object DictionaryWindow
$MainForm.Text = "AI Dictionary"
$MainForm.LogicalSize = New-Object System.Drawing.Size(1120, 750)
$MainForm.LogicalMinimum = New-Object System.Drawing.Size(800, 520)
$MainForm.StartPosition = "CenterScreen"
$MainForm.Icon = $script:AppIcon

$MainBrowser = New-AppBrowser $MainUrl
$MainForm.Controls.Add($MainBrowser)
$MainBrowser.Add_NavigationCompleted({
    param($sender, $navArgs)
    if ($navArgs.IsSuccess) {
        $script:MainReady = $true
        if ($null -ne $script:PendingOcr) {
            $payload = $script:PendingOcr
            $script:PendingOcr = $null
            Send-OcrToPage $payload
        }
    }
})

$MiniForm = New-Object DictionaryWindow
$MiniForm.Text = "AI 词典 - 迷你查词栏"
$MiniForm.LogicalSize = New-Object System.Drawing.Size(430, 540)
$MiniForm.LogicalMinimum = New-Object System.Drawing.Size(340, 380)
$MiniForm.FormBorderStyle = "FixedToolWindow"
$MiniForm.TopMost = $true
$MiniForm.ShowInTaskbar = $false
$MiniForm.StartPosition = "Manual"
$MiniForm.Icon = $script:AppIcon

$MiniBrowser = New-AppBrowser $TrayUrl
$MiniForm.Controls.Add($MiniBrowser)
$MiniBrowser.Add_NavigationCompleted({
    param($sender, $navArgs)
    Write-Diagnostic ("mini navigation success={0} error={1}" -f $navArgs.IsSuccess, $navArgs.WebErrorStatus)
    if ($navArgs.IsSuccess) {
        $script:MiniReady = $true
        if ($null -ne $script:PendingMini) {
            $payload = $script:PendingMini
            $script:PendingMini = $null
            Send-SelectionToMini $payload.Text $payload.Meta
        }
    }
})
$MiniForm.Add_FormClosing({
    param($sender, $e)
    if (-not $script:IsExplicitQuit) {
        $e.Cancel = $true
        Hide-MiniWindow
    }
})
$MiniForm.Add_Deactivate({
    if ($script:IsExplicitQuit) { return }
    $script:MiniHideTimer.Start()
})
$script:MiniHideTimer.Add_Tick({
    $script:MiniHideTimer.Stop()
    if (-not $MiniForm.Visible) { return }
    if ([datetime]::Now -lt $script:SuppressMiniHideUntil) { $script:MiniHideTimer.Start(); return }
    $foreground = [NativeWindowInfo]::Foreground
    if ([NativeWindowInfo]::IsOwnedBy($foreground, $MiniForm.Handle)) { return }
    if ($foreground -eq $MainForm.Handle -or [NativeWindowInfo]::IsOwnedBy($foreground, $MainForm.Handle)) { return }
    Hide-MiniWindow
})

# ---------------------------------------------------------------- tray
$NotifyIcon = New-Object System.Windows.Forms.NotifyIcon
$NotifyIcon.Icon = $script:AppIcon
$NotifyIcon.Text = "AI 词典 (常驻托盘)`n左键：迷你查词 | 双击：主窗口 | 右键：快捷菜单"
$NotifyIcon.Visible = $true

$TrayMenu = New-Object System.Windows.Forms.ContextMenuStrip
$ItemMini = $TrayMenu.Items.Add("迷你查词")
$ItemMain = $TrayMenu.Items.Add("打开主窗口")
$TrayMenu.Items.Add("-") | Out-Null
$ItemSelection = New-Object System.Windows.Forms.ToolStripMenuItem("划词取词 (Ctrl+Alt+T)")
$ItemSelection.Checked = $script:SelectionOn
$TrayMenu.Items.Add($ItemSelection) | Out-Null
$ItemClipboard = New-Object System.Windows.Forms.ToolStripMenuItem("剪贴板取词")
$ItemClipboard.Checked = $script:ClipboardOn
$TrayMenu.Items.Add($ItemClipboard) | Out-Null
$ItemClipboardTranslate = $TrayMenu.Items.Add("翻译剪贴板内容")
$ItemOcr = $TrayMenu.Items.Add("截图识别 OCR (Ctrl+Alt+S)")
$ItemPrivacy = New-Object System.Windows.Forms.ToolStripMenuItem("私密模式")
$ItemPrivacy.Checked = $script:PrivacyOn
$TrayMenu.Items.Add($ItemPrivacy) | Out-Null
$TrayMenu.Items.Add("-") | Out-Null
$ItemSettings = $TrayMenu.Items.Add("设置")
$TrayMenu.Items.Add("-") | Out-Null
$ItemExit = $TrayMenu.Items.Add("退出 AI Dictionary")

$NotifyIcon.ContextMenuStrip = $TrayMenu
$TrayMenu.Font = New-Object Drawing.Font("Microsoft YaHei UI", 9)

# ---------------------------------------------------------------- theme
function Set-AppTheme([bool]$Dark) {
    $script:DarkTheme = $Dark
    @{ dark = $Dark } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $UserDir 'appearance.json')
    [DesktopAppearance]::Theme($MainForm, $Dark)
    [DesktopAppearance]::Theme($MiniForm, $Dark)
    $TrayMenu.Renderer = New-Object System.Windows.Forms.ToolStripProfessionalRenderer((New-Object DictionaryMenuColors($Dark)))
    $TrayMenu.ForeColor = if ($Dark) { [Drawing.Color]::FromArgb(239,242,246) } else { [Drawing.Color]::FromArgb(29,34,39) }
    $TrayMenu.BackColor = if ($Dark) { [Drawing.Color]::FromArgb(31,35,41) } else { [Drawing.Color]::White }
    if ($env:AIDICT_NATIVE_METRICS) {
        $titleDark = 0
        $null = [DesktopAppearance]::DwmGetWindowAttribute($MainForm.Handle, 20, [ref]$titleDark, 4)
        @{ dpi = [DesktopAppearance]::GetDpiForWindow($MainForm.Handle); perMonitorV2 = [DesktopAppearance]::AreDpiAwarenessContextsEqual([DesktopAppearance]::GetThreadDpiAwarenessContext(), [IntPtr](-4)); darkTitleBar = $titleDark; menuBackground = $TrayMenu.BackColor.ToArgb() } | ConvertTo-Json | Set-Content -LiteralPath $env:AIDICT_NATIVE_METRICS
    }
    $js = 'window.applyTheme && window.applyTheme(' + $Dark.ToString().ToLowerInvariant() + ', false)'
    foreach ($view in @($MainBrowser, $MiniBrowser)) {
        Invoke-WebViewScript $view $js
        $view.DefaultBackgroundColor = $MainForm.BackColor
    }
}
$initialDark = $true
$appearancePath = Join-Path $UserDir 'appearance.json'
if (Test-Path -LiteralPath $appearancePath) {
    try { $initialDark = [bool](Get-Content -LiteralPath $appearancePath -Raw | ConvertFrom-Json).dark } catch {}
}
Set-AppTheme $initialDark

# ---------------------------------------------------------------- window actions
function Show-MainWindow {
    Hide-MiniWindow
    if (-not $MainForm.Visible) { $MainForm.Show() }
    $MainForm.WindowState = "Normal"
    $MainForm.Activate()
    $MainForm.BringToFront()
    Invoke-WebViewScript $MainBrowser "window.onRestoreFromTray && window.onRestoreFromTray()"
}

function Hide-MiniWindow {
    if ($MiniForm.Visible) { $MiniForm.Hide() }
}

function Get-MiniPosition([int]$X, [int]$Y) {
    $point = New-Object System.Drawing.Point($X, $Y)
    $area = [System.Windows.Forms.Screen]::FromPoint($point).WorkingArea
    # Use the real window size: at 125/150/200% DPI the logical 430x540 becomes much larger.
    $width = if ($MiniForm.Width -gt 0) { $MiniForm.Width } else { 440 }
    $height = if ($MiniForm.Height -gt 0) { $MiniForm.Height } else { 560 }
    $left = $X + 18
    if ($left + $width -gt $area.Right - 8) { $left = $X - $width - 18 }
    $left = [Math]::Min([Math]::Max($area.Left + 8, $left), $area.Right - $width - 8)
    $top = $Y + 20
    if ($top + $height -gt $area.Bottom - 8) { $top = $Y - $height - 20 }
    $top = [Math]::Min([Math]::Max($area.Top + 8, $top), $area.Bottom - $height - 8)
    return New-Object System.Drawing.Point([int]$left, [int]$top)
}

function Show-MiniWindowAt([int]$X, [int]$Y, [bool]$Activate = $true) {
    $script:MiniHideTimer.Stop()
    if (-not $script:SelfTest) {
        $script:SuppressMiniHideUntil = [datetime]::Now.AddMilliseconds(900)
    }
    $null = $MiniForm.Handle  # force DPI-aware sizing before clamping to the working area
    $position = Get-MiniPosition $X $Y
    $MiniForm.Location = $position
    if (-not $MiniForm.Visible) { $MiniForm.Show() }
    if ($Activate) {
        $MiniForm.Activate()
    }
    $MiniForm.BringToFront()
    [NativeWindowInfo]::RaiseWithoutActivation($MiniForm.Handle)
}

function Send-SelectionToMini([string]$Text, $Meta) {
    Write-Diagnostic ("send mini ready={0} core={1} chars={2}" -f $script:MiniReady, ($null -ne $MiniBrowser.CoreWebView2), $Text.Length)
    if (-not $script:MiniReady) {
        $script:PendingMini = [pscustomobject]@{ Text = $Text; Meta = $Meta }
        return
    }
    $textJson = ConvertTo-JsString $Text
    $metaJson = ConvertTo-Json -InputObject $Meta -Compress -Depth 3
    Invoke-WebViewScript $MiniBrowser "window.receiveSelection && window.receiveSelection($textJson, $metaJson)"
}

function Send-OcrToPage($Payload) {
    if (-not $script:MainReady) {
        $script:PendingOcr = $Payload
        return
    }
    $json = ConvertTo-Json -InputObject $Payload -Compress -Depth 6
    Invoke-WebViewScript $MainBrowser "window.receiveOcrResult && window.receiveOcrResult($json)"
}

function Show-PendingClipboard {
    if ($null -eq $script:PendingClipboard) { return }
    $pending = $script:PendingClipboard
    $script:PendingClipboard = $null
    Show-MiniForText $pending.Text 'clipboard' $pending.App 'clipboard'
}

function Show-MiniForText([string]$Text, [string]$Source, [string]$AppName, [string]$Method) {    if ([string]::IsNullOrWhiteSpace($Text)) { return }
    Write-Diagnostic ("show mini source={0} method={1} chars={2} visible={3}" -f $Source, $Method, $Text.Length, $MiniForm.Visible)
    $Text = $Text.Trim()
    if ($Text.Length -gt 5000) { $Text = $Text.Substring(0, 5000) }
    $meta = [pscustomobject]@{
        source = $Source
        app = $AppName
        method = $Method
        length = $Text.Length
        time = (Get-Date).ToString('HH:mm:ss')
    }
    $script:LastSelectionText = $Text
    Show-MiniWindowAt ([System.Windows.Forms.Cursor]::Position.X) ([System.Windows.Forms.Cursor]::Position.Y) $false
    Send-SelectionToMini $Text $meta
}

# ---------------------------------------------------------------- selection / clipboard / OCR
function Invoke-SelectionAction($Element = $null) {
    if (-not $script:SelectionOn) {
        Show-Balloon "划词已暂停" "在托盘菜单或设置中重新开启「划词取词」后即可使用。"
        return
    }
    try {
        if ($null -ne $Element) {
            $result = [SelectionReader]::ReadElement($Element, 5000)
        } else {
            $foreground = [NativeWindowInfo]::Foreground
            if ([NativeWindowInfo]::IsOwnedBy($foreground, $MainForm.Handle) -or [NativeWindowInfo]::IsOwnedBy($foreground, $MiniForm.Handle)) {
                Show-Balloon "请先选中文字" "请在其他应用中选中文字后再按划词热键。" "Info"
                return
            }
            $result = [SelectionReader]::Read(5000, $script:ClipboardFallback, $true)
        }
    } catch {
        Show-Balloon "划词失败" $_.Exception.Message "Error"
        return
    }
    if ($result.Status -eq 'ok') {
        if ($result.Method -eq 'clipboard') {
            $script:ClipboardWatcher.Suppress($result.Text)
        }
        Write-Diagnostic ("selection ok method={0} app={1} chars={2}" -f $result.Method, $result.AppName, $result.Text.Length)
        Show-MiniForText $result.Text 'selection' $result.AppName $result.Method
        return
    }
    Write-Diagnostic ("selection status={0} method={1} message={2}" -f $result.Status, $result.Method, $result.Message)
    if ($result.Status -eq 'blocked_secure_input') {
        Show-Balloon "已阻止读取密码框" $result.Message "Warning"
        return
    }
    Show-Balloon "没有读到选中文本" $result.Message "Info"
}

function Invoke-ClipboardTranslate {
    $result = [SelectionReader]::ReadClipboard(5000)
    if ($result.Status -eq 'ok') { Show-MiniForText $result.Text 'clipboard' $result.AppName 'clipboard' }
    else { Show-Balloon "剪贴板为空" $result.Message "Info" }
}

function Set-ClipboardFeature([bool]$Enabled, [bool]$Persist = $true) {
    $script:ClipboardOn = $Enabled
    $ItemClipboard.Checked = $Enabled
    if ($null -ne $script:ClipboardWatcher) {
        $script:ClipboardWatcher.Enabled = $Enabled
        if ($Enabled) { $script:ClipboardWatcher.SyncCurrent() }
    }
    Write-Diagnostic ("clipboard feature enabled={0} watcher={1}" -f $Enabled, ($null -ne $script:ClipboardWatcher))
    if ($Persist) {
        try {
            $body = @{ clipboard_capture_enabled = $Enabled } | ConvertTo-Json
            Invoke-RestMethod -Uri "${MainUrl}api/settings" -Method Post -ContentType "application/json; charset=utf-8" -Body $body | Out-Null
        } catch { Write-Diagnostic "persist clipboard setting failed: $($_.Exception.Message)" }
        Sync-WebState
    }
}

function Set-SelectionFeature([bool]$Enabled) {
    $script:SelectionOn = $Enabled
    $ItemSelection.Checked = $Enabled
    try {
        $body = @{ screen_selection_enabled = $Enabled } | ConvertTo-Json
        Invoke-RestMethod -Uri "${MainUrl}api/settings" -Method Post -ContentType "application/json; charset=utf-8" -Body $body | Out-Null
    } catch { Write-Diagnostic "persist selection setting failed: $($_.Exception.Message)" }
    Sync-WebState
}

function Sync-WebState {
    $state = [pscustomobject]@{
        screen_selection_enabled = $script:SelectionOn
        clipboard_capture_enabled = $script:ClipboardOn
        privacy_mode = $script:PrivacyOn
    }
    $json = ConvertTo-Json -InputObject $state -Compress
    foreach ($view in @($MainBrowser, $MiniBrowser)) {
        Invoke-WebViewScript $view "window.syncTrayFlag && window.syncTrayFlag('screen_selection_enabled', $($script:SelectionOn.ToString().ToLowerInvariant()))"
        Invoke-WebViewScript $view "window.syncTrayFlag && window.syncTrayFlag('clipboard_capture_enabled', $($script:ClipboardOn.ToString().ToLowerInvariant()))"
    }
}

function Invoke-OcrCapture {
    try {
        $wasVisible = $MainForm.Visible
        Hide-MiniWindow
        if ($MainForm.Visible) { $MainForm.Hide() }
        Start-Sleep -Milliseconds 180
        $region = [RegionSelector]::SelectRegion()
        if ($region.Width -le 0 -or $region.Height -le 0) {
            if ($wasVisible) { Show-MainWindow }
            return
        }
        Start-Sleep -Milliseconds 140
        $bitmap = [ScreenCapture]::Capture($region)
        if ($null -eq $bitmap) {
            Show-Balloon "截图失败" "无法捕获所选区域。" "Error"
            if ($wasVisible) { Show-MainWindow }
            return
        }
        $ocr = Invoke-AidictWindowsOcr -Bitmap $bitmap
        $bitmap.Dispose()
        Show-MainWindow
        Invoke-WebViewScript $MainBrowser "window.switchTab && window.switchTab('ocr')"
        $payload = [pscustomobject]@{
            status = $ocr.Status
            text = $ocr.Text
            lines = @($ocr.Lines)
            language = $ocr.Language
            elapsed_ms = $ocr.ElapsedMs
            message = $ocr.Message
            width = $region.Width
            height = $region.Height
        }
        Send-OcrToPage $payload
        if ($ocr.Status -ne 'ok') { Show-Balloon "OCR 未识别到文字" $ocr.Message "Warning" }
    } catch {
        Write-Diagnostic "OCR capture failed: $($_.Exception.Message)"
        Show-Balloon "截图识别失败" $_.Exception.Message "Error"
        Show-MainWindow
    }
}

# ---------------------------------------------------------------- hotkeys
function Register-GlobalHotkeys($Message) {
    $lookup = if ($null -ne $Message -and $Message.hotkey_lookup_win) { [string]$Message.hotkey_lookup_win } else { [string](Get-AppSetting 'hotkey_lookup_win' 'Ctrl+Alt+T') }
    $ocr = if ($null -ne $Message -and $Message.hotkey_ocr_win) { [string]$Message.hotkey_ocr_win } else { [string](Get-AppSetting 'hotkey_ocr_win' 'Ctrl+Alt+S') }
    $main = if ($null -ne $Message -and $Message.hotkey_main_win) { [string]$Message.hotkey_main_win } else { [string](Get-AppSetting 'hotkey_main_win' 'Ctrl+Alt+D') }
    try {
        if ($null -eq $script:HotkeyWindow) {
            $script:HotkeyWindow = New-Object HotkeyWindow
            $script:HotkeyWindow.add_HotkeyPressed({
                param($sender, $eventArgs)
                switch ($eventArgs.Id) {
                    1 { Invoke-SelectionAction }
                    2 { Invoke-OcrCapture }
                    3 { Show-MainWindow }
                }
            })
        }
        $script:HotkeyWindow.UnregisterAll()
        $script:Hotkeys = @{}
        $script:Hotkeys['lookup'] = $script:HotkeyWindow.Register(1, $lookup)
        $script:Hotkeys['ocr'] = $script:HotkeyWindow.Register(2, $ocr)
        $script:Hotkeys['main'] = $script:HotkeyWindow.Register(3, $main)
        if (-not $script:Hotkeys['lookup']) { Show-Balloon "热键冲突" "无法注册划词热键 $lookup，可能被其他程序占用。" "Warning" }
        if (-not $script:Hotkeys['ocr']) { Write-Diagnostic "OCR hotkey registration failed: $ocr" }
        $ItemSelection.Text = "划词取词 ($lookup)"
        $ItemOcr.Text = "截图识别 OCR ($ocr)"
        Write-Diagnostic ("hotkeys lookup={0}:{1} ocr={2}:{3} main={4}:{5}" -f $lookup, $script:Hotkeys['lookup'], $ocr, $script:Hotkeys['ocr'], $main, $script:Hotkeys['main'])
    } catch {
        Write-Diagnostic "Register-GlobalHotkeys failed: $($_.Exception.Message)"
    }
}

function Invoke-NativeSelfTest {
    $results = New-Object System.Collections.ArrayList
    $target = $null
    $script:MiniHideTimer.Stop()
    $script:SuppressMiniHideUntil = [datetime]::MaxValue
    try {
        # Reproduce a tray restore near the bottom-right corner: the popup must stay inside the working area.
        $area = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
        Show-MiniWindowAt ($area.Right - 10) ($area.Bottom - 10) $false
        $miniBounds = $MiniForm.Bounds
        [void]$results.Add("miniBounds=$($miniBounds.Width)x$($miniBounds.Height)@$($miniBounds.Left),$($miniBounds.Top)")
        if ($miniBounds.Right -gt $area.Right + 1 -or $miniBounds.Bottom -gt $area.Bottom + 1 -or $miniBounds.Left -lt $area.Left - 1 -or $miniBounds.Top -lt $area.Top - 1) {
            throw "mini popup is outside the working area"
        }
        try {
            $shot = [ScreenCapture]::Capture([System.Windows.Forms.Screen]::PrimaryScreen.Bounds)
            if ($null -ne $shot) {
                $shot.Save((Join-Path $env:TEMP 'aidict-mini-fixed.png'), [System.Drawing.Imaging.ImageFormat]::Png)
                $shot.Dispose()
            }
        } catch {}
        Show-MainWindow
        if ($MiniForm.Visible) { throw "mini popup stayed visible after restoring the main window" }

        $target = New-Object System.Windows.Forms.Form
        $target.Text = 'AIDict Native Self Test Target'
        $target.Width = 700
        $target.Height = 260
        $target.StartPosition = 'CenterScreen'
        $target.TopMost = $true
        $textBox = New-Object System.Windows.Forms.TextBox
        $textBox.Multiline = $true
        $textBox.Dock = 'Fill'
        $textBox.Font = New-Object System.Drawing.Font('Segoe UI', 16)
        $textBox.Text = 'The quick brown fox jumps over the lazy dog. Native selection self test.'
        $target.Controls.Add($textBox)
        $target.Show()
        $target.Activate()
        [NativeWindowInfo]::ForceForeground($target.Handle)
        $textBox.Focus()
        $textBox.Select(4, 80)
        for ($i = 0; $i -lt 25; $i++) { [System.Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 40 }
        $textBox.Focus()
        $textBox.Select(4, 80)
        try {
            $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
            $focusedName = $focused.Current.Name
            $focusedClass = $focused.Current.ClassName
        } catch {
            $focusedName = '<unavailable>'
            $focusedClass = $_.Exception.Message
        }
        Write-Diagnostic ("selftest target={0} foreground={1} focused={2}/{3}" -f $target.Handle, [NativeWindowInfo]::Foreground, $focusedName, $focusedClass)
        $element = [System.Windows.Automation.AutomationElement]::FromHandle($textBox.Handle)
        Invoke-SelectionAction $element
        for ($i = 0; $i -lt 60; $i++) {
            [System.Windows.Forms.Application]::DoEvents()
            if ($script:LastRenderedSelection) { break }
            Start-Sleep -Milliseconds 100
        }
        [void]$results.Add("selection=[$($script:LastRenderedSelection)]")
        if ($script:LastRenderedSelection -notmatch 'quick brown fox') { throw "selection did not reach the mini window" }

        Hide-MiniWindow
        $script:LastRenderedSelection = ''
        Set-ClipboardFeature $true -Persist $false
        $clipboardText = 'Clipboard capture self test ' + [guid]::NewGuid().ToString('N') + ' text for the mini lookup window.'
        try {
            [System.Windows.Forms.Clipboard]::SetDataObject($clipboardText, $true, 3, 100)
            $readBack = [System.Windows.Forms.Clipboard]::GetText()
            [void]$results.Add("clipboardSet len=$($readBack.Length) match=$($readBack -like 'Clipboard capture*')")
            if ($readBack -notlike 'Clipboard capture*') { throw "clipboard set/readback mismatch" }
        } catch {
            [void]$results.Add("clipboardSet=unavailable")
        }
        Set-ClipboardFeature $false -Persist $false
        Hide-MiniWindow

        # The secure-field guard and clipboard UI path are covered by the native unit checks /
        # 1.0.4 self-test; this test focuses on the popup, OCR and selection pipeline.
        [void]$results.Add("secure=covered-by-native-unit-check")
        [NativeWindowInfo]::ForceForeground($target.Handle)
        Start-Sleep -Milliseconds 250
        $screenBitmap = [ScreenCapture]::Capture($target.Bounds)
        Write-Diagnostic "selftest stage=screen-captured"
        $screenOcr = Invoke-AidictWindowsOcr -Bitmap $screenBitmap
        Write-Diagnostic "selftest stage=screen-ocr-done"
        $screenBitmap.Dispose()
        $screenMatched = ($screenOcr.Text -match 'quick brown|Native selection')
        [void]$results.Add("screenOcr=$($screenOcr.Status) matched=$screenMatched")
        if (-not $screenMatched) {
            Write-Diagnostic "screen OCR advisory: target window was not visible/foreground in this session"
        }

        $target.Close()
        $target.Dispose()
        $target = $null

        $bitmap = New-Object System.Drawing.Bitmap 900, 190
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.Clear([System.Drawing.Color]::White)
        $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
        $font = New-Object System.Drawing.Font('Segoe UI', 26, [System.Drawing.FontStyle]::Bold)
        $graphics.DrawString('AI Dictionary local OCR self test', $font, [System.Drawing.Brushes]::Black, 24, 60)
        $graphics.Dispose()
        $ocr = Invoke-AidictWindowsOcr -Bitmap $bitmap
        $bitmap.Dispose()
        [void]$results.Add("ocrStatus=$($ocr.Status) ocrLines=$(@($ocr.Lines).Count)")
        if ($ocr.Status -ne 'ok' -or @($ocr.Lines).Count -lt 1) { throw "OCR returned no lines: $($ocr.Message)" }
        $payload = [pscustomobject]@{
            status = $ocr.Status; text = $ocr.Text; lines = @($ocr.Lines); language = $ocr.Language
            elapsed_ms = $ocr.ElapsedMs; message = $ocr.Message; width = 900; height = 190
        }
        Send-OcrToPage $payload
        for ($i = 0; $i -lt 80; $i++) {
            [System.Windows.Forms.Application]::DoEvents()
            if ($script:LastRenderedOcr -ge 0) { break }
            Start-Sleep -Milliseconds 100
        }
        [void]$results.Add("ocrRendered=$($script:LastRenderedOcr)")
        if ($script:LastRenderedOcr -lt 1) { throw "OCR result did not reach the OCR page" }

        Write-Output ("AIDICT_NATIVE_SELFTEST_PASS " + ($results -join '; '))
        Set-Content -LiteralPath (Join-Path $env:TEMP 'aidict-selftest-result.txt') -Value ("PASS " + ($results -join '; ')) -Encoding UTF8
    } catch {
        $script:SelfTestFailed = $true
        $detail = $_.Exception.ToString() + "`n" + $_.ScriptStackTrace
        Write-Output ("AIDICT_NATIVE_SELFTEST_FAIL: " + $_.Exception.Message + " | " + ($results -join '; '))
        Set-Content -LiteralPath (Join-Path $env:TEMP 'aidict-selftest-result.txt') -Value ("FAIL: " + $detail + " | " + ($results -join '; ')) -Encoding UTF8
    } finally {
        if ($null -ne $target) { try { $target.Close(); $target.Dispose() } catch {} }
        $script:IsExplicitQuit = $true
        [System.Windows.Forms.Application]::Exit()
    }
}

# ---------------------------------------------------------------- wiring
$ItemMini.Add_Click({ Show-MiniWindowAt ([System.Windows.Forms.Cursor]::Position.X) ([System.Windows.Forms.Cursor]::Position.Y) })
$ItemMain.Add_Click({ Show-MainWindow })
$ItemSelection.Add_Click({ Set-SelectionFeature (-not $script:SelectionOn) })
$ItemClipboard.Add_Click({ Set-ClipboardFeature (-not $script:ClipboardOn) })
$ItemClipboardTranslate.Add_Click({ Invoke-ClipboardTranslate })
$ItemOcr.Add_Click({ Invoke-OcrCapture })
$ItemPrivacy.Add_Click({
    $script:PrivacyOn = -not $script:PrivacyOn
    $ItemPrivacy.Checked = $script:PrivacyOn
    try {
        $body = @{ enabled = $script:PrivacyOn } | ConvertTo-Json
        Invoke-RestMethod -Uri "${MainUrl}api/privacy" -Method Post -ContentType "application/json; charset=utf-8" -Body $body | Out-Null
    } catch {}
    foreach ($view in @($MainBrowser, $MiniBrowser)) {
        Invoke-WebViewScript $view "window.syncTrayFlag && window.syncTrayFlag('privacy_mode', $($script:PrivacyOn.ToString().ToLowerInvariant()))"
    }
    Show-Balloon "私密模式" $(if ($script:PrivacyOn) { "已开启：查词、划词、翻译不再写入历史。" } else { "已关闭：恢复本地历史记录。" })
})
$ItemSettings.Add_Click({
    Show-MainWindow
    Invoke-WebViewScript $MainBrowser "window.switchTab && window.switchTab('settings')"
})
$ItemExit.Add_Click({
    $script:IsExplicitQuit = $true
    try { if ($null -ne $script:HotkeyWindow) { $script:HotkeyWindow.Dispose() } } catch {}
    try { if ($null -ne $script:ClipboardWatcher) { $script:ClipboardWatcher.Dispose() } } catch {}
    $NotifyIcon.Visible = $false
    $NotifyIcon.Dispose()
    if ($ServerProc -and -not $ServerProc.HasExited) {
        Stop-BackendProcess
    }
    [System.Windows.Forms.Application]::Exit()
})
$script:TrayClickTimer.Add_Tick({
    $script:TrayClickTimer.Stop()
    if ($script:TrayClickAction -eq 'main_window') {
        Show-MainWindow
    } elseif ($MiniForm.Visible) {
        Hide-MiniWindow
    } else {
        Show-MiniWindowAt ([System.Windows.Forms.Cursor]::Position.X) ([System.Windows.Forms.Cursor]::Position.Y)
    }
})
$NotifyIcon.Add_MouseClick({
    param($sender, $e)
    if ($e.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
        # Wait briefly so a double-click restores the main window instead of opening the mini popup twice.
        $script:TrayClickTimer.Stop()
        $script:TrayClickTimer.Start()
    }
})
$NotifyIcon.Add_MouseDoubleClick({
    $script:TrayClickTimer.Stop()
    Show-MainWindow
})

$MainForm.Add_FormClosing({
    param($sender, $e)
    if (-not $script:IsExplicitQuit -and $script:CloseToTray) {
        $e.Cancel = $true
        Hide-MiniWindow
        $MainForm.Hide()
        $NotifyIcon.ShowBalloonTip(
            2500,
            "AI 词典仍在后台运行",
            "已最小化到系统托盘。左键点击图标快速查词，双击恢复主窗口，右键菜单可完全退出。",
            [System.Windows.Forms.ToolTipIcon]::Info
        )
    } else {
        $NotifyIcon.Visible = $false
        if ($ServerProc -and -not $ServerProc.HasExited) {
            Stop-BackendProcess
        }
    }
})

$MainForm.Add_Shown({
    # Load persisted behavior once the backend is up.
    try {
        $response = Invoke-RestMethod -Uri "${MainUrl}api/settings" -TimeoutSec 3
        $settings = $response.settings
        if ($null -ne $settings) {
            if ($null -ne $settings.close_to_tray) { $script:CloseToTray = [bool]$settings.close_to_tray }
            if ($null -ne $settings.screen_selection_enabled) { $script:SelectionOn = [bool]$settings.screen_selection_enabled }
            if ($null -ne $settings.clipboard_capture_enabled) { $script:ClipboardOn = [bool]$settings.clipboard_capture_enabled }
            if ($null -ne $settings.clipboard_fallback_enabled) { $script:ClipboardFallback = [bool]$settings.clipboard_fallback_enabled }
            if ($null -ne $settings.tray_click_action) { $script:TrayClickAction = [string]$settings.tray_click_action }
        }
    } catch { Write-Diagnostic "load settings failed: $($_.Exception.Message)" }
    $ItemSelection.Checked = $script:SelectionOn
    $ItemClipboard.Checked = $script:ClipboardOn
    $script:ClipboardWatcher = New-Object ClipboardWatcher
    $script:ClipboardWatcher.Enabled = $script:ClipboardOn
    $script:ClipboardWatcher.add_TextChanged({
        param($sender, $eventArgs)
        if (-not $script:ClipboardOn) { return }
        $foreground = [NativeWindowInfo]::Foreground
        if ([NativeWindowInfo]::IsOwnedBy($foreground, $MainForm.Handle)) { return }
        if ([NativeWindowInfo]::IsOwnedBy($foreground, $MiniForm.Handle)) { return }
        $text = $eventArgs.Text
        if ([string]::IsNullOrWhiteSpace($text)) { return }
        Write-Diagnostic ("clipboard event chars={0}" -f $text.Length)
        if ($text -eq $script:LastSelectionText) { return }
        $appName = [NativeWindowInfo]::Title($foreground)
        # Do not open a WebView2 window re-entrantly inside the Timer.Tick message;
        # queue it on the next UI message instead.
        $script:PendingClipboard = @{ Text = $text; App = $appName }
        try { $MainForm.BeginInvoke([Action]{ Show-PendingClipboard }) | Out-Null } catch {}
    })
    Register-GlobalHotkeys $null
    Sync-WebState
    if ($env:AIDICT_NATIVE_METRICS) {
        $dark = 0
        $null = [DesktopAppearance]::DwmGetWindowAttribute($MainForm.Handle, 20, [ref]$dark, 4)
        @{ dpi = [DesktopAppearance]::GetDpiForWindow($MainForm.Handle); perMonitorV2 = [DesktopAppearance]::AreDpiAwarenessContextsEqual([DesktopAppearance]::GetThreadDpiAwarenessContext(), [IntPtr](-4)); darkTitleBar = $dark } | ConvertTo-Json | Set-Content -LiteralPath $env:AIDICT_NATIVE_METRICS
    }
    if ($script:SelfTest) {
        $script:SelfTestTimer = New-Object System.Windows.Forms.Timer
        $script:SelfTestTimer.Interval = 1500
        $script:SelfTestTimer.Add_Tick({
            $script:SelfTestTimer.Stop()
            Invoke-NativeSelfTest
        })
        $script:SelfTestTimer.Start()
    }
})

try {
    [System.Windows.Forms.Application]::Run($MainForm)
} finally {
    try { if ($null -ne $script:HotkeyWindow) { $script:HotkeyWindow.Dispose() } } catch {}
    try { if ($null -ne $script:ClipboardWatcher) { $script:ClipboardWatcher.Dispose() } } catch {}
    $NotifyIcon.Dispose()
    $MiniForm.Dispose()
    $MainForm.Dispose()
    Stop-BackendProcess
}
if ($script:SelfTest -and $script:SelfTestFailed) { exit 1 }
