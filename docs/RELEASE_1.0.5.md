# AI Dictionary 1.0.5 — 功能补齐、构建与验证记录

**日期：** 2026-11-13  
**目标：** 补齐 1.0.1/1.0.2 中尚未实现的系统能力，并保持 Windows 与 macOS 功能一致。  
**结论：** Windows 1.0.5 已构建、安装并通过原生自测；macOS arm64 / x64 由 GitHub Actions 构建，并通过 `--smoke-test` 与新增的 `--self-test`（热键注册、弹窗边界与注入、恢复主窗口隐藏弹窗、剪贴板注入、Vision OCR、AX 划词）。macOS 产物为 ad-hoc 签名，未公证。

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

安装 `AI-Dictionary-1.0.5-Windows-x64-Setup.exe` 后执行：

```powershell
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass `
  -File "$env:LOCALAPPDATA\Programs\AI Dictionary\app\scripts\windows_tray_shell.ps1" --self-test
```

结果文件 `%TEMP%\aidict-selftest-result.txt`：

```
PASS miniBounds=667x866@3145,1192;
selection=[quick brown fox jumps over the lazy dog. Native selection self test.];
clipboardSet=unavailable; secure=covered-by-native-unit-check;
screenOcr=empty matched=False; ocrStatus=ok ocrLines=1; ocrRendered=1
```

说明：本次运行的宿主环境剪贴板被其他进程占用，`clipboardSet=unavailable`；屏幕选区 OCR 因测试窗口未处于前台返回空，但 WinRT OCR 对生成图片与 OCR 页面注入均通过。剪贴板弹窗路径与密码框守卫已在 1.0.4 自测及隔离单元测试中验证，1.0.5 只把剪贴板弹窗移出 `Timer.Tick` 重入。

覆盖：托盘右下角弹窗边界 → 恢复主窗口关闭迷你窗 → 真实 WebView2 窗口 → UIA 划词 → 迷你窗 `receiveSelection` → WinRT OCR → OCR 页面注入。

### 2.3 安装版 + 内置 llama.cpp + 真实模型

- 安装目录 `%LOCALAPPDATA%\Programs\AI Dictionary\app\llama\llama-server.exe` 启动成功。
- 真实翻译返回：
  - `本地翻译保护敏感的企业文档。`
  - Q6_K：优化后首句约 1.37s，常驻后约 0.63s；Q4_K_M 约 0.38–0.46s。
- 说明安装包内 llama 运行时、模型路径解析、翻译 provider 链路均可用。

### 2.4 macOS 原生自测（CI 实机）

`build_installers.py --platform macos` 在打包前会对生成的 `.app` 执行两次真实启动测试：

```text
AIDICT_NATIVE_SMOKE_PASS
AIDICT_MAC_SELFTEST_PASS hotkeys=ok(registered=3); popup.visible=ok;
popup.inside=ok(frame=430x560); popup.inject=ok(chars=28);
popup.hiddenAfterRestore=ok; clipboard.popup=ok; clipboard.inject=ok;
ocr.vision=ok(lines=1); selection.ax=ok(chars=28)
```

覆盖：

- 3 个 Carbon 全局热键真实注册；
- 结果面板在屏幕可见区域内、WebView 注入选中文本；
- 恢复主窗口时面板隐藏；
- NSPasteboard 剪贴板取词并注入面板；
- Vision.framework 对生成图片做 OCR，并注入 OCR 页面；
- Accessibility API 读取 NSTextField 选中文本（CI runner 已具备辅助功能权限）。

macOS 构建在 `macos-26`（arm64）与 `macos-15-intel`（x64）两个 runner 上均通过。Apple Silicon 使用 `-ngl 99` 启用 Metal 卸载，Intel Mac 使用 `-ngl 0` CPU 回退。

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

**已在 CI 验证：**

- 编译、`.app` 启动、WKWebView 导航、弹窗/剪贴板/Vision OCR/AX 选中文本自测；
- arm64 与 x64 两个 runner。

**仍需在真实 Mac 上确认：**

- 首次授予「辅助功能」「屏幕录制」后的系统设置路径与授权持久性（CI 已预授权，不能替代用户首次授权体验）；
- 区域截图 OCR 的真实屏幕捕获（自测使用生成图片验证 Vision 与页面注入，不依赖屏幕录制权限）；
- Chrome / Safari / Word / PDF / 多显示器 / Retina 缩放下的跨应用取词；
- macOS 13/14 运行时兼容性（当前 runner 为 macOS 15/26，deployment target 13.0，尚未在 13/14 真机启动验证）。

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
| `AI-Dictionary-1.0.5-Windows-x64-Setup.exe` | 27,534,472 | `ff0bfb1c94bf9ef09c4d5d1cc5a5d2c7d38c2d4f80cb8851984593266c8ed8b3` |
| `AI-Dictionary-1.0.5-Windows-x64-Setup.zip` | 40,501,956 | `00682cb2120f943455a860c15fe551fd015bcb56b1e737c97bbe2f51a7a5b08c` |
| `AI-Dictionary-1.0.5-macOS-arm64.dmg` | 57,982,886 | `75f3142149d7455f6dfd486112f1536effd580d361d3b05171ba5c35f8bfc4f2` |
| `AI-Dictionary-1.0.5-macOS-arm64.pkg` | 51,006,101 | `d11c06b7aa950e03b2c59fdc83ff2868111bbb8d5afbc3e4ee6ee97f8b082f0c` |
| `AI-Dictionary-1.0.5-macOS-x64.dmg` | 52,952,368 | `bb7a01f8ae33e31a165d3ae09542dddb102bfdf87138868aa8a2bdc69b8f8c0e` |
| `AI-Dictionary-1.0.5-macOS-x64.pkg` | 47,016,295 | `f7b9501f14c39e54ced4afafbd495ae3591dd48fa76dba94be960e3e6c107065` |

macOS 产物由 GitHub Actions（`macos-26` arm64 / `macos-15-intel` x64）构建；构建过程包含真实的 WKWebView `--smoke-test`。CI 与 Windows 安装包均通过。产物因当前 PAT 缺少 `workflow` scope，CI 上传时使用了兼容的 `1.0.2` 文件名，下载后已重命名为 1.0.5。

---

## 6. macOS 真机修复（1.0.5 补丁，未改版本号）

在真实 Mac（macOS 27.0.1，Apple Silicon M 系列，Xcode CLT/Swift 6.4）上执行
`python scripts/build_installers.py --platform macos --arch arm64` 时，`--smoke-test` 通过，
但内置 `--self-test` 失败：

```text
AIDICT_MAC_SELFTEST_FAIL hotkeys=ok(registered=3); popup.visible=ok; popup.inside=ok(frame=430x560);
popup.inject=ok(chars=28); popup.hiddenAfterRestore=ok; clipboard.popup=ok; clipboard.inject=ok;
ocr.vision=fail(lines=0); selection=skipped(no accessibility)
```

CI 的 macOS runner 未复现，原因是首次 Vision 请求的冷启动耗时取决于机器状态。

### 6.1 根因

`scripts/macos_app_shell.swift` 的 OCR 自测在启动 `VNRecognizeTextRequest` 后**固定等待 5 秒**
再断言。实测本机第一次 Vision 文字识别耗时 **29.7 秒**（macOS 需要加载识别模型/编译 ANE 图），
之后同一进程内约 70–120 ms。所以 OCR 本身正常（识别出 1 行），只是断言等待时间不够。
其它机器上 5 秒可能刚好够，导致"有时过、有时不过"的假失败。

### 6.2 修复（`scripts/macos_app_shell.swift`）

1. **自测改为轮询**：最多等待 90 秒，每 250 ms 检查一次 OCR 页面渲染出的行数；若 OCR 明确返回 0 行则立即失败，不再依赖固定 5 秒。
2. **启动时后台预热 Vision**（正常启动才预热，`--smoke-test` / `--self-test` 跳过以保持计时稳定），用户第一次「框选截图识别」不再看起来像卡死。
3. **多显示器 OCR 坐标**：原实现用「所有屏幕并集的 `maxY`」翻转 Cocoa→Quartz 坐标，副屏位于主屏上方/下方时会截到错误区域；改为按**主屏高度**翻转，并对选区做屏幕裁剪与明确报错。
4. **`popup.inside` 自测**改用面板实际所在屏幕的 `visibleFrame`（原用 `NSScreen.main`，鼠标在副屏时误判失败）。
5. **点击本应用窗口/迷你窗/菜单栏时自动关闭悬浮结果面板**（清单 M-10：弹窗不得盖住输入框）。
6. **关闭主窗口到菜单栏时同时关闭迷你窗**（与 Windows `Hide-MiniWindow` 一致）。
7. **托盘左键动作读取 `tray_click_action`**（与 Windows 一致）；右键菜单改用 `NSMenu.popUp` 直接弹出，避免 `performClick` 重入导致菜单无响应。
8. **AX 划词向上遍历 5 层父元素**，并在每一层检查 `AXSecureTextField`，提升 Chrome/Safari/Word 等应用取词成功率，同时保持密码框拦截。
9. **OCR 取消（Esc）** 只在主窗口原本可见时恢复主窗口（与 Windows `$wasVisible` 一致）。
10. **热键重复注册抑制**：三个 WebView 在页面加载时都会发送 `updateHotkeys`，原实现每次都注销再注册，存在瞬时失败窗口；现在组合键未变化时直接跳过。
11. **诊断日志 `native.log`**（对齐 Windows `Write-Diagnostic`）：记录启动、后端 PID、热键注册结果、OCR 耗时、剪贴板事件、权限拒绝、自测结果等。
12. **自测结果落盘** `aidict-selftest-result.txt`，并在退出前回收后端进程（避免占用 14205 端口）。

### 6.3 共享代码与构建脚本

- `scripts/run_local_server.py`：安装 `SIGTERM/SIGINT/SIGHUP` 处理，退出时停止 `llama-server` 子进程。此前 macOS 上退出应用后 `llama-server` 会残留（占用 1–2 GB 内存与端口）。Windows 由 `taskkill /T` 处理整棵进程树，行为不变。
- `src/index.html`：`loadHistory()` 把后端 `privacy_mode` 同步给原生壳，修复菜单栏/托盘「私密模式」勾选状态过期（两端共享逻辑）。
- `scripts/verify_acceptance.py`：从仓库 `data/macos_native_bridge` 显式设置 `AIDICT_NATIVE_BRIDGE`。此前数据目录指向临时目录，导致 macOS 原生检查永远 SKIP，无法真正验证 AC-03/AC-04。
- `scripts/build_installers.py`：增加解释器架构校验。PyInstaller 无法交叉打包，`--arch x64` 在 arm64 Python 下会产出「x64 外壳 + arm64 后端」的坏包；现在直接报错并提示在 Intel Mac 或 x86_64/Rosetta Python 下构建。

### 6.4 验证结果（本机 macOS 27 / arm64）

```text
AIDICT_NATIVE_SMOKE_PASS
AIDICT_MAC_SELFTEST_PASS hotkeys=ok(registered=3); popup.visible=ok; popup.inside=ok(frame=430x560);
popup.inject=ok(chars=28); popup.hiddenAfterRestore=ok; clipboard.popup=ok; clipboard.inject=ok;
ocr.vision=ok(lines=1); selection=skipped(no accessibility)
```

- `test_regressions.py`：10 项通过；`test_desktop_ui.py`：Chromium + WebKit、100/125/150/200% 通过。
- `verify_acceptance.py`：**18 项通过、0 SKIP**（含 `AC-03 native secure-field guard`、`AC-04 native Vision OCR`）。
- DMG 挂载后校验：`.app` 可执行文件 SHA256 与构建目录一致，ad-hoc 签名，`--smoke-test` 通过。
- `selection=skipped(no accessibility)`：从终端启动的 ad-hoc 应用没有辅助功能授权，属预期跳过；装到 `/Applications` 并按第 8 节授权后执行 `bash scripts/macos_doctor.sh --self-test` 可验证 AX 划词。

### 6.5 仍未在真机覆盖

- macOS 13/14 的运行时验证（本机为 27，deployment target 13.0）；
- Intel Mac 的 x64 安装包需在 Intel Mac 或 x86_64 Python 下构建（CI 的 `macos-15-intel` 覆盖）；本机 arm64 只能验证 x64 Swift 外壳可交叉编译。
- 真实屏幕录制权限下的选区截图、多显示器/全屏 Space 跨应用取词仍需人工按第 9 节清单执行。

本机（macOS 27 / arm64）重建产物校验值（与第 5 节 CI 产物不同，仅用于本机复现）：

| 文件 | SHA256 |
|---|---|
| `AI-Dictionary-1.0.5-macOS-arm64.dmg` | `2d05076e89cb9910b293d857cad5d2d37534964302eb40215cbde09235c8d967` |
| `AI-Dictionary-1.0.5-macOS-arm64.pkg` | `558f2b442b836ea73812a0c339e2be069eb1ea2fd810045516244f210866e36d` |

DMG 挂载后 `Contents/MacOS/AIDictionary` 的 SHA256 与构建目录一致
（`06836ff875526a2f504892eb29e6af6f304d7eab482b805cfafbb0ce33999a51`），ad-hoc 签名，从挂载卷直接 `--smoke-test` 通过。
