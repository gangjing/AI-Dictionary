# AI Dictionary macOS 开发、测试与修复手册

**适用版本：** v1.0.5（Windows 1.0.5 为功能基线）  
**适用环境：** macOS 13+，Apple Silicon / Intel Mac，DeepSeek Harness  
**目标：** 在 Mac 上从 GitHub 拉取代码、运行、构建、安装、逐项测试，并用 DeepSeek Harness 修复 macOS 端问题，同时保证不破坏 Windows 行为。

> 当前仓库的真实架构是：Python 后端 + 单页 HTML 前端 + 原生壳。macOS 壳为 Swift/AppKit + WKWebView，Windows 壳为 PowerShell + WinForms + WebView2。两者共享同一套前端和后端。`src-tauri/` Rust 原型已删除。

---

## 1. 当前基线

| 项目 | 值 |
|---|---|
| 仓库 | https://github.com/gangjing/AI-Dictionary |
| 稳定 Tag | `v1.0.5` |
| 最新 Release | https://github.com/gangjing/AI-Dictionary/releases/tag/v1.0.5 |
| macOS Bundle ID | `com.aidictionary.desktop` |
| 最低系统 | macOS 13.0 |
| 架构 | arm64（Apple Silicon）、x86_64（Intel），分别构建 |
| 用户数据 | `~/Library/Application Support/AIDictionary/` |
| 模型目录 | `~/Library/Application Support/AIDictionary/models/` |
| 本地端口 | `127.0.0.1:14205` |

macOS 1.0.5 已实现并通过 CI 自测：

- Carbon 全局热键；
- AX 划词 + 剪贴板回退 + 安全输入框保护；
- 剪贴板取词；
- 非激活 `NSPanel` 迷你窗，屏幕内定位、置顶；
- 主窗口关闭/恢复时隐藏迷你窗；
- Vision OCR + OCR 页面注入；
- llama.cpp 本地翻译，Apple Silicon 使用 Metal（`-ngl 99`），Intel 使用 CPU（`-ngl 0`）；
- 模型下载/校验/预加载；
- 生词本、复习、历史、私密模式。

CI 自测输出（arm64 / x64 均通过）：

```text
AIDICT_NATIVE_SMOKE_PASS
AIDICT_MAC_SELFTEST_PASS hotkeys=ok(registered=3);
popup.visible=ok; popup.inside=ok(frame=430x560);
popup.inject=ok(chars=28); popup.hiddenAfterRestore=ok;
clipboard.popup=ok; clipboard.inject=ok;
ocr.vision=ok(lines=1); selection.ax=ok(chars=28)
```

但 CI 不能替代真实 Mac 的首次 TCC 授权、多显示器、全屏 Space、Chrome/Word/PDF 跨应用取词。真机仍可能有 bug，本手册给出逐项复现与修复路径。

---

## 2. 在 Mac 上安装 DeepSeek Harness

1. 安装 macOS 版 DeepSeek Harness（官方安装包或你已有的安装方式）。
2. 启动 Harness，确认它可以打开本地文件夹、运行终端命令。
3. 为仓库准备一个工作目录，例如 `~/Developer`。
4. 如果 Harness 支持“打开文件夹 / Open Folder”，后续直接打开 `~/Developer/AI-Dictionary`。
5. 如果 Harness 只提供对话窗口，也可以在它的终端里执行本手册命令，之后把仓库路径告诉它。

建议在 Harness 中使用 **Full Access / 允许终端执行**，否则构建、`codesign`、`hdiutil`、`tccutil` 等命令会被拦截。

---

## 3. 拉取代码

### 3.1 公开仓库（推荐）

```bash
mkdir -p ~/Developer
cd ~/Developer
git clone https://github.com/gangjing/AI-Dictionary.git
cd AI-Dictionary
git fetch --tags
git checkout main
# main 当前 = v1.0.5 代码 + 本手册。
# 严格复现 Release 时可改用：git checkout v1.0.5
```

### 3.2 需要 token 时（不要把 token 写进文件）

```bash
cd ~/Developer
read -r -s GH_TOKEN
git clone "https://x-access-token:${GH_TOKEN}@github.com/gangjing/AI-Dictionary.git" AI-Dictionary
unset GH_TOKEN
cd AI-Dictionary
git remote set-url origin https://github.com/gangjing/AI-Dictionary.git
git fetch --tags
git checkout main
# main 当前 = v1.0.5 代码 + 本手册。
# 严格复现 Release 时可改用：git checkout v1.0.5
```

