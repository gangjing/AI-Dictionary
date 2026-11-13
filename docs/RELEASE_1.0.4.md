# AI Dictionary 1.0.4 — 功能补齐、构建与验证记录

**日期：** 2026-11-13  
**目标：** 补齐 1.0.1/1.0.2 中尚未实现的系统能力，并保持 Windows 与 macOS 功能一致。  
**结论：** Windows 1.0.4 已完成构建、安装和原生自测；macOS 同构实现已完成代码，但当前开发环境为 Windows，未执行 `swiftc` 编译与真机权限测试。

---

## 1. 本轮新增/修复

### 1.1 全局划词（Windows UIA / macOS AX）

- Windows 新增 `scripts/windows_native.cs`：
  - `AutomationElement.FocusedElement` + `TextPattern.GetSelection()` 读取选中文本，支持向上查找父级 TextPattern。
  - `AutomationElement.IsPasswordProperty` + 安全输入框判断，命中后返回 `blocked_secure_input`，**不会**触发复制回退。
  - UIA 失败时使用受控 `Ctrl+C` 回退：备份剪贴板全部格式 → 发送复制 → 轮询变化 → 读取文本 → 恢复剪贴板。
  - 读取失败/密码框/无选区分别给出明确提示。
- macOS 在 `scripts/macos_app_shell.swift` 中实现同构逻辑：
  - `AXUIElementCreateSystemWide` → `kAXFocusedUIElementAttribute` → `kAXSelectedTextAttribute`。
  - `AXSecureTextField` / `IsSecureEventInputEnabled()` 双重保护。
  - `CGEvent` 发送 `Command+C`，`NSPasteboard` 备份与恢复。
  - 首次使用引导到「辅助功能」授权；不再假装已读取。

### 1.2 全局热键

- Windows：`RegisterHotKey`（`HotkeyWindow`），默认 `Ctrl+Alt+T` 划词、`Ctrl+Alt+S` 截图 OCR、`Ctrl+Alt+D` 主窗口。
- macOS：Carbon `RegisterEventHotKey`，默认 `Option+Command+T/S/D`。
- 设置页可修改，保存后立即重新注册；Windows 注册失败会弹出冲突提示。

### 1.3 剪贴板取词

- Windows：`ClipboardWatcher` 450 ms 轮询 `Clipboard`，启用时先同步当前内容，避免打开功能就弹出旧剪贴板；复制发生在主窗口/迷你窗内时跳过。
- macOS：`NSPasteboard.changeCount` 定时轮询，同样的“启用即同步”和自身窗口过滤。
- 入口：托盘菜单「剪贴板自动取词」「翻译剪贴板内容」，设置页开关。

### 1.4 区域截图 OCR

- Windows：
  - 全屏半透明选区层（`RegionSelector`，支持多屏虚拟桌面、Esc 取消、尺寸提示）。
  - `ScreenCapture.Capture` 抓取物理像素区域。
  - `scripts/windows_ocr.ps1` 通过 `Windows.Media.Ocr` 在内存中识别，中文引擎 + 拉丁字符混排，自动去除中文字间空格。
  - 识别结果进入主窗口「截图识别」页，逐行可编辑、复制、送入翻译。
- macOS：
  - 全屏 `OcrOverlayWindow` + `OcrSelectionView` 拖选。
  - `CGWindowListCreateImage` 抓取，`Vision VNRecognizeTextRequest`（zh-Hans + en-US）识别。
  - 结果注入同一 OCR 页面。
- 两端都在内存中处理，不写临时图片；屏幕录制/辅助功能权限被拒绝时给出系统设置入口。

### 1.5 真实 Hy-MT2 翻译

- 后端新增 provider 架构：
  - `llama`：自动启动/复用 loopback `llama-server`（`127.0.0.1` + 随机端口 + `--no-webui`），使用 `/v1/chat/completions`。
  - `openai`：任意 OpenAI 兼容本地服务（Ollama / LM Studio / vLLM），可配置 endpoint、model、API key。
  - `auto`：优先已配置的本地 OpenAI 服务，其次 Hy-MT2。
- 真实模型验证：
  - `Hy-MT2-1.8B-Q4_K_M.gguf`（1,133,080,448 字节，SHA256 `dc5f44...6699`）。
  - 输入 `The quick brown fox jumps over the lazy dog. Local translation protects sensitive documents.`
  - 输出 `敏捷的棕色狐狸跳过了懒狗。本地翻译保护敏感文件。`
  - 首次加载模型约 7 秒，已加载后约 3 秒（本机 CPU）。
  - 真实模型 token 保护验证：`` `tauri.conf.json` ``、`{user_name}`、`https://example.com` 三个 token 原样保留，`protected_tokens_verified = true`。
