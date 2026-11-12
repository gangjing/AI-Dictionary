# AI Dictionary 客户端完整工程目录结构树 (Tauri 2 + React + Rust)

```
ai-dictionary/
├── .github/
│   └── workflows/
│       ├── build-windows.yml       # Windows MSI / NSIS 打包与代码签名 CI
│       └── build-macos.yml         # macOS DMG 打包与 Apple Notarization 公证 CI
├── src-tauri/                      # Rust 底层原生桌面能力
│   ├── Cargo.toml                  # Rust 依赖 (tauri 2.0, windows-sys, cocoa, objc, rusqlite)
│   ├── tauri.conf.json             # 跨平台多窗口配置 (main, hud, tray-popover)
│   ├── capabilities/
│   │   └── default.json            # 权限能力配置 (剪贴板、全局快捷键、文件访问)
│   ├── icons/                      # 双平台应用图标
│   │   ├── 32x32.png
│   │   ├── 128x128.png
│   │   ├── icon.icns               # macOS 应用图标
│   │   └── icon.ico                # Windows 应用图标
│   ├── src/
│   │   ├── main.rs                 # 应用生命周期初始化与多窗口加载
│   │   ├── lib.rs                  # Tauri 插件与指令注册入口
│   │   ├── ocr/                    # 本地 OCR 原生绑定
│   │   │   ├── mod.rs
│   │   │   ├── win_ocr.rs          # Windows.Media.Ocr (WinRT) 接口封装
│   │   │   └── mac_vision.rs       # macOS Apple Vision Framework 封装
│   │   ├── selection/              # 跨应用选词与无抢占焦点捕获
│   │   │   ├── mod.rs
│   │   │   ├── win_uia.rs          # Windows UI Automation + WS_EX_NOACTIVATE 风格无焦点窗口
│   │   │   └── mac_ax.rs           # macOS Accessibility API (AXUIElement) 选区抓取
│   │   ├── sidecar/                # 腾讯 Hy-MT2 本地推理进程调度
│   │   │   ├── mod.rs
│   │   │   ├── process_manager.rs  # llama.cpp 独立 Sidecar 启动、守护与 OOM 熔断
│   │   │   └── ipc_client.rs       # 本地环回 IPC 通信 (Unix Domain Socket / Localhost 随机端口)
│   │   ├── db/                     # SQLite 本地数据持久化
│   │   │   ├── mod.rs
│   │   │   ├── schema.sql          # 词库、生词本、查询历史数据库表结构 (FTS5 全文索引)
│   │   │   └── repository.rs       # 词条极速查询与 CRUD 仓储
│   │   └── tts/                    # 离线系统发音适配器
│   │       ├── mod.rs
│   │       ├── win_sapi.rs         # Windows SAPI / OneCore 语音合成
│   │       └── mac_speech.rs       # macOS NSSpeechSynthesizer 适配
│   └── native/                     # 系统特定原生动效桥接
│       ├── motion.swift            # macOS AppKit / CoreAnimation CASpringAnimation 弹簧动画
│       └── motion_win.cpp          # Windows 11 WinUI 3 CompositionTarget 物理阻尼弹簧
├── public/
│   ├── dict/                       # 离线结构化词典数据 (WordNet + 中英离线词表)
│   │   └── lexicon.sqlite
│   └── assets/                     # 静态 SVG 徽标、图标与字体
│       ├── logo-win11.svg
│       └── logo-macos.svg
├── src/                            # 前端核心业务逻辑 (React 18 + TypeScript)
│   ├── main.tsx                    # React DOM 渲染根入口
│   ├── App.tsx                     # 路由与视窗模式调度 (Main / FloatingHUD / TrayPopover)
│   ├── index.css                   # 全局样式、毛玻璃滤镜与动效回退规范
│   ├── tokens/                     # 设计系统与动效参数令牌
│   │   ├── motion.ts               # Windows 11 Fluent 物理常数 (Stiffness 420, Damping 0.82)
│   │   ├── macosMotion.ts          # macOS Liquid Glass 物理常数 (Stiffness 380, Damping 0.78)
│   │   ├── colors.ts               # 主题色盘 (Fluent Mica Dark / macOS Liquid Glass)
│   │   └── typography.ts           # 字体排印规范 (Segoe UI Variable / SF Pro)
│   ├── components/                 # 可复用组件库
│   │   ├── common/                 # 跨平台通用 UI 组件
│   │   │   ├── AudioSpeaker.tsx    # 离线发音播放器控件
│   │   │   ├── StarButton.tsx      # 生词收藏开关
│   │   │   ├── KeyBadge.tsx        # 快捷键徽标 (⌘ / Ctrl)
│   │   │   └── LoadingDots.tsx     # Hy-MT2 离线推理占位动画
│   │   ├── win11/                  # Windows 11 Fluent 专属组件
│   │   │   ├── FloatingQuickHUD.tsx # 划词悬浮浮层 (380x190)
│   │   │   ├── SystemTrayFlyout.tsx # 任务栏托盘小窗 (380x460)
│   │   │   ├── FluentSidebar.tsx   # 主界面亚克力侧边栏
│   │   │   └── FluentWordDetail.tsx # 展开态多维释义卡片
│   │   └── macos/                  # macOS Liquid Glass 专属组件
│   │       ├── MacOSQuickPill.tsx  # 划词悬浮胶囊窗 (360x180)
│   │       ├── MacOSMenuPopover.tsx# 菜单栏常驻小窗 (380x480)
│   │       ├── TrafficLights.tsx   # 交通灯微控点
│   │       └── GlassSidebar.tsx    # Liquid Glass 通透毛玻璃侧栏
│   ├── pages/                      # 六大核心页面 (P0 范围)
│   │   ├── DictionaryPage.tsx      # 1. 查词主视窗 (结构化多义项、音标、变形、权威例句)
│   │   ├── TranslatorPage.tsx      # 2. AI 双栏翻译工作台 (腾讯 Hy-MT2 离线互译、长文流式)
│   │   ├── OcrCapturePage.tsx      # 3. 屏幕截图 OCR (区域框选提取、置信度编辑、即时翻译)
│   │   ├── WordbookPage.tsx        # 4. 生词本复习中心 (词汇标签、掌握度、CSV / Anki 导出)
│   │   ├── HistoryPage.tsx         # 5. 查询历史 (90天离线日志、私密模式零落盘保护)
│   │   └── SettingsPage.tsx        # 6. 系统设置 (Hy-MT2 模型生命周期管理、热键防冲突、开机自启)
│   ├── hooks/                      # 自定义 React Hooks
│   │   ├── useSelectionLookup.ts   # 全局划词选区监听与坐标定位 Hook
│   │   ├── useHyMT2Inference.ts    # Hy-MT2 异步流式翻译与任务取消调度
│   │   ├── useWordbook.ts          # 生词收藏与 SQLite 增删改查
│   │   └── usePlatformTheme.ts     # 探测系统深色/浅色模式及 prefers-reduced-motion
│   ├── services/                   # 底层通信服务封装
│   │   ├── tauriBridge.ts          # Tauri invoke 指令统一调用封装
│   │   ├── modelManager.ts         # 模型分片下载、断点续传与 SHA256 完整性校验
│   │   └── localDictService.ts     # 本地 SQLite 词典快速索引
│   └── types/                      # TypeScript 类型定义
│       ├── dictionary.ts           # 词条结构、音标、词性及例句模型
│       ├── model.ts                # Hy-MT2 模型状态 (1.8B/7B, GGUF, Quant, VRAM)
│       └── motion.ts               # 动效阶段与弹簧插值参数接口
├── models/                         # 腾讯 Hy-MT2 离线模型存放目录 (用户初次引导下载)
│   ├── .gitkeep
│   ├── Hy-MT2-1.8B-Q4_K_M.gguf     # 推荐默认模型 (~1.13 GB)
│   └── Hy-MT2-7B-Q4_K_M.gguf       # 备选高精度模型 (~4.62 GB, 可选)
├── .env.example
├── .gitignore
├── package.json                    # 前端依赖配置
├── postcss.config.js
├── tailwind.config.js              # 双平台设计系统令牌与主题色扩展配置
├── tsconfig.json                   # TypeScript 编译配置
├── tsconfig.node.json
└── vite.config.ts                  # Vite 桌面端构建配置
```