确认基线：

```bash
git status --short --branch
git describe --tags --always
# 期望：v1.0.5 或 v1.0.5-...
```

---

## 4. 安装构建依赖

在 macOS 上打开终端，执行：

```bash
# 1) Xcode Command Line Tools（swiftc、codesign、hdiutil、pkgbuild）
xcode-select -p || xcode-select --install

# 2) Python 3.12（推荐；PyInstaller 6.17 对 3.12 最稳）
brew install python@3.12

# 3) 虚拟环境
cd ~/Developer/AI-Dictionary
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

# 4) 构建与浏览器测试依赖
python -m pip install pyinstaller==6.17.0 playwright==1.58.0
python -m playwright install chromium webkit
```

验证：

```bash
python --version
swiftc --version
python -c "import PyInstaller, playwright; print('deps ok')"
```

> 如果 `brew` 未安装，先按 https://brew.sh 安装 Homebrew。Apple Silicon 默认前缀 `/opt/homebrew`，Intel 为 `/usr/local`，不要混用两套 Python。

---

## 5. 先跑基线测试（不要先改代码）

```bash
cd ~/Developer/AI-Dictionary
source .venv/bin/activate

python scripts/test_regressions.py
python scripts/test_desktop_ui.py
python scripts/verify_acceptance.py
```

期望：

- `test_regressions.py`：10 项通过；
- `test_desktop_ui.py`：Chromium + WebKit、100/125/150/200% 缩放、六页面无横向溢出；
- `verify_acceptance.py`：16 项通过，原生项在 macOS 上可能显示 SKIP。

如果这里已经失败，先把完整输出保存下来，不要继续改 UI。

---

## 6. 构建 macOS App

### Apple Silicon

```bash
cd ~/Developer/AI-Dictionary
source .venv/bin/activate
python scripts/build_installers.py --platform macos --arch arm64
```

### Intel Mac

```bash
python scripts/build_installers.py --platform macos --arch x64
```

构建脚本会：

1. PyInstaller 打包 Python 后端；
2. 编译 Swift 原生壳 + `macos_native_bridge`；
3. 下载并打包 llama.cpp macOS CPU/Metal 运行时；
4. 生成 `.app`；
5. 运行真实 `--smoke-test`；
6. 运行真实 `--self-test`；
7. 生成 DMG/PKG。

输出：

```text
dist/macos-arm64/AI Dictionary.app
dist/installers/AI-Dictionary-1.0.5-macOS-arm64.dmg
dist/installers/AI-Dictionary-1.0.5-macOS-arm64.pkg
```

构建过程中任何 smoke/self-test 失败都会中止并打印输出，这是第一道防线。

---

## 7. 安装到 /Applications

### DMG

```bash
hdiutil attach dist/installers/AI-Dictionary-1.0.5-macOS-arm64.dmg
cp -R "/Volumes/AI Dictionary 1.0.5/AI Dictionary.app" /Applications/
hdiutil detach "/Volumes/AI Dictionary 1.0.5"
open "/Applications/AI Dictionary.app"
```

### PKG

```bash
sudo installer -pkg dist/installers/AI-Dictionary-1.0.5-macOS-arm64.pkg -target /
open "/Applications/AI Dictionary.app"
```

> 未公证的 ad-hoc 签名包首次启动会被 Gatekeeper 拦截：右键 App → 打开。确认来源可信后再继续。

---

## 8. 首次权限设置（macOS 最容易出错的一步）

### 8.1 复位旧授权

每次重新构建/替换 ad-hoc 签名的 App，macOS 可能保留旧 TCC 记录但新二进制不生效。先完全退出 App，然后：

```bash
tccutil reset Accessibility com.aidictionary.desktop
tccutil reset ScreenCapture com.aidictionary.desktop
```

再启动 `/Applications/AI Dictionary.app`。

### 8.2 授权

打开：

- 系统设置 → 隐私与安全性 → **辅助功能**：加入并勾选 AI Dictionary；
- 系统设置 → 隐私与安全性 → **屏幕录制**：加入并勾选 AI Dictionary；
- 授权后 **退出 App 再启动一次**。

### 8.3 验证

```bash
open -a "AI Dictionary"
```

然后按：

- `Option+Command+T`：划词；
- `Option+Command+S`：截图 OCR；
- `Option+Command+D`：主窗口。

如果菜单栏图标在但热键无反应，先看第 12 节。

---

## 9. 完整测试清单（以 Windows 1.0.5 为基准）

