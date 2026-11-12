# AI Dictionary — 技术架构与 M0–M2 研发实施计划

**对应 PRD 版本：** [AI_Dictionary_PRD_v1.0.md](file:///Users/gangjing/Documents/AI%20Dictionary/AI_Dictionary_PRD_v1.0.md)  
**日期：** 2026-11-12  
**目标：** 将 PRD 的需求拆解为可执行的工程目录结构、核心 Rust/TypeScript 接口契约、数据库物理 Schema 以及 M0–M2 阶段的具体实施步骤。

---

## 1. 工程仓库结构设计（Monorepo / Tauri v2 标准结构）

采用 Tauri v2 + React 18/19 + TypeScript + Vite + TailwindCSS 架构，Rust 后端按领域模块高内聚、低耦合拆分：

```text
ai-dictionary/
├── AI_Dictionary_PRD_v1.0.md          # 产品需求文档与开发执行摘要
├── docs/
│   ├── TECHNICAL_ARCHITECTURE_AND_PLAN.md  # 本文档：技术架构与实施计划
│   ├── DATA_LICENSE_LEDGER.md         # 词库、模型、开源依赖许可证台账
│   └── BENCHMARK_REPORT.md            # M0 多平台性能基准与取词兼容性报告
├── scripts/
│   ├── etl_dictionary.py              # 词典数据清洗、词形还原映射与 SQLite FTS5 构建脚本
│   └── fetch_sidecar.sh               # 拉取/构建特定平台 llama-server sidecar 二进制
├── src/                               # 前端 React + TypeScript 源码
│   ├── main.tsx                       # 入口，按窗口 label 路由（main / popup / ocr-overlay）
│   ├── windows/
│   │   ├── MainWindow/                # 主窗口（查词、翻译、截图、生词本、历史、设置、首次向导）
│   │   ├── SelectionPopup/            # 轻量划词悬浮卡（独立 Tauri WebviewWindow）
│   │   └── OcrOverlay/                # 屏幕区域选择遮罩层
│   ├── services/
│   │   └── ipc.ts                     # 强类型封装 Tauri invoke 与 Channel 流式事件
│   ├── stores/                        # Zustand 状态管理（查词、翻译流、设置、私密模式）
│   └── types/                         # 与 Rust 共享的 DTO 类型定义
└── src-tauri/                         # Rust 核心后端与系统适配层
    ├── Cargo.toml
    ├── tauri.conf.json                # 多窗口、系统托盘、capabilities 最小权限配置
    ├── binaries/                      # 按 target triple 存放 llama-server sidecar
    ├── migrations/                    # SQLite 数据库迁移脚本（dictionary.db / user_data.db）
    └── src/
        ├── main.rs / lib.rs           # Tauri 启动与插件注册（global-shortcut, single-instance 等）
        ├── commands/                  # 暴露给前端的 #[tauri::command]
        ├── dictionary/                # EP-02: SQLite FTS5 查询、词形还原（Lemmatization）、LRU 缓存
        ├── translation/               # EP-03: llama.cpp sidecar 进程池、Prompt 模板、流式分段队列与熔断
        ├── model_manager/             # EP-04: HTTPS 断点续传（.part）、SHA256 校验、模型注册表
        ├── selection/                 # EP-05: 跨平台取词 trait（macOS AXUIElement / Win UIA / 安全剪贴板回退）
        ├── ocr/                       # EP-07: 屏幕捕获与原生 OCR trait（macOS Vision / WinRT Media.Ocr）
        ├── speech/                    # EP-08: 系统离线 TTS 适配（NSSpeechSynthesizer / Win SAPI）
        ├── wordbook/                  # EP-09: 生词本、历史记录、私密模式拦截、CSV 导出
        └── config/                    # EP-12: 快捷键管理、权限状态探测、系统设置持久化
```

---

## 2. 核心系统架构与数据流

```mermaid
flowchart TB
    subgraph UI["Tauri v2 多窗口前端 (React + TS)"]
        MainWin["主窗口 (MainWindow)"]
        PopupWin["划词浮层 (SelectionPopup)"]
        OcrWin["截图选区层 (OcrOverlay)"]
    end

    subgraph Core["Rust Application Orchestrator (src-tauri)"]
        Hotkeys["全局热键 & 托盘控制器"]
        DictSvc["Dictionary Service\n(SQLite R/O + FTS5 + 词形还原)"]
        UserRepo["Wordbook & History Repo\n(SQLite R/W + 私密模式守卫)"]
        TransSvc["Translation Orchestrator\n(任务优先级队列 / 抢占 / 分段校验)"]
        ModelMgr["Model Manager\n(Range 续传 / SHA256 / 生命周期)"]
        SelAdapter["Selection Adapter\n(macOS AX / Win UIA / 复制回退)"]
        OcrAdapter["Capture & OCR Adapter\n(macOS Vision / WinRT OCR)"]
        TtsAdapter["Speech Adapter\n(系统原生离线 TTS)"]
    end

    subgraph Storage["本地存储与受控进程 (零云端依赖)"]
        DictDB[("dictionary.db\n(只读词库包)")]
        UserDB[("user_data.db\n(生词/历史/设置)")]
        Sidecar["llama-server Sidecar\n(127.0.0.1 随机端口 + Bearer Token)"]
        ModelFile[("Hy-MT2-1.8B-Q4_K_M.gguf")]
    end

    Hotkeys -->|触发划词| SelAdapter
    SelAdapter -->|返回选中文本 & 坐标| PopupWin
    MainWin & PopupWin -->|lookup_word| DictSvc
    DictSvc --> DictDB
    MainWin & PopupWin -->|translate_stream (Channel)| TransSvc
    TransSvc -->|HTTP SSE / Loopback| Sidecar
    Sidecar --> ModelFile
    OcrWin -->|capture & recognize| OcrAdapter
    MainWin & PopupWin -->|save_word / history| UserRepo
    UserRepo --> UserDB
    ModelMgr --> ModelFile
```

---

## 3. 关键技术设计决策与实现契约

### 3.1 双数据库物理隔离（防止词库升级覆盖用户数据）

1. **`dictionary.db`（只读挂载，`SQLITE_OPEN_READ_ONLY`）**
   - 存放结构化词条 `dictionary_entries`、词形变形映射表 `word_forms`（如 `running -> run`, `went -> go`）以及 `dictionary_fts`（FTS5 索引）。
   - 启动时启用 `PRAGMA mmap_size = 268435456;`（256MB 内存映射）与进程内 LRU Cache（容量 2,048 条），确保 p95 查询耗时稳定在 `< 15ms`（远优于 PRD `< 150ms` 要求）。
2. **`user_data.db`（读写挂载，WAL 模式）**
   - 存放 `saved_words`（生词本）、`query_history`（查询历史）、`model_registry`（模型状态）、`app_settings`（配置）。
   - **私密模式守卫（Privacy Guard）**：在 Rust 仓储层统一拦截，当 `privacy_mode == true` 时，任何查词、划词、OCR 请求均跳过 `query_history` 写入，且不落盘任何临时图片或文本。

### 3.2 `llama.cpp` Sidecar 进程管控与流式通信

- **进程隔离与安全**：
  - 启动 `llama-server` 时生成一次性 CSPRNG `api_key`，绑定 `--host 127.0.0.1 --port <ephemeral_port> --api-key <token> --no-webui`。
  - 根据平台自动选择硬件加速：macOS Apple Silicon 默认启用 Metal (`-ngl 99`)；Intel Mac 与无独显 Windows 默认 CPU 并限制物理核线程数（如 `max(1, physical_cores - 1)`），防止桌面卡顿。
- **单并发抢占队列与熔断**：
  - `--parallel 1` 限制单槽位推理以最小化 KV Cache 内存开销（8GB 设备关键保护）。
  - Rust `TranslationOrchestrator` 维护当前活动 `request_id` 的 `CancellationToken`。当新的划词请求到来时，自动 cancel 上一个未完成的划词流（解决 AC-02 新请求被旧结果覆盖问题）。
  - 进程健康检查与看门狗：若 sidecar 异常退出或 OOM，自动记录故障计数；连续 3 次崩溃触发熔断，停止自动拉起并在前端提示降级为纯词典或切换轻量配置。
- **Hy-MT2 提示词模板版本化与格式保护**：
  - 内置经过版本标记（如 `prompt_v1.0_hymt2`）的指令模板，支持在翻译前提取代码块/占位符（`__PROTECTED_TOKEN_0__`）并在流式输出结束后校验还原。

### 3.3 跨应用取词（EP-05）双路径与防打扰设计

1. **首选原生无感路径**：
   - **macOS**：通过 `ApplicationServices` (`AXUIElementCopySystemWide` -> `kAXFocusedUIElementAttribute` -> `kAXSelectedTextAttribute` & `kAXSelectedTextRangeAttribute`) 获取选中文本与屏幕坐标矩形。
   - **Windows**：通过 `UIAutomation` (`GetFocusedElement` -> `TextPattern` -> `GetSelection`) 获取选中文本与 BoundingRectangle。
2. **安全检查与受控复制回退（Fallback）**：
   - 首先检测焦点控件是否为密码框/安全输入（macOS `AXSecureTextField` / Windows `IsPasswordProperty`）或黑名单应用（如 1Password、Keychain、终端模拟器可选）。若是安全框，立即中止并返回 `SelectionError::SecureInputField`（满足 AC-03）。
   - 若原生接口返回空且用户在设置中开启了“允许复制回退”：备份当前剪贴板 `ChangeCount` 与内容快照 -> 发送合成按键（`Cmd+C` / `Ctrl+C`） -> 等待最多 80ms 检测 `ChangeCount` 变化 -> 读取文本 -> 恢复原剪贴板。

### 3.4 屏幕截图与原生离线 OCR（EP-07）

- **多屏高分屏选区**：获取所有显示器逻辑坐标与 `scaleFactor`，全屏透明遮罩不重复捕获自身。截图像素仅保存在 Rust 内存 `Vec<u8>` 中，**绝不写入磁盘临时文件**。
- **原生 OCR 桥接**：
  - **macOS**：通过 `objc2` / Swift 静态桥接调用 `VNRecognizeTextRequest`（`VNRequestTextRecognitionLevelAccurate`，启用 `zh-Hans`, `zh-Hant`, `en-US` 及语言纠错）。
  - **Windows**：通过 `windows` crate 调用 `Windows.Graphics.Imaging.SoftwareBitmap` 与 `Windows.Media.Ocr.OcrEngine`。

---

## 4. M0–M2 分阶段研发实施计划

### 阶段 M0：技术 Spike 与核心风险验证（预计 1–2 周）

> **目标：** 在写复杂业务 UI 前，验证 5 项最高风险底层能力，产出可运行的验证代码与基准数据。

- **Task M0.1：词典数据源授权核验与微型 ETL 管道**
  - 建立 `docs/DATA_LICENSE_LEDGER.md`，明确 WordNet 3.0 + 开源合法可商用中英词表（如 CC-CEDICT / 经许可校验的双语词表）的许可证声明与字段映射。
  - 编写 `scripts/etl_dictionary.py`，生成含 5,000+ 高频测试词条、IPA 音标、词性释义及变形映射表（lemma）的 `dictionary.db`，验证 FTS5 + 精确查询 p95 延迟。
- **Task M0.2：Hy-MT2 GGUF 推理与 Sidecar 管控验证**
  - 验证 `llama-server` 加载 `Hy-MT2-1.8B-GGUF (Q4_K_M)` 的启动耗时、闲置 RSS、推理峰值 RSS、首 token 延迟（TTFT）与生成速度（tokens/s）。
  - 验证通过 Tauri `Channel` 将流式 token 实时推送到前端并支持随时中断（Abort/Cancel）。
- **Task M0.3：跨应用全局划词与安全框拦截 PoC**
  - 在 macOS（及 Windows 条件具备时）实现 `read_selected_text` 原生取词 + 密码框检测 + 剪贴板回退原型，在 Chrome、Safari、VS Code、PDF 预览中实测成功率与耗时（目标 `< 350ms`）。
- **Task M0.4：内存级截图与系统原生 OCR PoC**
  - 验证 macOS `Vision`（及 Windows `WinRT OCR`）对中英混排截图的内存识别准确率与耗时。

**M0 准出标准：** 词库查询 `< 50ms`（本地实测）、Hy-MT2 流式翻译可取消、划词密码框拦截生效、原生 OCR 离线识别跑通。

---

### 阶段 M1：基础桌面词典闭环（预计 2 周）

> **目标：** 完成 Tauri 2 应用骨架、主窗口 UI、离线查词、系统 TTS 发音、生词本与历史记录（含私密模式）。

- **Task M1.1：Tauri v2 + React + TypeScript 项目初始化（EP-01）**
  - 配置多窗口管理（主窗口、托盘菜单、全局快捷键插件 `tauri-plugin-global-shortcut`）。
  - 建立统一日志模块（含 `requestId`, `module`, `elapsedMs`, `errorCode`，严格脱敏正文）与 SQLite 迁移框架。
- **Task M1.2：离线查词引擎与词条详情页（EP-02 / F-001 / F-002）**
  - 实现大小写归一、Unicode NFC 正规化、词形还原（如 `running` -> `run`）与前缀联想建议。
  - 实现主窗口查词 UI：80~120ms 输入防抖、英/美音标展示、分词性释义、词形变化、例句展示及数据源角标。
- **Task M1.3：系统离线发音模块（EP-08 / F-003）**
  - 封装 macOS `NSSpeechSynthesizer` / `AVSpeechSynthesizer` 与 Windows SAPI，支持英/美发音切换、语速调节、停止播放及“系统语音”标识。
- **Task M1.4：生词本、查询历史与私密模式（EP-09 / F-009 / F-010）**
  - 实现收藏/取消收藏（`UNIQUE(source_text, source_lang, target_lang)` 去重并保留备注）、标签筛选、备注编辑、CSV 导出。
  - 实现查询历史记录、一键清理及**私密模式开关**（开启后零历史落盘）。

**M1 准出标准：** 断网状态下可完整执行查词、联想、发音、收藏、备注编辑、CSV 导出与私密模式验证（通过 AC-01, AC-07, AC-08）。

---

### 阶段 M2：本地 AI 翻译引擎与模型管理器（预计 2 周）

> **目标：** 实现模型下载/校验生命周期管理、Hy-MT2 本地流式翻译页、长文分段与异常熔断恢复。

- **Task M2.1：模型管理器与首次启动向导（EP-04 / F-011）**
  - 实现 HTTPS Range 断点续传下载器（临时文件 `.part`）、磁盘剩余空间预检、SHA256 完整性校验、原子重命名、模型激活与卸载。
  - 实现首次启动向导：允许用户跳过模型下载直接使用纯词典模式（满足 U-06 / AC-06 / AC-09）。
- **Task M2.2：Translation Service 与 Sidecar 守护进程（EP-03 / F-007）**
  - 实现 `llama-server` 独立进程管理、空闲自动卸载计时器（5~15 分钟可配）、单任务抢占队列、超时与崩溃熔断机制。
- **Task M2.3：全文/段落翻译 UI 与格式保护（F-007）**
  - 实现左右双栏可调宽翻译页、中英语言自动检测、流式逐字渲染、随时停止生成、一键复制与互换语言。
  - 实现长文按自然段/句子自动切分、数字/URL/Markdown 代码块结构保护与基础后处理。

**M2 准出标准：** 断网状态下完成 Hy-MT2-1.8B Q4 模型校验加载、中英互译流式输出、中途取消、进程强杀后自动恢复及卸载模型后优雅降级（通过 AC-05, AC-06, AC-09, AC-10）。