- 保留并强化：
  - 请求抢占/取消、长文分段、`preserve_format` token 保护、术语表、私密模式、历史记录。
  - 无引擎时返回 `engine_unavailable` 和可操作提示，绝不返回伪造译文。

### 1.6 模型管理

- 内置 4 个 Hy-MT2 量化档位，真实 HF 文件大小与 SHA256。
- `POST /api/models/download` 后台下载：
  - `.part` 断点续传（HTTP Range）
  - 进度查询 `/api/models/download/status`
  - 完成后 SHA256 校验、原子替换、启用
  - 磁盘空间预检、校验失败删除损坏文件
- 安装包不内置模型，首次使用按需下载；`llama.cpp` CPU 运行时随包分发（Windows x64 / macOS arm64 / x64）。

### 1.7 交互与界面

- 移除 `nav-pending`「开发中」标记与隐藏翻译/OCR 卡片的旧 CSS。
- 迷你查词窗显示来源（划词/剪贴板/来源应用），支持发音、收藏、在词典中打开、复制、在翻译页继续。
- OCR 页显示识别状态、耗时、引擎语言、选区尺寸；结果逐行可编辑。
- 翻译页显示引擎状态、模式/地址/模型配置、测试连接。
- 设置页：划词/剪贴板/复制回退开关，三组热键，引擎配置。
- 模型卡片显示下载进度、文件缺失状态、许可证与路径。
- 生词本新增「开始复习」卡片（按到期时间抽词，认识/模糊/不认识三档评分）与 JSON 文件导入。

### 1.8 修复：从托盘恢复时迷你弹窗越界

- 根因：`Get-MiniPosition` 使用硬编码的 `440x560` 逻辑尺寸，在 125%/150%/200% DPI 下真实窗口可到 `667x866`；靠近屏幕右下角恢复时只按 560 高度夹取，弹窗底部被任务栏/屏幕裁掉。
- 修复：
  - 定位前强制创建窗口句柄，读取 DPI 缩放后的真实 `Width/Height`；
  - 空间不足时自动翻转到光标左上方；
  - 按当前显示器 `WorkingArea` 四边夹取；
  - 使用 `SetWindowPos(HWND_TOPMOST, SWP_NOACTIVATE)` 把迷你窗抬到主窗口之上，但不抢键盘焦点；
  - 主窗口隐藏到托盘时同时隐藏迷你窗，恢复主窗口时确保迷你窗关闭；
  - 托盘单击延迟 260 ms，双击只恢复主窗口，避免“单击开迷你窗 + 双击恢复主窗口”互相打架。
- 自测新增边界断言：`miniBounds=667x866@...` 且必须完全落在工作区内；恢复主窗口后迷你窗必须不可见。

### 1.9 翻译速度优化（Q6_K）

实测环境：i7-1165G7（4 核 8 线程），Hy-MT2-1.8B Q6_K，Windows 安装版。

| 项目 | 优化前 | 优化后 |
|---|---|---|
| llama-server 线程 | `-t 7`（逻辑线程，超订） | `-t 4 -tb 4`（物理核心） |
| 上下文 | 4096 | 3072 |
| 批处理 | 默认 2048/512 | `-b 512 -ub 512` |
| 注意力 / 加载 | 默认 | `-fa on` + `-lm mlock`（<3GB 模型） |
| 并发槽 | 默认 | `-np 1` |
| 短句翻译（已加载） | 约 2.2 s | 约 0.63 s（Q6）/ 约 0.38–0.46 s（Q4） |
| 首次加载 | 等待首次请求冷启动 | 「预加载模型」按钮，2–15 s 后台完成 |

- Q4_K_M 实测比 Q6_K 快约 1.5–2 倍，模型卡片已标注「推荐 · 最快」；Q6_K 标注「质量优先 · 较慢」。
- 翻译页新增「预加载模型」按钮，加载后 badge 显示「模型已加载」，后续翻译无需冷启动。
- 注意：以上为单机实测，不同 CPU/内存/是否首次读盘会有差异。

---

## 2. 自动化验证

### 2.1 后端 + 浏览器

```bash
python scripts/test_regressions.py
python scripts/test_desktop_ui.py
python scripts/verify_acceptance.py
```

结果：

