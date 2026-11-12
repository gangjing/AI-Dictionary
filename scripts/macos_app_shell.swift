import Cocoa
import WebKit

class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var webView: WKWebView!
    var statusItem: NSStatusItem!
    var popover: NSPopover!
    var popoverWebView: WKWebView!
    var statusMenu: NSMenu!

    var menuSelectionItem: NSMenuItem!
    var menuClipboardItem: NSMenuItem!
    var menuPrivacyItem: NSMenuItem!

    var serverProcess: Process?
    let serverPort = 14205

    var closeToTray: Bool = true
    var isExplicitQuit: Bool = false
    var screenSelectionEnabled: Bool = true
    var clipboardCaptureEnabled: Bool = false
    var privacyModeEnabled: Bool = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        startBackendDaemon()
        setupMainMenu()
        setupMainWindow()
        setupYoudaoStyleStatusBar()
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
        webView.autoresizingMask = [.width, .height]
        window.contentView?.addSubview(webView)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func setupYoudaoStyleStatusBar() {
        // Create macOS Top Menu Bar Status Item (Youdao Dictionary Style)
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.title = "📖 AI词典"
            button.toolTip = "AI 词典 (常驻信息栏)\n• 左键点击：弹出有道式迷你查词小窗\n• 右键点击：打开快捷开关与退出菜单"
            button.target = self
            button.action = #selector(handleStatusBarClick(_:))
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        }

        // Create Youdao-style Menu Bar Mini Lookup Popover
        popover = NSPopover()
        popover.contentSize = NSSize(width: 390, height: 500)
        popover.behavior = .transient
        popover.animates = false

        let popVC = NSViewController()
        let popConfig = WKWebViewConfiguration()
        popConfig.userContentController.add(self, name: "nativeShell")
        popoverWebView = WKWebView(frame: NSRect(x: 0, y: 0, width: 390, height: 500), configuration: popConfig)
        popVC.view = popoverWebView
        popover.contentViewController = popVC

        // Create Right-Click Context Menu modeled after Youdao Dictionary
        statusMenu = NSMenu(title: "AI 词典")

        let miniItem = NSMenuItem(title: "🔍 打开迷你查词小窗 (Mini 查词栏)", action: #selector(openPopoverExplicit), keyEquivalent: "m")
        miniItem.target = self
        statusMenu.addItem(miniItem)

        let mainItem = NSMenuItem(title: "📖 显示 AI 词典主窗口", action: #selector(showMainWindowAction), keyEquivalent: "d")
        mainItem.target = self
        statusMenu.addItem(mainItem)

        statusMenu.addItem(NSMenuItem.separator())

        menuSelectionItem = NSMenuItem(title: "屏幕划词翻译 (Screen Capture)", action: #selector(toggleScreenSelectionAction), keyEquivalent: "")
        menuSelectionItem.target = self
        menuSelectionItem.state = screenSelectionEnabled ? .on : .off
        statusMenu.addItem(menuSelectionItem)

        menuClipboardItem = NSMenuItem(title: "剪贴板自动查词 (Clipboard Monitor)", action: #selector(toggleClipboardCaptureAction), keyEquivalent: "")
        menuClipboardItem.target = self
        menuClipboardItem.state = clipboardCaptureEnabled ? .on : .off
        statusMenu.addItem(menuClipboardItem)

        let ocrItem = NSMenuItem(title: "📸 区域截图 OCR 翻译", action: #selector(openOcrTabAction), keyEquivalent: "s")
        ocrItem.target = self
        statusMenu.addItem(ocrItem)

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
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        webView.evaluateJavaScript("if(window.onRestoreFromTray) window.onRestoreFromTray();", completionHandler: nil)
    }

    @objc func hideMainWindowToTray() {
        window.orderOut(nil)
    }

    @objc func toggleScreenSelectionAction() {
        screenSelectionEnabled.toggle()
        menuSelectionItem.state = screenSelectionEnabled ? .on : .off
        let js = "if(window.syncTrayFlag) window.syncTrayFlag('screen_selection_enabled', \(screenSelectionEnabled));"
        webView.evaluateJavaScript(js, completionHandler: nil)
        popoverWebView.evaluateJavaScript(js, completionHandler: nil)
    }

    @objc func toggleClipboardCaptureAction() {
        clipboardCaptureEnabled.toggle()
        menuClipboardItem.state = clipboardCaptureEnabled ? .on : .off
        let js = "if(window.syncTrayFlag) window.syncTrayFlag('clipboard_capture_enabled', \(clipboardCaptureEnabled));"
        webView.evaluateJavaScript(js, completionHandler: nil)
        popoverWebView.evaluateJavaScript(js, completionHandler: nil)
    }

    @objc func togglePrivacyModeAction() {
        privacyModeEnabled.toggle()
        menuPrivacyItem.state = privacyModeEnabled ? .on : .off
        let js = "if(window.syncTrayFlag) window.syncTrayFlag('privacy_mode', \(privacyModeEnabled));"
        webView.evaluateJavaScript(js, completionHandler: nil)
        popoverWebView.evaluateJavaScript(js, completionHandler: nil)
    }

    @objc func openOcrTabAction() {
        showMainWindowAction()
        webView.evaluateJavaScript("if(window.switchTab) window.switchTab('ocr');", completionHandler: nil)
    }

    @objc func openSettingsTabAction() {
        showMainWindowAction()
        webView.evaluateJavaScript("if(window.switchTab) window.switchTab('settings');", completionHandler: nil)
    }

    @objc func explicitQuitAction() {
        isExplicitQuit = true
        NSApp.terminate(nil)
    }

    // Intercept window close button (X): Hide to Menu Bar instead of quitting (Youdao Dictionary behavior)
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

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any],
              let action = body["action"] as? String else { return }

        switch action {
        case "hideToTray":
            window.orderOut(nil)
        case "showMainWindow":
            showMainWindowAction()
            if let tab = body["tab"] as? String {
                let allowedTabs = ["dictionary", "translate", "ocr", "wordbook", "history", "models", "settings"]
                if allowedTabs.contains(tab) {
                    webView.evaluateJavaScript("if(window.switchTab) window.switchTab('\(tab)');", completionHandler: nil)
                }
            }
        case "toggleMiniPopover":
            togglePopoverAction()
        case "closeMiniPopover":
            popover.performClose(nil)
        case "setCloseToTray":
            if let enabled = body["enabled"] as? Bool {
                closeToTray = enabled
            }
        case "syncState":
            if let sel = body["screen_selection_enabled"] as? Bool {
                screenSelectionEnabled = sel
                menuSelectionItem.state = sel ? .on : .off
            }
            if let clip = body["clipboard_capture_enabled"] as? Bool {
                clipboardCaptureEnabled = clip
                menuClipboardItem.state = clip ? .on : .off
            }
            if let priv = body["privacy_mode"] as? Bool {
                privacyModeEnabled = priv
                menuPrivacyItem.state = priv ? .on : .off
            }
        case "quitApp":
            explicitQuitAction()
        default:
            break
        }
    }

    func startBackendDaemon() {
        guard let resourcePath = Bundle.main.resourcePath else { return }
        let serverScript = (resourcePath as NSString).appendingPathComponent("app/scripts/run_local_server.py")
        let bundledDataDir = (resourcePath as NSString).appendingPathComponent("app/data")

        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let userDir = appSupport.appendingPathComponent("AIDictionary", isDirectory: true)
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
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
