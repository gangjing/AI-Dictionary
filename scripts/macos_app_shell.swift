import Cocoa
import WebKit
import Carbon
import ApplicationServices
import Vision
import CoreGraphics
import Darwin

@_silgen_name("IsSecureEventInputEnabled")
func IsSecureEventInputEnabled() -> DarwinBoolean

private let hotKeySignature: OSType = 0x41494443 // 'AIDC'

private func hotKeyEventHandler(
    _ nextHandler: EventHandlerCallRef?,
    _ event: EventRef?,
    _ userData: UnsafeMutableRawPointer?
) -> OSStatus {
    guard let event = event, let userData = userData else { return noErr }
    var hotKeyID = EventHotKeyID()
    let status = GetEventParameter(
        event,
        EventParamName(kEventParamDirectObject),
        EventParamType(typeEventHotKeyID),
        nil,
        UInt32(MemoryLayout<EventHotKeyID>.size),
        nil,
        &hotKeyID
    )
    if status == noErr {
        let delegate = Unmanaged<AppDelegate>.fromOpaque(userData).takeUnretainedValue()
        DispatchQueue.main.async {
            delegate.handleHotKey(id: Int(hotKeyID.id))
        }
    }
    return noErr
}

final class ResultPanel: NSPanel {
    override var canBecomeKey: Bool { return true }
    override var canBecomeMain: Bool { return false }
}

final class OcrOverlayWindow: NSWindow {
    override var canBecomeKey: Bool { return true }
    override var canBecomeMain: Bool { return false }
}

final class OcrSelectionView: NSView {
    var startPoint: NSPoint?
    var selection: NSRect = .zero
    var onComplete: ((NSRect) -> Void)?
    var onCancel: (() -> Void)?

    override var acceptsFirstResponder: Bool { return true }

    override func draw(_ dirtyRect: NSRect) {
        NSColor.black.withAlphaComponent(0.34).setFill()
        bounds.fill()
        if selection.width > 0 && selection.height > 0 {
            NSGraphicsContext.saveGraphicsState()
            NSColor.clear.setFill()
            NSRectFillUsingOperation(selection, NSCompositingOperation.copy)
            NSGraphicsContext.restoreGraphicsState()
            NSColor(calibratedRed: 0.23, green: 0.51, blue: 0.96, alpha: 1).setStroke()
            let border = NSBezierPath(rect: selection)
            border.lineWidth = 2
            border.stroke()
            let label = "\(Int(selection.width)) × \(Int(selection.height))"
            let attributes: [NSAttributedString.Key: Any] = [
                .font: NSFont.systemFont(ofSize: 12, weight: .semibold),
                .foregroundColor: NSColor.white
            ]
            let size = (label as NSString).size(withAttributes: attributes)
            let origin = NSPoint(x: selection.minX, y: min(selection.maxY + 6, bounds.maxY - size.height - 4))
            NSColor(calibratedRed: 0.06, green: 0.09, blue: 0.16, alpha: 0.9).setFill()
            NSRect(x: origin.x, y: origin.y, width: size.width + 12, height: size.height + 6).fill()
            (label as NSString).draw(at: NSPoint(x: origin.x + 6, y: origin.y + 3), withAttributes: attributes)
        } else {
            let message = "拖拽框选中英文字符，Esc 取消"
            let attributes: [NSAttributedString.Key: Any] = [
                .font: NSFont.systemFont(ofSize: 18, weight: .semibold),
                .foregroundColor: NSColor.white
            ]
            let size = (message as NSString).size(withAttributes: attributes)
            (message as NSString).draw(
                at: NSPoint(x: (bounds.width - size.width) / 2, y: bounds.height - 90),
                withAttributes: attributes
            )
        }
    }

    override func mouseDown(with event: NSEvent) {
        startPoint = convert(event.locationInWindow, from: nil)
        selection = .zero
        needsDisplay = true
    }

    override func mouseDragged(with event: NSEvent) {
        guard let start = startPoint else { return }
        let current = convert(event.locationInWindow, from: nil)
        selection = NSRect(
            x: min(start.x, current.x),
            y: min(start.y, current.y),
            width: abs(start.x - current.x),
            height: abs(start.y - current.y)
        )
        needsDisplay = true
    }

    override func mouseUp(with event: NSEvent) {
        guard selection.width > 8 && selection.height > 8, let window = window else {
            onCancel?()
            return
        }
        let screenRect = window.convertToScreen(selection)
        onComplete?(screenRect)
    }

    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 {
            onCancel?()
        } else {
            super.keyDown(with: event)
        }
    }
}