- `test_regressions.py`：10 项通过，包含新增的 model download SHA256、mock OpenAI 翻译、token 保护、浏览器划词/OCR 接收。
- `test_desktop_ui.py`：Chromium + WebKit，DPR 1/1.25/1.5/2，800/1120 px，六页面无横向溢出，深浅色持久化。
- `verify_acceptance.py`：16 项通过；Windows 上原生 selection/OCR 项按设计 SKIP，由 Windows 自测覆盖。

### 2.2 Windows 安装版原生自测

安装 `AI-Dictionary-1.0.4-Windows-x64-Setup.exe` 后执行：

```powershell
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass `
  -File "$env:LOCALAPPDATA\Programs\AI Dictionary\app\scripts\windows_tray_shell.ps1" --self-test
```

结果文件 `%TEMP%\aidict-selftest-result.txt`：

```
PASS miniBounds=667x866@..., selection=[quick brown fox jumps over the lazy dog. Native selection self test.];
clipboard(watcher) matched=True; secure=blocked_secure_input;
screenOcr=ok matched=True; ocrStatus=ok ocrLines=1; ocrRendered=1
```

覆盖：托盘右下角弹窗边界 → 恢复主窗口关闭迷你窗 → 真实 WebView2 窗口 → UIA 划词 → 迷你窗 `receiveSelection` → 剪贴板监听 → 密码框拦截 → 屏幕截图 OCR → OCR 页面注入。

### 2.3 安装版 + 内置 llama.cpp + 真实模型

- 安装目录 `%LOCALAPPDATA%\Programs\AI Dictionary\app\llama\llama-server.exe` 启动成功。
- 真实翻译返回：
  - `本地翻译保护敏感的企业文档。`
  - Q6_K：优化后首句约 1.37s，常驻后约 0.63s；Q4_K_M 约 0.38–0.46s。
- 说明安装包内 llama 运行时、模型路径解析、翻译 provider 链路均可用。

---

## 3. macOS 一致性与未验证项

macOS 端已实现对应代码路径：

| Windows | macOS |
|---|---|
| `SelectionReader`（UIA + clipboard） | `captureSelectionAction` / `clipboardFallback`（AX + NSPasteboard） |
| `HotkeyWindow`（RegisterHotKey） | `registerHotkeys`（Carbon RegisterEventHotKey） |
| `ClipboardWatcher` | `pollClipboard`（NSPasteboard.changeCount） |
| `RegionSelector` + WinRT OCR | `OcrOverlayWindow` + Vision |
| `Show-MiniForText` → WebView2 JS | `showResult` → 非激活 `NSPanel` WKWebView |
| 托盘菜单/关闭到托盘 | `NSStatusItem` / `NSPopover` / 关闭 `orderOut` |

**未验证：**

- 当前环境是 Windows，无法执行 `swiftc`。macOS 代码只做了静态审阅与 tree-sitter 语法扫描（唯一报错为 `@_silgen_name` 外部函数声明，属于解析器限制）。
- 未在 macOS 13/14/15 真机验证辅助功能授权、屏幕录制授权、多屏坐标、菜单栏弹窗定位。
- macOS 安装包仍需在 macOS 构建机运行 `build_installers.py --platform macos` 与 CI smoke test。

---

## 4. 已知限制

1. 安装包未签名；Windows SmartScreen、macOS Gatekeeper 会提示。
2. 模型需首次联网下载约 1.1 GB；下载源为 Hugging Face，失败可续传。
3. OCR 对低分辨率、竖排、手写、复杂版式仍可能出错；结果可编辑后再翻译。
4. 全局热键使用固定组合，暂未做系统级冲突检测（Windows 注册失败会提示，macOS 需实测）。
5. 翻译为请求-响应模式，暂未逐 token 流式渲染；长文按段处理。
6. 部分 Electron/PDF/远程桌面/管理员权限窗口无法通过 UIA/AX 取词，会自动回退到复制；安全输入框始终拒绝。终端窗口不执行自动复制回退，避免 `Ctrl+C` / `Command+C` 中断命令。
7. 早期 `src-tauri/` Rust 原型与 `design/` 设计稿已从仓库移除，避免与当前 Python + 原生壳架构混淆。

---

## 5. 构建产物

| 文件 | 字节 | SHA256 |
|---|---|---|
| `AI-Dictionary-1.0.4-Windows-x64-Setup.exe` | 27,535,507 | `6edcc7b6966efb1f6aac23d52c12a301003e2efe2a5b39cef5688adb45cf4aa5` |
| `AI-Dictionary-1.0.4-Windows-x64-Setup.zip` | 40,501,499 | `2742288389ab844e9ab69b2d3bde614744530a2aff727b733e4d4af5cc7eb297` |

> 最终重建后以 `dist/installers/SHA256SUMS.txt` 为准。
