# Windows 界面与字体修复：1.0.2

## 判断与方案

用户截图中的白色顶部是原生 WinForms 标题栏，不是网页菜单。旧代码仅设置网页背景，未设置 DWM 深色标题栏。原生托盘菜单也未提供暗色渲染器。

字体模糊的主要可验证风险是 PowerShell / WinForms 宿主缺少明确的 UI 线程 DPI 感知，导致系统可能放大已绘制的位图。截图本身不能排除远程桌面、显示器、ClearType 或兼容性设置的影响；本次先修正应用自身的 DPI 路径，而非用 CSS 字重掩盖问题。

参考官方最佳实践：

- [Microsoft：High DPI Desktop Application Development](https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-desktop-application-development-on-windows)：Per-Monitor V2、非客户区缩放与窗口 DPI 变化。
- [Microsoft：Support Dark and Light themes in Win32 apps](https://learn.microsoft.com/windows/apps/desktop/modernize/apply-windows-themes)：整个应用表面应匹配主题，使用 DWM 标题栏属性。
- [Microsoft：Typography in Windows](https://learn.microsoft.com/windows/apps/design/signature-experiences/typography)：一致的系统字体、字号与视觉层级。

## 实施

1. 在创建任何 WinForms / WebView2 窗口前，给实际 UI 线程设置 Per-Monitor V2。独立 launcher 的设置不会自动传递给 PowerShell 子进程，因此修复放在真实宿主内。
2. 使用 DPI 感知窗口类设置初始物理尺寸，并处理 WM_DPICHANGED 建议矩形；WebView2 继续使用原生设备像素比例，不进行 CSS 缩放或文本平滑强制覆盖。
3. DWM 标题栏及文字颜色随应用主题同步，保留系统的关闭、最小化、最大化操作。托盘菜单使用对应的深浅色颜色表。
4. 网页显式设置 color-scheme，使滚动条、下拉选择与复选框匹配主题。主题同时保存在网页存储和宿主用户目录，并同步主窗口与迷你窗口。
5. 移除可见的模拟系统信息栏、调试式按钮与导航编号。使用线性图标、低饱和蓝色选中态、一致的圆角与间距。
6. Windows 字体栈优先 Segoe UI Variable Text / Segoe UI，中文使用 Microsoft YaHei UI。提高弱文本对比度，补充键盘 focus-visible。
7. 重新设计搜索、词条和未收录空状态；词形字段使用中文名称；不再在未找到词时把尚未接入的 AI 翻译作为主操作。
8. 尚未实现的翻译、OCR 与全局取词明确标记为开发中，移除误导性的可执行外观。保留底层接口及现有回归覆盖。

## 验证

- 原有 8 组回归测试通过。
- `python scripts/test_desktop_ui.py`：Chromium / WebKit，设备像素比例 1 / 1.25 / 1.5 / 2，800 / 1120 CSS 像素宽度，六个页面横向溢出检查通过；深浅色主题、存储恢复及空状态通过。
- Windows 原生运行实测：窗口 DPI = 144，UI 线程 Per-Monitor V2 = true，WebView2 devicePixelRatio = 1.5。
- 调用 DwmGetWindowAttribute 实测标题栏暗色属性随主题在 0 / 1 间变化；托盘菜单背景在白色与深色间变化；两个 WebView 同步。
- 浏览器缩放模拟不能代替真实多显示器移动、所有 Windows 版本与显示器组合的测试。这些组合仍需实际设备复测。

交付：`dist/installers/AI-Dictionary-1.0.2-Windows-x64-Setup.exe`，保留旧 1.0.1 包。安装机制沿用已验证的 NSIS 安装/卸载流程，新增原生外观辅助代码随包交付。当前安装包仍未数字签名。
