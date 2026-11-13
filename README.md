> **1.0.5 更新：** 以 Windows 1.0.4 为模板补齐 macOS：托盘恢复弹窗边界/置顶、主窗口隐藏时关闭弹窗、全局热键、剪贴板取词、AX 划词、Vision OCR 与面板注入全部加入原生自测；macOS CI 在 arm64 / x64 上通过 `--smoke-test` 与 `--self-test`。Apple Silicon 启用 Metal（`-ngl 99`），Intel Mac 回退 CPU（`-ngl 0`），并保留物理核心、Flash Attention、mlock/预加载等速度优化。Windows 安装包与 macOS DMG/PKG 均已重建。

<p align="center">
  <img src="public/assets/logo.svg" width="96" height="96" alt="AI Dictionary Logo" />
</p>

<h1 align="center">AI Dictionary v1.0.5</h1>

<p align="center">
  <strong>Windows / macOS 双平台本地离线 AI 词典与翻译桌面端（Hy-MT2 + llama.cpp + SQLite FTS5）</strong>
</p>

---

## 1.0.5 完成度

| 能力 | Windows | macOS | 说明 |
|---|---|---|---|
| 离线查词 / 词形还原 / 中英反查 / 建议 | 可用 | 可用 | 14,625 条词条，SQLite FTS5 + mmap + LRU |
| 生词本 / 历史 / 私密模式 / CSV / JSON | 可用 | 可用 | 词典库与用户库物理隔离 |
| 全局划词（UIA / AX + 复制回退） | 可用，已自测 | 已实现，待 macOS 实测 | 密码框/安全输入状态直接拒绝 |
| 剪贴板取词（自动弹窗） | 可用，已自测 | 已实现，待 macOS 实测 | 启用时不会弹出旧剪贴板内容 |
| 全局热键 | 可用，已自测注册 | Carbon 实现，待实测 | 默认 `Ctrl+Alt+T/S/D`、`Option+Command+T/S/D` |
| 区域截图 OCR | 可用，已自测 | Vision 实现，待实测 | 内存处理，不写临时图片 |
| Hy-MT2 本地翻译 | 可用，已用真实模型验证 | 已接入 llama-server，待实测 | 需下载约 1.1 GB 模型；llama.cpp 随包 |
| OpenAI 兼容本地服务 | 可用，已用 mock 验证 | 可用 | 支持 Ollama / LM Studio / vLLM 等 |
| 模型下载 / 断点续传 / SHA256 / 原子替换 | 可用，已用 mock 验证 | 同左 | 模型不内置，首次使用需联网下载 |
| 签名 / 公证 | 未签名 | ad-hoc，未公证 | 公开发布前仍需证书与 notarization |

> 没有模型时词典、划词、OCR 全部可用；翻译会明确提示先下载模型或配置本地服务，不会伪造译文。

---

## 安装包

构建产物位于 `dist/installers/`（1.0.5）：

| 平台 | 文件 |
|---|---|
| Windows 10/11 x64 | `AI-Dictionary-1.0.5-Windows-x64-Setup.exe`（NSIS，含 WebView2 检测、llama.cpp CPU 运行时） |
| Windows 便携包 | `AI-Dictionary-1.0.5-Windows-x64-Setup.zip` |
| macOS Apple Silicon | `AI-Dictionary-1.0.5-macOS-arm64.dmg` / `.pkg` |
| macOS Intel | `AI-Dictionary-1.0.5-macOS-x64.dmg` / `.pkg` |

用户数据：macOS `~/Library/Application Support/AIDictionary/`；Windows `%LOCALAPPDATA%\AIDictionary\`。升级/卸载不会主动删除。

---

## 快速开发与验证

```bash
# 1. 重建词典库（可选）
python3 scripts/etl_dictionary.py

# 2. 启动本地服务与浏览器预览
python3 scripts/run_local_server.py --port 1420

# 3. 后端 + 浏览器回归测试
python3 scripts/test_regressions.py
python3 scripts/test_desktop_ui.py

# 4. 自动化验收（平台相关的原生项按平台 SKIP/执行）
python3 scripts/verify_acceptance.py

# 5. 构建 Windows 安装包（需要 Python/PyInstaller；llama.cpp 运行时自动下载）
python3 scripts/build_installers.py --platform windows
python3 scripts/build_windows_exe.py \
  --makensis dist/build-tools/nsis/nsis-3.08/Bin/makensis.exe \
  --bootstrapper dist/build-tools/MicrosoftEdgeWebview2Setup.exe

# 6. 构建 macOS 安装包（需在 macOS + Xcode CLT 上执行）
python3 scripts/build_installers.py --platform macos --arch arm64
```

Windows 原生自测（会真实启动 WebView2、模拟划词、剪贴板取词、密码框拦截与截图 OCR）：

```powershell
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass `
  -File "$env:LOCALAPPDATA\Programs\AI Dictionary\app\scripts\windows_tray_shell.ps1" --self-test
```

自测结果写入 `%TEMP%\aidict-selftest-result.txt`，通过时包含
`PASS selection=...; clipboard(watcher) matched=True; secure=blocked_secure_input; ocrStatus=ok; ocrRendered=1`。

---

## 数据与运行时

- `data/dictionary.db`：14,625 条公开词条、41,916 条词形映射、FTS5 索引。
- `data/user_data.db`：生词本、历史、模型登记、设置。
- 词库来源：公开应试词表（BSD-3-Clause）、少量 WordNet/ECDICT 标注词条、CC-CEDICT 词条；许可证与来源见 [docs/DATA_LICENSE_LEDGER.md](docs/DATA_LICENSE_LEDGER.md)。
- Hy-MT2 GGUF 模型不随安装包分发；首次在「本地翻译模型」下载，校验 SHA256 后原子替换。
- llama.cpp 运行时来自官方 release `b12340`，按平台打包；Windows 为 CPU x64，macOS 为 arm64/x64。

---

## 文档索引

- [产品需求文档 (AI_Dictionary_PRD_v1.0.md)](AI_Dictionary_PRD_v1.0.md)
- [1.0.5 构建与验证记录](docs/RELEASE_1.0.5.md)
- [数据与模型许可证台账](docs/DATA_LICENSE_LEDGER.md)
- [1.0.1 代码检查与修复记录](docs/BUG_REVIEW_1.0.1.md)
- [1.0.2 Windows 界面/DPI 修复记录](docs/UI_REVIEW_1.0.2.md)

> 当前实际发行架构为 Python 后端 + 单页前端 + 原生壳（Swift/AppKit + WKWebView、PowerShell + WinForms + WebView2）。PRD 中的 Tauri 2 + React + Rust 是早期目标技术基线，该原型目录已从仓库移除。