class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKScriptMessageHandler, WKNavigationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var statusItem: NSStatusItem!
    var popover: NSPopover!
    var popoverWebView: WKWebView!
    var statusMenu: NSMenu!

    var resultPanel: ResultPanel!
    var resultWebView: WKWebView!

    var menuSelectionItem: NSMenuItem!
    var menuClipboardItem: NSMenuItem!
    var menuOcrItem: NSMenuItem!
    var menuPrivacyItem: NSMenuItem!

    var serverProcess: Process?
    var smokeNavigationMessages = 0
    let smokeTest = ProcessInfo.processInfo.arguments.contains("--smoke-test")
    let serverPort = 14205

    var closeToTray: Bool = true
    var isExplicitQuit: Bool = false
    var screenSelectionEnabled: Bool = true
    var clipboardCaptureEnabled: Bool = false
    var clipboardFallbackEnabled: Bool = true
    var privacyModeEnabled: Bool = false

    var hotKeyRefs: [EventHotKeyRef?] = []
    var hotKeyHandler: EventHandlerRef?
    var lookupHotkey = "Option+Command+T"
    var ocrHotkey = "Option+Command+S"
    var mainHotkey = "Option+Command+D"

    var resultReady = false
    var pendingResult: (String, [String: Any])?
    var lastSelectionText = ""
    var clipboardTimer: Timer?
    var lastClipboardChange = NSPasteboard.general.changeCount
    var ocrOverlay: OcrOverlayWindow?

    func applicationDidFinishLaunching(_ notification: Notification) {
        startBackendDaemon()
        setupMainMenu()
        setupMainWindow()
        setupResultPanel()
        setupYoudaoStyleStatusBar()
        setupHotkeys()
        setupClipboardMonitor()
        setupDismissMonitors()
        waitForServerAndLoad(retries: 150)
    }

    func setupMainMenu() {
        let mainMenu = NSMenu()
        let appMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "显示 AI 词典主窗口", action: #selector(showMainWindowAction), keyEquivalent: "d")
        appMenu.addItem(withTitle: "打开信息栏迷你查词窗", action: #selector(togglePopoverAction), keyEquivalent: "m")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "隐藏到顶部信息栏 (不退出)", action: #selector(hideMainWindowToTray), keyEquivalent: "w")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "完全退出 AI 词典", action: #selector(explicitQuitAction), keyEquivalent: "q")
        appMenuItem.submenu = appMenu
        let editItem = NSMenuItem()
        let editMenu = NSMenu(title: "编辑")
        editMenu.addItem(withTitle: "撤销", action: Selector(("undo:")), keyEquivalent: "z")
        editMenu.addItem(withTitle: "剪切", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "复制", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "粘贴", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "全选", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = editMenu
        mainMenu.addItem(editItem)
        NSApp.mainMenu = mainMenu
    }

    func setupMainWindow() {
        let screenRect = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1280, height: 820)
        let winWidth: CGFloat = 1120
        let winHeight: CGFloat = 750
        let originX = screenRect.origin.x + (screenRect.size.width - winWidth) / 2
        let originY = screenRect.origin.y + (screenRect.size.height - winHeight) / 2

        window = NSWindow(
            contentRect: NSRect(x: originX, y: originY, width: winWidth, height: winHeight),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "AI Dictionary — 本地离线词典与翻译 (关闭窗口将驻留顶部信息栏)"
        window.minSize = NSSize(width: 860, height: 560)
        window.delegate = self
        window.isReleasedWhenClosed = false
        window.backgroundColor = NSColor(calibratedRed: 0.06, green: 0.09, blue: 0.16, alpha: 1.0)

        let config = WKWebViewConfiguration()
        config.userContentController.add(self, name: "nativeShell")
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")
        webView = WKWebView(frame: window.contentView!.bounds, configuration: config)
        webView.navigationDelegate = self
        webView.autoresizingMask = [.width, .height]
        window.contentView?.addSubview(webView)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func setupResultPanel() {
        let panel = ResultPanel(
            contentRect: NSRect(x: 0, y: 0, width: 430, height: 560),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = true

        let config = WKWebViewConfiguration()
        config.userContentController.add(self, name: "nativeShell")
        resultWebView = WKWebView(frame: NSRect(x: 0, y: 0, width: 430, height: 560), configuration: config)
        resultWebView.navigationDelegate = self
        resultWebView.autoresizingMask = [.width, .height]
        panel.contentView = resultWebView
        resultWebView.frame = panel.contentView?.bounds ?? NSRect(x: 0, y: 0, width: 430, height: 560)
        resultPanel = panel
    }

    func setupYoudaoStyleStatusBar() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.title = "📖 AI词典"
            button.toolTip = "AI 词典 (常驻信息栏)\n• 左键点击：弹出有道式迷你查词小窗\n• 右键点击：打开快捷开关与退出菜单"
            button.target = self
            button.action = #selector(handleStatusBarClick(_:))
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        }

        popover = NSPopover()
        popover.contentSize = NSSize(width: 390, height: 500)
        popover.behavior = .transient
        popover.animates = false

        let popVC = NSViewController()
        let popConfig = WKWebViewConfiguration()
        popConfig.userContentController.add(self, name: "nativeShell")
        popoverWebView = WKWebView(frame: NSRect(x: 0, y: 0, width: 390, height: 500), configuration: popConfig)
        popoverWebView.navigationDelegate = self
        popVC.view = popoverWebView
        popover.contentViewController = popVC

        statusMenu = NSMenu(title: "AI 词典")

        let miniItem = NSMenuItem(title: "🔍 打开迷你查词小窗 (Mini 查词栏)", action: #selector(openPopoverExplicit), keyEquivalent: "m")
        miniItem.target = self
        statusMenu.addItem(miniItem)

        let mainItem = NSMenuItem(title: "📖 显示 AI 词典主窗口", action: #selector(showMainWindowAction), keyEquivalent: "d")
        mainItem.target = self
        statusMenu.addItem(mainItem)

        statusMenu.addItem(NSMenuItem.separator())

        menuSelectionItem = NSMenuItem(title: "屏幕划词翻译", action: #selector(toggleScreenSelectionAction), keyEquivalent: "")
        menuSelectionItem.target = self
        menuSelectionItem.state = screenSelectionEnabled ? .on : .off
        statusMenu.addItem(menuSelectionItem)

        menuClipboardItem = NSMenuItem(title: "剪贴板自动取词", action: #selector(toggleClipboardCaptureAction), keyEquivalent: "")
        menuClipboardItem.target = self
        menuClipboardItem.state = clipboardCaptureEnabled ? .on : .off
        statusMenu.addItem(menuClipboardItem)

        let translateClipboardItem = NSMenuItem(title: "翻译剪贴板内容", action: #selector(translateClipboardAction), keyEquivalent: "")
        translateClipboardItem.target = self
        statusMenu.addItem(translateClipboardItem)

        let ocrItem = NSMenuItem(title: "📸 区域截图 OCR 翻译", action: #selector(startOcrCaptureAction), keyEquivalent: "s")
        ocrItem.target = self
        statusMenu.addItem(ocrItem)
        menuOcrItem = ocrItem

        menuPrivacyItem = NSMenuItem(title: "🛡️ 私密无痕查词模式", action: #selector(togglePrivacyModeAction), keyEquivalent: "")
        menuPrivacyItem.target = self
        menuPrivacyItem.state = privacyModeEnabled ? .on : .off
        statusMenu.addItem(menuPrivacyItem)

        statusMenu.addItem(NSMenuItem.separator())

        let settingsItem = NSMenuItem(title: "⚙️ 偏好设置与词库管理...", action: #selector(openSettingsTabAction), keyEquivalent: ",")
        settingsItem.target = self
        statusMenu.addItem(settingsItem)

        statusMenu.addItem(NSMenuItem.separator())

        let quitItem = NSMenuItem(title: "🚪 完全退出 AI 词典", action: #selector(explicitQuitAction), keyEquivalent: "q")
        quitItem.target = self
        statusMenu.addItem(quitItem)
    }

    // MARK: - Hotkeys

    func setupHotkeys() {
        var eventType = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard),
            eventKind: UInt32(kEventHotKeyPressed)
        )
        InstallEventHandler(
            GetApplicationEventTarget(),
            hotKeyEventHandler,
            1,
            &eventType,
            Unmanaged.passUnretained(self).toOpaque(),
            &hotKeyHandler
        )
        registerHotkeys(lookup: lookupHotkey, ocr: ocrHotkey, main: mainHotkey)
    }

    func registerHotkeys(lookup: String, ocr: String, main: String) {
        for ref in hotKeyRefs {
            if let ref = ref { UnregisterEventHotKey(ref) }
        }
        hotKeyRefs.removeAll()
        lookupHotkey = lookup
        ocrHotkey = ocr
        mainHotkey = main
        let lookupOK = registerHotkey(lookup, id: 1)
        let ocrOK = registerHotkey(ocr, id: 2)
        let mainOK = registerHotkey(main, id: 3)
        if !lookupOK {
            notify(title: "划词热键注册失败", message: "\(lookup) 可能已被其他应用占用，请在设置中更换组合键。")
        }
        if !ocrOK {
            notify(title: "截图热键注册失败", message: "\(ocr) 可能已被其他应用占用，请在设置中更换组合键。")
        }
        _ = mainOK
        menuSelectionItem?.title = "屏幕划词翻译 (\(lookup))"
        menuOcrItem?.title = "📸 区域截图 OCR 翻译 (\(ocr))"
    }

    @discardableResult
    func registerHotkey(_ text: String, id: UInt32) -> Bool {
        guard let parsed = HotkeyParser.parse(text) else { return false }
        var ref: EventHotKeyRef?
        let hotKeyID = EventHotKeyID(signature: hotKeySignature, id: id)
        let status = RegisterEventHotKey(parsed.keyCode, parsed.modifiers, hotKeyID, GetApplicationEventTarget(), 0, &ref)
        if status == noErr, let ref = ref {
            hotKeyRefs.append(ref)
            return true
        }
        return false
    }

    func handleHotKey(id: Int) {
        switch id {
        case 1:
            captureSelectionAction()
        case 2:
            startOcrCaptureAction()
        case 3:
            showMainWindowAction()
        default:
            break
        }
    }

    // MARK: - Clipboard monitor

    func setupClipboardMonitor() {
        clipboardTimer = Timer.scheduledTimer(withTimeInterval: 0.45, repeats: true) { [weak self] _ in
            self?.pollClipboard()
        }
        if let timer = clipboardTimer {
            RunLoop.main.add(timer, forMode: .common)
        }
    }

    func pollClipboard() {
        guard clipboardCaptureEnabled else { return }
        let pasteboard = NSPasteboard.general
        let changeCount = pasteboard.changeCount
        guard changeCount != lastClipboardChange else { return }
        lastClipboardChange = changeCount
        guard let text = pasteboard.string(forType: .string)?.trimmingCharacters(in: .whitespacesAndNewlines),
              !text.isEmpty else { return }
        guard text != lastSelectionText else { return }
        if NSApp.isActive && (resultPanel?.isVisible == true || window?.isVisible == true) { return }
        let appName = NSWorkspace.shared.frontmostApplication?.localizedName ?? ""
        showResult(text: String(text.prefix(5000)), source: "clipboard", app: appName, method: "clipboard")
    }

    func setupDismissMonitors() {
        NSEvent.addGlobalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
            self?.resultPanel?.orderOut(nil)
        }
        NSEvent.addLocalMonitorForEvents(matching: [.keyDown]) { [weak self] event in
            if event.keyCode == 53 {
                self?.resultPanel?.orderOut(nil)
                self?.popover?.performClose(nil)
            }
            return event
        }
    }

    // MARK: - Selection

    func captureSelectionAction() {
        guard screenSelectionEnabled else {
            NSSound.beep()
            return
        }
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
        guard AXIsProcessTrustedWithOptions(options) else {
            showPermissionAlert(
                title: "需要辅助功能权限",
                message: "请在「系统设置 → 隐私与安全性 → 辅助功能」中允许 AI Dictionary 读取选中文本。授权后重新按一次热键。",
                settingsURL: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
            )
            return
        }
        guard !IsSecureEventInputEnabled().boolValue else {
            NSSound.beep()
            notify(title: "已阻止读取密码框", message: "当前系统处于安全输入状态，不会读取选中文本或触发剪贴板回退。")
            return
        }

        let frontApp = NSWorkspace.shared.frontmostApplication
        let appName = frontApp?.localizedName ?? ""
        let bundleId = frontApp?.bundleIdentifier ?? ""
        if frontApp?.bundleIdentifier == Bundle.main.bundleIdentifier {
            NSSound.beep()
            notify(title: "请先选中文字", message: "请在其他应用中选中文字后再按划词热键。")
            return
        }
        let systemWide = AXUIElementCreateSystemWide()
        var focusedValue: CFTypeRef?
        let focusedError = AXUIElementCopyAttributeValue(
            systemWide,
            kAXFocusedUIElementAttribute as CFString,
            &focusedValue
        )
        guard focusedError == .success, let focused = focusedValue else {
            tryClipboardFallback(appName: appName, bundleId: bundleId)
            return
        }
        let element = focused as! AXUIElement
        let role = axAttribute(element, kAXRoleAttribute) as? String
        let subrole = axAttribute(element, kAXSubroleAttribute) as? String
        if subrole == "AXSecureTextField" {
            NSSound.beep()
            notify(title: "已阻止读取密码框", message: "当前焦点是安全输入框，不会读取文本，也不会使用剪贴板回退。")
            return
        }
        if let text = axAttribute(element, kAXSelectedTextAttribute) as? String, !text.isEmpty {
            showResult(text: String(text.prefix(5000)), source: "selection", app: appName, method: "ax")
            return
        }
        // Some apps expose the selection on a parent element.
        if let parentValue = axAttribute(element, kAXParentAttribute) {
            let parent = parentValue as! AXUIElement
            if let text = axAttribute(parent, kAXSelectedTextAttribute) as? String, !text.isEmpty {
                showResult(text: String(text.prefix(5000)), source: "selection", app: appName, method: "ax_parent")
                return
            }
        }
        _ = role
        tryClipboardFallback(appName: appName, bundleId: bundleId)
    }

    func tryClipboardFallback(appName: String, bundleId: String) {
        let terminalBundles = ["com.apple.Terminal", "com.googlecode.iterm2", "dev.warp.Warp-Stable", "io.alacritty", "net.kovidgoyal.kitty"]
        if terminalBundles.contains(bundleId) {
            notify(title: "终端窗口不支持安全复制回退", message: "在终端中发送 Command+C 可能被解释为中断命令；请手动复制后使用剪贴板取词。")
            return
        }
        guard clipboardFallbackEnabled else {
            notify(title: "没有读到选中文本", message: "当前应用不支持原生取词；可在设置中开启「划词失败时使用复制回退」。")
            return
        }
        if let text = clipboardFallback() {
            showResult(text: text, source: "selection", app: appName, method: "clipboard")
        } else {
            notify(title: "没有读到选中文本", message: "部分应用禁止自动复制。请先在目标应用中选中文字，或手动复制后使用剪贴板取词。")
        }
    }

    func clipboardFallback() -> String? {
        let pasteboard = NSPasteboard.general
        let savedItems = pasteboard.pasteboardItems
        let before = pasteboard.changeCount
        sendCommandC()
        let deadline = Date().addingTimeInterval(0.5)
        while Date() < deadline {
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
            if pasteboard.changeCount != before,
               let text = pasteboard.string(forType: .string)?.trimmingCharacters(in: .whitespacesAndNewlines),
               !text.isEmpty {
                restorePasteboard(savedItems)
                lastClipboardChange = pasteboard.changeCount
                return String(text.prefix(5000))
            }
        }
        restorePasteboard(savedItems)
        lastClipboardChange = pasteboard.changeCount
        return nil
    }

    func restorePasteboard(_ items: [NSPasteboardItem]?) {
        guard let items = items, !items.isEmpty else { return }
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.writeObjects(items)
    }

    func sendCommandC() {
        guard let source = CGEventSource(stateID: .hidSystemState) else { return }
        let keyCode: CGKeyCode = 0x08 // C
        let down = CGEvent(keyboardEventSource: source, virtualKey: keyCode, keyDown: true)
        down?.flags = .maskCommand
        down?.post(tap: .cghidEventTap)
        usleep(15_000)
        let up = CGEvent(keyboardEventSource: source, virtualKey: keyCode, keyDown: false)
        up?.flags = .maskCommand
        up?.post(tap: .cghidEventTap)
    }

    func axAttribute(_ element: AXUIElement, _ name: String) -> Any? {
        var value: CFTypeRef?
        let status = AXUIElementCopyAttributeValue(element, name as CFString, &value)
        return status == .success ? value : nil
    }

    // MARK: - Selection panel

    func showResult(text: String, source: String, app: String, method: String) {
        let trimmed = String(text.trimmingCharacters(in: .whitespacesAndNewlines).prefix(5000))
        guard !trimmed.isEmpty else { return }
        lastSelectionText = trimmed
        if popover.isShown { popover.performClose(nil) }
        positionResultPanel()
        resultPanel.orderFrontRegardless()
        let meta: [String: Any] = [
            "source": source,
            "app": app,
            "method": method,
            "length": trimmed.count,
            "time": DateFormatter.localizedString(from: Date(), dateStyle: .none, timeStyle: .medium)
        ]
        pendingResult = (trimmed, meta)
        if resultReady {
            injectPendingResult()
        }
    }

    func positionResultPanel() {
        let mouse = NSEvent.mouseLocation
        let screen = NSScreen.screens.first(where: { NSMouseInRect(mouse, $0.frame, false) }) ?? NSScreen.main
        guard let visible = screen?.visibleFrame else { return }
        let size = resultPanel.frame.size
        var x = mouse.x + 18
        var y = mouse.y - size.height - 18
        x = min(max(x, visible.minX + 8), visible.maxX - size.width - 8)
        y = min(max(y, visible.minY + 8), visible.maxY - size.height - 8)
        resultPanel.setFrameOrigin(NSPoint(x: x, y: y))
    }

    func injectPendingResult() {
        guard let pending = pendingResult else { return }
        let textJSON = HotkeyParser.jsonString(pending.0)
        let metaJSON = HotkeyParser.jsonString(pending.1)
        resultWebView.evaluateJavaScript(
            "window.receiveSelection && window.receiveSelection(\(textJSON), \(metaJSON))",
            completionHandler: nil
        )
        pendingResult = nil
    }

    // MARK: - OCR

    @objc func startOcrCaptureAction() {
        if !CGPreflightScreenCaptureAccess() {
            _ = CGRequestScreenCaptureAccess()
            showPermissionAlert(
                title: "需要屏幕录制权限",
                message: "请在「系统设置 → 隐私与安全性 → 屏幕录制」中允许 AI Dictionary，然后重新启动应用。",
                settingsURL: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
            )
            return
        }
        if popover.isShown { popover.performClose(nil) }
        resultPanel?.orderOut(nil)
        window?.orderOut(nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.18) {
            self.presentOcrOverlay()
        }
    }

    func presentOcrOverlay() {
        let screens = NSScreen.screens
        guard !screens.isEmpty else { return }
        var union = screens[0].frame
        for screen in screens.dropFirst() {
            union = union.union(screen.frame)
        }
        let overlay = OcrOverlayWindow(
            contentRect: union,
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        overlay.level = .screenSaver
        overlay.backgroundColor = .clear
        overlay.isOpaque = false
        overlay.hasShadow = false
        overlay.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        overlay.isReleasedWhenClosed = false

        let view = OcrSelectionView(frame: NSRect(origin: .zero, size: union.size))
        view.onCancel = { [weak self] in
            self?.ocrOverlay?.orderOut(nil)
            self?.ocrOverlay = nil
            self?.showMainWindowAction()
        }
        view.onComplete = { [weak self] rect in
            self?.ocrOverlay?.orderOut(nil)
            self?.ocrOverlay = nil
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.12) {
                self?.captureAndRecognize(rect: rect)
            }
        }
        overlay.contentView = view
        ocrOverlay = overlay
        overlay.makeKeyAndOrderFront(nil)
        overlay.makeFirstResponder(view)
        NSApp.activate(ignoringOtherApps: true)
    }

    func captureAndRecognize(rect: NSRect) {
        let screens = NSScreen.screens
        guard !screens.isEmpty else { return }
        var union = screens[0].frame
        for screen in screens.dropFirst() {
            union = union.union(screen.frame)
        }
        let quartzRect = CGRect(
            x: rect.minX,
            y: union.maxY - rect.maxY,
            width: rect.width,
            height: rect.height
        )
        guard let image = CGWindowListCreateImage(quartzRect, .optionOnScreenOnly, kCGNullWindowID, .bestResolution) else {
            deliverOcrFailure("无法捕获所选屏幕区域。")
            return
        }
        recognize(image: image)
    }

    func recognize(image: CGImage) {
        DispatchQueue.global(qos: .userInitiated).async {
            let started = CFAbsoluteTimeGetCurrent()
            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            request.recognitionLanguages = ["zh-Hans", "en-US"]
            request.usesLanguageCorrection = true
            let handler = VNImageRequestHandler(cgImage: image, options: [:])
            do {
                try handler.perform([request])
            } catch {
                DispatchQueue.main.async { self.deliverOcrFailure("OCR 失败：\(error.localizedDescription)") }
                return
            }
            let observations = (request.results as? [VNRecognizedTextObservation] ?? []).sorted { left, right in
                let leftTop = 1 - left.boundingBox.maxY
                let rightTop = 1 - right.boundingBox.maxY
                if abs(leftTop - rightTop) > 0.02 { return leftTop < rightTop }
                return left.boundingBox.minX < right.boundingBox.minX
            }
            var lines: [[String: Any]] = []
            for observation in observations {
                guard let candidate = observation.topCandidates(1).first else { continue }
                let text = HotkeyParser.normalizeOcrText(candidate.string)
                if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { continue }
                let box = observation.boundingBox
                lines.append([
                    "text": text,
                    "left": Double(box.minX) * Double(image.width),
                    "top": (1 - Double(box.maxY)) * Double(image.height),
                    "width": Double(box.width) * Double(image.width),
                    "height": Double(box.height) * Double(image.height)
                ])
            }
            let elapsed = (CFAbsoluteTimeGetCurrent() - started) * 1000
            let text = lines.compactMap { $0["text"] as? String }.joined(separator: "\n")
            let payload: [String: Any] = [
                "status": lines.isEmpty ? "empty" : "ok",
                "text": text,
                "lines": lines,
                "language": "zh-Hans + en-US",
                "elapsed_ms": (elapsed * 10).rounded() / 10,
                "message": lines.isEmpty ? "未在选区中识别到文字，请放大选区或提高清晰度。" : "已识别 \(lines.count) 行文本",
                "width": image.width,
                "height": image.height
            ]
            DispatchQueue.main.async { self.deliverOcr(payload) }
        }
    }

    func deliverOcrFailure(_ message: String) {
        deliverOcr([
            "status": "error",
            "text": "",
            "lines": [],
            "language": "zh-Hans + en-US",
            "elapsed_ms": 0,
            "message": message,
            "width": 0,
            "height": 0
        ])
    }

    func deliverOcr(_ payload: [String: Any]) {
        showMainWindowAction()
        let json = HotkeyParser.jsonString(payload)
        webView.evaluateJavaScript(
            "window.switchTab && window.switchTab('ocr'); window.receiveOcrResult && window.receiveOcrResult(\(json))",
            completionHandler: nil
        )
    }

    // MARK: - Status bar actions

    @objc func handleStatusBarClick(_ sender: NSStatusBarButton) {
        guard let event = NSApp.currentEvent else {
            togglePopoverAction()
            return
        }
        if event.type == .rightMouseUp || event.modifierFlags.contains(.control) {
            if popover.isShown {
                popover.performClose(sender)
            }
            statusItem.menu = statusMenu
            statusItem.button?.performClick(nil)
            statusItem.menu = nil
        } else {
            togglePopoverAction()
        }
    }

    @objc func togglePopoverAction() {
        guard let button = statusItem.button else { return }
        if popover.isShown {
            popover.performClose(button)
        } else {
            resultPanel?.orderOut(nil)
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            NSApp.activate(ignoringOtherApps: true)
            popoverWebView.evaluateJavaScript("if(window.focusMiniInput) window.focusMiniInput();", completionHandler: nil)
        }
    }

    @objc func openPopoverExplicit() {
        guard let button = statusItem.button else { return }
        if !popover.isShown {
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            NSApp.activate(ignoringOtherApps: true)
        }
    }

    @objc func showMainWindowAction() {
        if popover.isShown {
            popover.performClose(nil)
        }
        resultPanel?.orderOut(nil)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        webView.evaluateJavaScript("if(window.onRestoreFromTray) window.onRestoreFromTray();", completionHandler: nil)
    }

    @objc func hideMainWindowToTray() {
        window.orderOut(nil)
        resultPanel?.orderOut(nil)
    }

    @objc func toggleScreenSelectionAction() {
        screenSelectionEnabled.toggle()
        menuSelectionItem.state = screenSelectionEnabled ? .on : .off
        syncFeatureFlag("screen_selection_enabled", value: screenSelectionEnabled)
    }

    @objc func toggleClipboardCaptureAction() {
        clipboardCaptureEnabled.toggle()
        menuClipboardItem.state = clipboardCaptureEnabled ? .on : .off
        if clipboardCaptureEnabled {
            lastClipboardChange = NSPasteboard.general.changeCount
        }
        syncFeatureFlag("clipboard_capture_enabled", value: clipboardCaptureEnabled)
    }

    @objc func translateClipboardAction() {
        guard let text = NSPasteboard.general.string(forType: .string)?.trimmingCharacters(in: .whitespacesAndNewlines),
              !text.isEmpty else {
            NSSound.beep()
            return
        }
        showResult(text: String(text.prefix(5000)), source: "clipboard", app: "剪贴板", method: "clipboard")
    }

    @objc func togglePrivacyModeAction() {
        privacyModeEnabled.toggle()
        menuPrivacyItem.state = privacyModeEnabled ? .on : .off
        syncFeatureFlag("privacy_mode", value: privacyModeEnabled)
    }

    @objc func openOcrTabAction() {
        showMainWindowAction()
        webView.evaluateJavaScript("if(window.switchTab) window.switchTab('ocr');", completionHandler: nil)
    }

    @objc func openSettingsTabAction() {
        showMainWindowAction()
        webView.evaluateJavaScript("if(window.switchTab) window.switchTab('settings');", completionHandler: nil)
    }

    func syncFeatureFlag(_ key: String, value: Bool) {
        let js = "window.syncTrayFlag && window.syncTrayFlag('\(key)', \(value ? "true" : "false"))"
        webView.evaluateJavaScript(js, completionHandler: nil)
        popoverWebView.evaluateJavaScript(js, completionHandler: nil)
        resultWebView.evaluateJavaScript(js, completionHandler: nil)
    }

    @objc func explicitQuitAction() {
        isExplicitQuit = true
        NSApp.terminate(nil)
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if closeToTray && !isExplicitQuit {
            sender.orderOut(nil)
            return false
        }
        explicitQuitAction()
        return false
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return false
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag {
            showMainWindowAction()
        }
        return true
    }

    // MARK: - WebView messages

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any],
              let action = body["action"] as? String else { return }

        switch action {
        case "hideToTray":
            window.orderOut(nil)
            resultPanel?.orderOut(nil)
        case "showMainWindow":
            smokeNavigationMessages += 1
            showMainWindowAction()
            if let tab = body["tab"] as? String {
                let allowedTabs = ["dictionary", "translate", "ocr", "wordbook", "history", "models", "settings"]
                if allowedTabs.contains(tab) {
                    webView.evaluateJavaScript("if(window.switchTab) window.switchTab('\(tab)');", completionHandler: nil)
                }
            }
        case "captureSelection":
            captureSelectionAction()
        case "captureOcr":
            startOcrCaptureAction()
        case "translateClipboard":
            translateClipboardAction()
        case "openWord":
            if let text = body["text"] as? String {
                showMainWindowAction()
                webView.evaluateJavaScript("window.quickSelectWord && window.quickSelectWord(\(HotkeyParser.jsonString(text)))", completionHandler: nil)
            }
        case "openTranslate":
            if let text = body["text"] as? String {
                showMainWindowAction()
                let js = "document.getElementById('transStudioInput').value = \(HotkeyParser.jsonString(text)); window.switchTab && window.switchTab('translate')"
                webView.evaluateJavaScript(js, completionHandler: nil)
            }
        case "toggleMiniPopover":
            togglePopoverAction()
        case "closeMiniPopover":
            if let view = message.webView, view === resultWebView {
                resultPanel?.orderOut(nil)
            } else {
                popover.performClose(nil)
            }
        case "setCloseToTray":
            if let enabled = body["enabled"] as? Bool {
                closeToTray = enabled
            }
        case "setTheme":
            if let dark = body["dark"] as? Bool {
                let appearanceName: NSAppearance.Name = dark ? .darkAqua : .aqua
                NSApp.appearance = NSAppearance(named: appearanceName)
            }
        case "updateHotkeys":
            let lookup = (body["hotkey_lookup_mac"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? lookupHotkey
            let ocr = (body["hotkey_ocr_mac"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? ocrHotkey
            let main = (body["hotkey_main_mac"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? mainHotkey
            registerHotkeys(lookup: lookup, ocr: ocr, main: main)
        case "syncState":
            if let selected = body["screen_selection_enabled"] as? Bool {
                screenSelectionEnabled = selected
                menuSelectionItem.state = selected ? .on : .off
            }
            if let clipboard = body["clipboard_capture_enabled"] as? Bool {
                clipboardCaptureEnabled = clipboard
                menuClipboardItem.state = clipboard ? .on : .off
                if clipboard { lastClipboardChange = NSPasteboard.general.changeCount }
            }
            if let fallback = body["clipboard_fallback_enabled"] as? Bool {
                clipboardFallbackEnabled = fallback
            }
            if let privacy = body["privacy_mode"] as? Bool {
                privacyModeEnabled = privacy
                menuPrivacyItem.state = privacy ? .on : .off
            }
        case "quitApp":
            explicitQuitAction()
        default:
            break
        }
    }

    // MARK: - Permissions / notifications

    func showPermissionAlert(title: String, message: String, settingsURL: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message
        alert.addButton(withTitle: "打开系统设置")
        alert.addButton(withTitle: "稍后")
        let response = alert.runModal()
        if response == .alertFirstButtonReturn, let url = URL(string: settingsURL) {
            NSWorkspace.shared.open(url)
        }
    }

    func notify(title: String, message: String) {
        let notification = NSUserNotification()
        notification.title = title
        notification.informativeText = message
        notification.soundName = nil
        NSUserNotificationCenter.default.deliver(notification)
    }

    // MARK: - Backend / navigation

    func startBackendDaemon() {
        guard let resourcePath = Bundle.main.resourcePath else { return }
        let bundledDataDir = (resourcePath as NSString).appendingPathComponent("app/data")

        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let userDir = ProcessInfo.processInfo.environment["AIDICT_USER_DATA_DIR"].map { URL(fileURLWithPath: $0) }
            ?? appSupport.appendingPathComponent("AIDictionary", isDirectory: true)
        try? FileManager.default.createDirectory(at: userDir, withIntermediateDirectories: true)

        let bundledUserDb = URL(fileURLWithPath: bundledDataDir).appendingPathComponent("user_data.db")
        let writableUserDb = userDir.appendingPathComponent("user_data.db")
        if !FileManager.default.fileExists(atPath: writableUserDb.path) {
            try? FileManager.default.copyItem(at: bundledUserDb, to: writableUserDb)
        }

        let writableDictionary = userDir.appendingPathComponent("dictionary.db")
        if !FileManager.default.fileExists(atPath: writableDictionary.path) {
            try? FileManager.default.copyItem(at: URL(fileURLWithPath: bundledDataDir).appendingPathComponent("dictionary.db"), to: writableDictionary)
        }
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: (resourcePath as NSString).appendingPathComponent("app/backend/AIDictionaryServer"))
        proc.arguments = ["--port", String(serverPort)]
        var env = ProcessInfo.processInfo.environment
        env["PORT"] = String(serverPort)
        env["AIDICT_DATA_DIR"] = userDir.path
        env["AIDICT_APP_ROOT"] = (resourcePath as NSString).appendingPathComponent("app")
        env["AIDICT_NATIVE_BRIDGE"] = (bundledDataDir as NSString).appendingPathComponent("macos_native_bridge")
        env["AIDICT_USER_DATA_DIR"] = userDir.path
        proc.environment = env
        do { try proc.run() } catch {
            let alert = NSAlert()
            alert.messageText = "AI Dictionary 后端启动失败"
            alert.informativeText = error.localizedDescription
            alert.runModal()
            NSApp.terminate(nil)
        }
        self.serverProcess = proc
    }

    func waitForServerAndLoad(retries: Int) {
        let mainUrl = URL(string: "http://127.0.0.1:\(serverPort)/")!
        let trayUrl = URL(string: "http://127.0.0.1:\(serverPort)/?mode=tray")!
        let task = URLSession.shared.dataTask(with: mainUrl) { _, response, _ in
            if let httpResp = response as? HTTPURLResponse, httpResp.statusCode == 200 {
                DispatchQueue.main.async {
                    self.webView.load(URLRequest(url: mainUrl))
                    self.popoverWebView.load(URLRequest(url: trayUrl))
                    self.resultWebView.load(URLRequest(url: trayUrl))
                }
            } else if retries == 0 {
                DispatchQueue.main.async {
                    let alert = NSAlert()
                    alert.messageText = "无法连接本地词典服务"
                    alert.informativeText = "请检查是否已经打开另一份 AI Dictionary，关闭后重试。"
                    alert.runModal()
                    NSApp.terminate(nil)
                }
            } else if retries > 0 {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.12) {
                    self.waitForServerAndLoad(retries: retries - 1)
                }
            }
        }
        task.resume()
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let proc = serverProcess, proc.isRunning {
            proc.terminate()
        }
        for ref in hotKeyRefs {
            if let ref = ref { UnregisterEventHotKey(ref) }
        }
        if let handler = hotKeyHandler {
            RemoveEventHandler(handler)
        }
        clipboardTimer?.invalidate()
    }

    // Exercise the real WKWebView -> native -> WKWebView navigation path in CI.
    func webView(_ view: WKWebView, didFinish navigation: WKNavigation!) {
        if view === resultWebView {
            resultReady = true
            if pendingResult != nil { injectPendingResult() }
            return
        }
        guard smokeTest, view === webView else { return }
        view.evaluateJavaScript("restoreMainWindowFromTray('models')", completionHandler: nil)
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            view.evaluateJavaScript("document.getElementById('page-models').classList.contains('active')") { result, error in
                if error == nil, result as? Bool == true, self.smokeNavigationMessages == 1 {
                    print("AIDICT_NATIVE_SMOKE_PASS")
                } else {
                    print("AIDICT_NATIVE_SMOKE_FAIL: messages=\(self.smokeNavigationMessages), error=\(String(describing: error))")
                }
                self.explicitQuitAction()
            }
        }
    }
}

enum HotkeyParser {
    struct Parsed {
        let keyCode: UInt32
        let modifiers: UInt32
    }

    private static let keyCodes: [String: Int] = [
        "a": kVK_ANSI_A, "s": kVK_ANSI_S, "d": kVK_ANSI_D, "f": kVK_ANSI_F,
        "h": kVK_ANSI_H, "g": kVK_ANSI_G, "z": kVK_ANSI_Z, "x": kVK_ANSI_X,
        "c": kVK_ANSI_C, "v": kVK_ANSI_V, "b": kVK_ANSI_B, "q": kVK_ANSI_Q,
        "w": kVK_ANSI_W, "e": kVK_ANSI_E, "r": kVK_ANSI_R, "y": kVK_ANSI_Y,
        "t": kVK_ANSI_T, "1": kVK_ANSI_1, "2": kVK_ANSI_2, "3": kVK_ANSI_3,
        "4": kVK_ANSI_4, "6": kVK_ANSI_6, "5": kVK_ANSI_5, "9": kVK_ANSI_9,
        "7": kVK_ANSI_7, "8": kVK_ANSI_8, "0": kVK_ANSI_0, "o": kVK_ANSI_O,
        "u": kVK_ANSI_U, "i": kVK_ANSI_I, "p": kVK_ANSI_P, "l": kVK_ANSI_L,
        "j": kVK_ANSI_J, "k": kVK_ANSI_K, "n": kVK_ANSI_N, "m": kVK_ANSI_M,
        "space": kVK_Space, "esc": kVK_Escape, "escape": kVK_Escape,
        "return": kVK_Return, "enter": kVK_Return, "tab": kVK_Tab,
        "f1": kVK_F1, "f2": kVK_F2, "f3": kVK_F3, "f4": kVK_F4,
        "f5": kVK_F5, "f6": kVK_F6, "f7": kVK_F7, "f8": kVK_F8,
        "f9": kVK_F9, "f10": kVK_F10, "f11": kVK_F11, "f12": kVK_F12
    ]

    static func parse(_ text: String) -> Parsed? {
        let parts = text.split(separator: "+").map {
            $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        }
        guard parts.count >= 2, let keyName = parts.last, let keyCode = keyCodes[keyName] else { return nil }
        var modifiers: UInt32 = 0
        for token in parts.dropLast() {
            switch token {
            case "option", "alt":
                modifiers |= UInt32(optionKey)
            case "command", "cmd":
                modifiers |= UInt32(cmdKey)
            case "control", "ctrl":
                modifiers |= UInt32(controlKey)
            case "shift":
                modifiers |= UInt32(shiftKey)
            default:
                return nil
            }
        }
        guard modifiers != 0 else { return nil }
        return Parsed(keyCode: UInt32(keyCode), modifiers: modifiers)
    }

    static func jsonString(_ value: Any) -> String {
        guard let data = try? JSONSerialization.data(withJSONObject: [value], options: []),
              let text = String(data: data, encoding: .utf8) else { return "null" }
        return String(text.dropFirst().dropLast())
    }

    static func normalizeOcrText(_ text: String) -> String {
        var result = text
        let patterns = [
            "(?<=[\\u4e00-\\u9fff])\\s+(?=[\\u4e00-\\u9fff，。！？；：、（）《》“”‘’])",
            "(?<=[，。！？；：、（）《》“”‘’])\\s+(?=[\\u4e00-\\u9fff])"
        ]
        for pattern in patterns {
            result = result.replacingOccurrences(of: pattern, with: "", options: .regularExpression)
        }
        return result
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