每项建议记录：系统版本、Mac 型号/芯片、显示器数量、缩放、是否全屏 Space、复现步骤、截图。

### 9.1 启动与托盘/菜单栏

| ID | 操作 | 期望 |
|---|---|---|
| M-01 | 启动 App | 主窗口正常显示，菜单栏出现 AI 词典图标 |
| M-02 | 点击主窗口关闭按钮 | 主窗口隐藏，进程不退出，菜单栏图标仍在 |
| M-03 | 菜单栏左键点击 | 弹出迷你查词窗；再点一次关闭 |
| M-04 | 菜单栏右键 | 出现菜单：显示主窗口、划词开关、剪贴板、OCR、私密模式、设置、退出 |
| M-05 | 关闭主窗口后再点“显示主窗口” | 主窗口恢复，迷你窗不得残留/遮挡 |
| M-06 | 完全退出后重开 | 状态正常，不出现两个菜单栏图标 |

### 9.2 划词

| ID | 操作 | 期望 |
|---|---|---|
| M-07 | 在 TextEdit 选中英文，按 `Option+Command+T` | 鼠标附近出现迷你窗，显示来源应用，查到释义 |
| M-08 | 在 Safari/Chrome 选中网页文字，按热键 | 同上；如 AX 不支持应自动走复制回退，剪贴板恢复原内容 |
| M-09 | 把鼠标放在屏幕右下角再划词 | 弹窗完整可见，不能越出屏幕/被 Dock 裁掉 |
| M-10 | 弹窗显示时点主窗口/恢复主窗口 | 弹窗立即隐藏，不得盖住输入框 |
| M-11 | 在密码框选中文字按热键 | 不读取、不复制、不记录，提示安全输入 |
| M-12 | 在终端选中文本按热键 | 不发送 `Command+C` 中断命令；提示手动复制或剪贴板取词 |

### 9.3 剪贴板取词

| ID | 操作 | 期望 |
|---|---|---|
| M-13 | 设置/菜单开启“剪贴板自动取词” | 开启瞬间不弹旧剪贴板内容 |
| M-14 | 在别的应用复制一段文字 | 自动弹迷你窗；内容正确 |
| M-15 | 在 AI 词典内部复制译文 | 不应再次弹自己的剪贴板内容 |
| M-16 | 关闭剪贴板取词 | 复制不再弹窗 |

### 9.4 OCR

| ID | 操作 | 期望 |
|---|---|---|
| M-17 | 按 `Option+Command+S`，拖选含中英文的区域 | 出现“截图识别”页；识别结果逐行可编辑 |
| M-18 | 点击“送入翻译” | OCR 文本进入翻译页 |
| M-19 | 中文/英文/混排各一次 | 中文不乱加空格；英文正常 |
| M-20 | 在未授权屏幕录制时触发 | 明确提示去系统设置，不静默失败 |
| M-21 | 多显示器/Retina | 选区坐标正确，截图不偏移 |

### 9.5 翻译与模型

| ID | 操作 | 期望 |
|---|---|---|
| M-22 | 设置 → 本地翻译模型 → 下载 Q4_K_M | 进度、断点续传、SHA256、完成后启用 |
| M-23 | 翻译页点“预加载模型” | 模型加载成功，badge 显示“模型已加载” |
| M-24 | 短句中英互译 | 结果正确，耗时合理 |
| M-25 | 含 `` `code` ``、`{变量}`、URL 的文本 | 结构原样保留 |
| M-26 | 自定义术语表 | 术语强制生效 |
| M-27 | 翻译中取消/再次翻译 | 旧请求不覆盖新结果 |
| M-28 | Q6_K 与 Q4_K_M 对比 | Q4 明显更快；Q6 更慢但质量更高 |
| M-29 | 卸载模型 | 词典、划词、OCR 仍可用；翻译给出明确引导 |
| M-30 | Apple Silicon | llama-server 使用 Metal；Intel 使用 CPU |

### 9.6 生词本/历史/隐私

| ID | 操作 | 期望 |
|---|---|---|
| M-31 | 收藏单词、编辑备注、删除 | 正确持久化 |
| M-32 | 开始复习并评分 | 复习日期按 1/2/4/7/15 天推进 |
| M-33 | 导入/导出 JSON、CSV | 文件正确 |
| M-34 | 开启私密模式后查词/划词/翻译 | 历史 0 行 |
| M-35 | 清空历史 | 列表为空 |
| M-36 | 深浅色切换 + 重启 | 主题保持 |

