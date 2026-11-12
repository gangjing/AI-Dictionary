# 1.0.1 代码检查与修复记录

## macOS 界面抖动根因

原始路径：`window.switchTab()` → `restoreMainWindowFromTray()` → `nativeShell.postMessage(showMainWindow)` → Swift `showMainWindowAction()` / `evaluateJavaScript(switchTab)` → 回到起点。

因此，从原生菜单进入设置/OCR，或者从迷你窗恢复主窗口，可能无限重复窗口激活、页面隐藏/显示以及模型、历史记录等请求。该问题是确定的代码循环；用户所报告的具体操作尚未提供，因此不能把所有肉眼可见的抖动都归因于它。

修复：原生回调只修改页面状态，禁止反向发送恢复窗口消息。保留用户点击时的一次原生请求。增加浏览器中的异步桥接回归测试，以及 macOS 安装包内实际 WKWebView 的 `--smoke-test`：只允许一次恢复消息，随后检查设置页可见并退出。迷你窗取消原生弹出动画，滚动容器预留滚动条空间。

## 已修复的问题

- 主查词、迷你查词、生词本请求的旧结果可能覆盖新结果；翻译取消后迟到结果仍写入界面。
- 主查词与迷你查词共用收藏对象，可能收藏错误的词；保存过程中再次查词导致提示串词。
- 查询、释义、例句、备注等直接插入 HTML / 内联 JavaScript，特殊字符导致页面损坏或脚本执行。
- Toast 定时器互相干扰；设置保存后未重新同步 UI；原生关闭行为未从持久化设置初始化。
- 空备注无法清除；重复导入同一词条留下旧 FTS 索引；中文查询中的双引号改变 FTS 查询语义。
- 复习日期被设为当前时刻，现按等级安排 1/2/4/7/15 天后的复习。
- Windows 启动时执行 macOS Mach-O 诊断程序而崩溃；服务忽略 `--port` 参数；畸形 JSON 断开请求。
- Windows 使用不支持当前页面语法的 IE WebBrowser；现使用 WebView2，并连接原生消息、托盘恢复、退出功能。
- 安装后依赖系统 Python；现将后端 Python 运行时一并打包。
- Windows 升级可能覆盖个人数据库；现将可变数据库保存在用户目录，安装包只含清理过的初始用户数据库。
- macOS 自定义词库写入 `.app` 内部，破坏签名或在只读卷失败；现将词库复制到用户支持目录后写入。
- macOS 关闭常驻功能后关闭窗口却不退出；缺少标准编辑菜单导致键盘剪切/复制/粘贴不可用。
- 构建脚本在 Windows 上调用 Swift/Cocoa；未安装的伪 Tauri 构建流水线；现按平台构建实际使用的原生壳。

## 验证方式

`python scripts/test_regressions.py` 使用临时数据库，不修改仓库数据或用户词本。包含后端回归和 Chromium/WebKit 的真实页面测试（原生回调循环、乱序返回、取消回写、收藏隔离、HTML 注入、多页面切换）。

Windows 已在本机启动打包后的 WebView2 壳，验证默认查词、设置页及原生退出。macOS CI 在生成 DMG/PKG 前运行真实 WKWebView 原生壳测试；以对应 Actions 作业成功为准。尚未在用户本人的 M1 / 当前 macOS 环境验证实际操作、显示缩放、多显示器和休眠唤醒。

## 尚未实现的功能，不能宣称已修复

1. `translate_rpc` 原本只是固定文本替换，不调用 Hy-MT2。模型“安装”只更改数据库状态，没有下载或 SHA256 校验。安装版现明确返回不可用，阻止伪译文及伪安装成功；演示实现仅在显式设置 `AIDICT_ENABLE_DEMO_TRANSLATION=1` 时允许。真实模型下载、推理、流式取消需要后续实现。
2. Swift OCR 识别的是程序绘制的测试图片，不是用户选区截图。界面现明确标注尚未实现。Windows OCR 也没有实现。
3. 屏幕划词、剪贴板监听和全局快捷键目前主要是设置/UI，未形成完整的系统监听流程。
4. `src-tauri` 是未接入发行包的原型模块：缺少入口、构建脚本和前端 npm 项目。其声明的功能不能当作已运行的产品功能；本次包仍使用 Swift / PowerShell + Python 架构。
5. macOS 包仅 ad-hoc 签名，没有 Apple Developer ID / notarization；Windows ZIP 也未签名。Windows 需要已安装的 WebView2 Runtime。不能宣称已完成正式签名发行。
6. 原版 `verify_acceptance.py` 依赖模拟数据和平台诊断，不能证明真实 AI 翻译、截图 OCR 或系统划词可用。本次不沿用其“全部验收通过”的结论。

本次为稳定性修复构建，不代表软件不存在其他 bug，也不是全部规划功能的完成版本。

## 构建与安装

- Windows：`python scripts/build_installers.py --platform windows`。
- Apple Silicon Mac：`python scripts/build_installers.py --platform macos --arch arm64`。
- Intel Mac：在 Intel Mac 上执行 `python scripts/build_installers.py --platform macos --arch x64`。
- 构建环境需 Python、PyInstaller；macOS 还需 Xcode Command Line Tools。运行时无需预装 Python。
- 新包版本为 1.0.1；旧 1.0.0 包保留，不作为本次修复结果。
- 用户数据：macOS `~/Library/Application Support/AIDictionary/`；Windows `%LOCALAPPDATA%\AIDictionary\`。升级和卸载程序不主动删除此目录。