### 9.7 兼容性

| ID | 操作 | 期望 |
|---|---|---|
| M-37 | 多显示器、不同缩放 | 弹窗/OCR 选区在正确屏幕 |
| M-38 | 全屏 Space / 多桌面 | 弹窗可在当前 Space 显示，不跑到别的桌面 |
| M-39 | 休眠唤醒后划词 | 热键、弹窗仍工作 |
| M-40 | macOS 13 / 14 / 15 / 26 | 至少启动、划词、OCR、翻译各一次 |
| M-41 | Intel Mac | 原生 x64 启动，不依赖 Rosetta |
| M-42 | 替换新构建后权限 | 不复用失效 TCC；按第 8 节复位后可用 |

---

## 10. 原生自测与诊断

### 10.1 一键收集环境

```bash
cd ~/Developer/AI-Dictionary
bash scripts/macos_doctor.sh
```

带原生自测：

```bash
# 先完全退出 AI Dictionary，确保 14205 没有被占用
bash scripts/macos_doctor.sh --self-test
```

期望看到：

```text
AIDICT_MAC_SELFTEST_PASS hotkeys=ok(registered=3); ...
```

### 10.2 直接运行 App 看 stdout/stderr

```bash
# 先退出正在运行的 App
TMP=$(mktemp -d)
AIDICT_USER_DATA_DIR="$TMP" \
  "/Applications/AI Dictionary.app/Contents/MacOS/AIDictionary" --self-test
```

如果要看正常启动日志：

```bash
"/Applications/AI Dictionary.app/Contents/MacOS/AIDictionary"
```

`print()` 日志、后端启动、Swift 异常都会出现在终端。

### 10.3 后端与 llama 日志

```bash
# 后端健康
curl -s http://127.0.0.1:14205/api/dict/stats | python3 -m json.tool
curl -s http://127.0.0.1:14205/api/translate/status | python3 -m json.tool

# llama-server 日志
tail -n 80 "$HOME/Library/Application Support/AIDictionary/llama-server.log"

# 原生壳诊断日志（启动、热键注册结果、OCR 耗时、剪贴板事件、权限拒绝）
tail -n 80 "$HOME/Library/Application Support/AIDictionary/native.log"

# 原生自测结果（--self-test 时写入）
cat "$HOME/Library/Application Support/AIDictionary/aidict-selftest-result.txt"

# 端口/进程
lsof -nP -iTCP:14205 -sTCP:LISTEN
pgrep -fl "AIDictionary|llama-server"
```

### 10.4 签名/隔离/崩溃

```bash
codesign -dv --verbose=4 "/Applications/AI Dictionary.app"
spctl -a -vv "/Applications/AI Dictionary.app"
xattr -l "/Applications/AI Dictionary.app"

# 最近崩溃报告
ls -lt ~/Library/Logs/DiagnosticReports | head
```

### 10.5 系统日志

```bash
log show --last 10m --predicate 'process == "AIDictionary"' --style compact
```

---

## 11. 常见症状 → 根因 → 修复

| 症状 | 优先检查 | 处理 |
|---|---|---|
| 按热键完全没反应 | 辅助功能授权、热键冲突 | 复位 TCC；系统设置重新授权；改设置里的热键 |
| 划词到了密码框仍弹窗 | 安全输入检测 | 检查 `AXSecureTextField` / `IsSecureEventInputEnabled`；不应回退复制 |
| 弹窗在屏幕右下角被裁掉 | 定位用了固定尺寸 | 用实际 `frame.size` + `visibleFrame` 夹取；记录显示器坐标 |
| 弹窗被主窗口盖住 | 面板层级/激活顺序 | `orderFrontRegardless`、非激活 `NSPanel`；恢复主窗口时关闭面板 |
| 关闭主窗口后弹窗还在 | 关闭路径遗漏 | `windowShouldClose` / `hideMainWindowToTray` 同时 `resultPanel.orderOut` |
| 菜单栏图标点击无反应 | 进程还在但 status item 丢失 | 完全退出重开；检查 `NSStatusItem` 强引用 |
| 剪贴板取词不弹 | 授权、自身窗口过滤 | 检查 `changeCount`、`NSApp.isActive`、`lastSelectionText` |
| 剪贴板取词弹旧内容 | 启用时未同步当前内容 | 启用时先记录 `changeCount`/当前字符串 |
| OCR 无结果 | 屏幕录制权限、选区太小、语言包 | 先授权；放大选区；检查 `VNRecognizeTextRequest` 支持语言 |
| Intel 上 OCR 英文都不识别 | Vision 语言模型缺失 | 用 `supportedRecognitionLanguages` 过滤并回退 `en-US` |
| 第一次截图识别要等很久（约 30 秒） | Vision 首次加载识别模型 | 1.0.5 补丁已在启动时后台预热；仍慢可看 `native.log` 的 `vision warm-up` 耗时 |
| 构建时 `--self-test` 报 `ocr.vision=fail` | 首次 OCR 冷启动超过固定等待 | 已改为轮询（≤90 秒）；确认用的是最新 `macos_app_shell.swift` |
| 退出应用后 `llama-server` 还在跑 | 后端未收到 SIGTERM 清理 | 已加 SIGTERM/SIGHUP 处理；`pgrep -fl llama-server` 可确认 |
| 菜单栏图标右键没反应 | `performClick` 重入 | 已改为 `NSMenu.popUp`；仍异常看 `native.log` |

| 翻译很慢 | Q6/CPU、模型未预加载 | 换 Q4_K_M；点“预加载模型”；Apple Silicon 确认 `-ngl 99` |
| 翻译不可用 | 模型未下载、llama-server 路径/启动失败 | 查 `llama-server.log`；检查模型 registry 与 `llama/llama-server` |
| App 打不开/Gatekeeper | 未公证、隔离属性 | 右键打开；必要时 `xattr -dr com.apple.quarantine` |
| 更新后功能失效 | TCC 绑定旧二进制 | 第 8 节复位并重新授权 |
| 多屏截图偏移 | Quartz/NSScreen 坐标转换 | 用鼠标所在屏幕的 `frame`，不要写死主屏 |
| 全屏 Space 弹窗不出现 | window level/collectionBehavior | `.floating`/`.screenSaver` + `.canJoinAllSpaces` + `.fullScreenAuxiliary` |

---

## 12. 在 DeepSeek Harness 中修复的推荐流程

### 12.1 打开项目

在 Harness 中选择 **Open Folder**，指向：

```text
~/Developer/AI-Dictionary
```

然后新建会话，粘贴下面这段“首条指令”：

```text
你是 AI Dictionary 的 macOS 端维护者。仓库：~/Developer/AI-Dictionary。
先阅读：
- README.md
- docs/MACOS_HARNESS_GUIDE.md
- docs/RELEASE_1.0.5.md
- scripts/macos_app_shell.swift
- scripts/run_local_server.py
- scripts/windows_tray_shell.ps1（Windows 行为基准）
- src/index.html

目标：以 Windows 1.0.5 的功能为基准，修复 macOS 端剩余 bug，保证 macOS 13+、Apple Silicon 与 Intel 都可用。

约束：
1. 不要删除或弱化 Windows 端已有行为；修改共享代码时必须同时跑 Windows 相关回归。
2. 修改后必须运行：
   python scripts/test_regressions.py
   python scripts/test_desktop_ui.py
   python scripts/verify_acceptance.py
   python scripts/build_installers.py --platform macos --arch arm64
   （如机器是 Intel，再跑 --arch x64）
3. 构建脚本内置 --smoke-test 与 --self-test；必须看到 AIDICT_MAC_SELFTEST_PASS。
4. 任何 UI 变化都要在真实 Mac 上截图/录屏验证，不能只靠单元测试。
5. 不要硬编码 token、密码或用户路径。

请先运行基线测试和 macos_doctor.sh，列出当前失败项，再逐项修复。
```

### 12.2 让 Harness 先做诊断

```bash
cd ~/Developer/AI-Dictionary
git status --short --branch
bash scripts/macos_doctor.sh
```

把输出直接贴给 Harness。若 App 已运行，先退出再跑 `--self-test`。

### 12.3 每一项修复的完成标准

Harness 提交修复前必须满足：

- 复现步骤 + 修复前现象 + 修复后现象；
- 相关测试通过；
- macOS `--self-test` 通过；
- Windows 端对应路径没有回归（至少静态检查 + 相关测试）；
- 若改了版本/打包，更新 `docs/RELEASE_*.md` 和 `README.md`；
- 不把构建产物、日志、`dist/`、用户数据提交进 Git。

### 12.4 提交与发布

```bash
git switch -c fix/macos-<short-name>
git add -A
git commit -m "Fix macOS <problem>"
git push -u origin HEAD
```

推送到 `fix/**` 分支会触发 GitHub Actions 的 macOS arm64/x64 构建。CI 通过后再合并 main、打 tag、发布 Release。

> 注意：当前用于自动化的 PAT 只有 `repo` scope，不能修改 `.github/workflows/`。如果 Harness 需要改 workflow，必须换一个有 `workflow` scope 的 token；否则只改业务代码，workflow 保持不变。

---

## 13. 版本与发布流程

1. 修改 `scripts/build_installers.py` / `scripts/windows_installer.nsi` / `scripts/build_windows_exe.py` 中的版本号；
2. 更新 `README.md`、`docs/RELEASE_<version>.md`；
3. 本地构建 macOS 两个架构：
   ```bash
   python scripts/build_installers.py --platform macos --arch arm64
   python scripts/build_installers.py --platform macos --arch x64
   ```
4. 检查 `--smoke-test` 与 `--self-test` 输出；
5. 在真实 Mac 上安装 DMG/PKG，跑第 9 节清单；
6. 提交、打 tag、上传 Release 资产（DMG/PKG/Windows exe/zip/validation JSON）；
7. 在 README 写清楚：ad-hoc 签名、未公证、macOS 13/14 是否实测。

---

## 14. macOS 兼容性矩阵

| 系统/芯片 | 状态 | 说明 |
|---|---|---|
| macOS 26 / arm64 | CI 已构建 + 自测通过 | GitHub `macos-26` |
| macOS 15 / x64 | CI 已构建 + 自测通过 | GitHub `macos-15-intel` |
| macOS 15 / arm64 | 预期可用 | 与 26 arm64 同一代码路径 |
| macOS 14 / arm64、x64 | 未真机验证 | 部署目标 13.0；需实测 |
| macOS 13 / arm64、x64 | 未真机验证 | 最低支持版本；需重点实测 |
| Apple Silicon M1–M4 | 已构建 arm64 | Metal 卸载 |
| Intel Mac | 已构建 x64 | CPU 推理，速度较慢 |

兼容性注意事项：

- 不要用 Rosetta 运行 x64 包到 Apple Silicon 上；优先 arm64。
- Apple Silicon 模型推理加 `-ngl 99`；Intel 加 `-ngl 0`。
- Intel Vision 可能只带英文 OCR 模型，代码已按支持语言过滤并回退 `en-US`。
- 屏幕录制/辅助功能授权在替换 App 后可能失效，必须复位 TCC。
- 未公证，Gatekeeper 会拦截；正式分发需要 Developer ID + notarization。
- 窗口/面板坐标全部使用 AppKit point，不要混用 Quartz 像素坐标。

---

## 15. 当前已知限制

1. 安装包未签名；macOS 为 ad-hoc 签名、未公证。
2. 模型不内置，首次使用需联网下载约 1.1 GB。
3. 翻译为请求-响应模式，暂未逐 token 流式渲染。
4. OCR 对低分辨率、竖排、手写、复杂版式仍可能出错。
5. 全局热键固定组合；被其他应用占用时需在设置中更换。
6. 终端窗口不自动复制回退，避免 `Command+C` 中断命令。
7. macOS 13/14 未在真机跑完整清单；CI 只覆盖 15/26。
8. `src-tauri/` 已删除；不要再按旧技术文档找 Rust 实现。

---

## 16. 附：最小可用命令清单

```bash
# 环境
xcode-select -p || xcode-select --install
brew install python@3.12
cd ~/Developer/AI-Dictionary
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install pyinstaller==6.17.0 playwright==1.58.0
python -m playwright install chromium webkit

# 基线
python scripts/test_regressions.py
python scripts/test_desktop_ui.py
python scripts/verify_acceptance.py

# 构建
python scripts/build_installers.py --platform macos --arch arm64

# 安装
hdiutil attach dist/installers/AI-Dictionary-1.0.5-macOS-arm64.dmg
cp -R "/Volumes/AI Dictionary 1.0.5/AI Dictionary.app" /Applications/
hdiutil detach "/Volumes/AI Dictionary 1.0.5"

# 权限复位（替换新构建后）
tccutil reset Accessibility com.aidictionary.desktop
tccutil reset ScreenCapture com.aidictionary.desktop
open "/Applications/AI Dictionary.app"

# 诊断
bash scripts/macos_doctor.sh --self-test
```

---

**维护原则：** macOS 端任何修改都以 Windows 1.0.5 的行为为基准；共享业务逻辑只改一处，两端同时回归。不要用“mac 上能用”作为唯一标准，Windows 不回归才算完成。
