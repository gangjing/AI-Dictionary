# AI Dictionary — 数据源、模型与核心组件许可证台账

**版本：** v1.0  |  **更新日期：** 2026-11-12  
**合规红线：** 严禁爬取、拆包或内置有道词典、牛津/朗文/柯林斯等受版权保护的专有词库、例句、发音音频及 UI 素材。所有随包分发或引导下载的资源必须具备明确、可追溯的再分发授权。

---

## 1. AI 翻译模型与推理运行时

| 资源名称 | `source_id` | 版本 / 格式 | 许可证 | 商用与再分发要求 | 分发方式 |
|---|---|---|---|---|---|
| **Tencent Hy-MT2-1.8B / 7B** | `hymt2-apache2` | v1.0 (`Q4_K_M` / `Q6_K` / `Q8_0` GGUF) | **Apache-2.0** | 保留版权声明、LICENSE 与 NOTICE；明确说明不代表腾讯官方背书 | 首次启动按需 HTTPS 下载，附 SHA256 校验 |
| **llama.cpp (`llama-server`)** | `llamacpp-mit` | 锁定通过基准测试的 Release tag | **MIT License** | 保留 MIT 版权声明与许可文本 | 随安装包按 OS/Arch 作为受控 Sidecar 分发 |

---

## 2. 离线基础词典数据源（候选与 MVP 组合）

> **策略：** 采用“英文权威语义网 + 合法开源英汉/汉英词表 + 词形还原表”构建 `dictionary.db`，每条释义、音标、例句在数据库中记录对应的 `source_id` 与 `source_version`，并在 UI 词条底部透明展示来源角标。

| 资源名称 | `source_id` | 覆盖内容 | 许可证 | 合规要求与注意事项 | MVP 采纳状态 |
|---|---|---|---|---|---|
| **Princeton WordNet 3.0** | `wordnet-3.0` | 英文词性、权威英文释义（Gloss）、同义词集（Synsets）、英文示例句、词形还原基表 | **WordNet 3.0 License**（类 BSD 宽松许可） | 必须在应用“关于/许可”页及文档中完整保留 Princeton University 版权声明 | **P0 必选**（英文释义与例句底座） |
| **ECDICT（开源英汉词典数据）** | `ecdict-mit` | 英文单词、英/美音标（IPA）、中文简明释义、词频、柯林斯星级标签、词形变化（exchange 字段） | **MIT License**（代码与清洗集声明 MIT） | 需在 ETL 阶段剔除任何来源存疑的第三方抓取扩展字段，仅保留基础简明英汉释义、音标与词形变化，并保留 MIT 声明 | **P0 候选**（需在 ETL 清洗脚本中执行合规过滤） |
| **CC-CEDICT** | `cc-cedict-ccbysa4` | 汉英词条、拼音、英文释义（支持中文查词转英文） | **CC BY-SA 4.0** | 要求署名（Attribution），且对数据库本身的修改部分保持 CC BY-SA 4.0 共享（独立存放在只读 `dictionary.db` 并公开 ETL 脚本即可完全合规） | **P0 必选**（中文查词底座） |
| **Tatoeba 双语例句库（精选子集）** | `tatoeba-ccby2` | 真实中英双语对照例句 | **CC BY 2.0 FR** | 仅筛选标明为 CC BY 2.0 或 CC0 的中英句对，UI 或致谢页保留 Tatoeba 署名与链接 | **P0 必选**（补充高质量双语例句） |

---

## 3. 发音与 OCR 组件合规说明

| 模块 | 实现方案 | 许可证 / 授权边界 |
|---|---|---|
| **发音（TTS）** | Windows 原生 SAPI / `Windows.Media.SpeechSynthesis`；macOS 原生 `AVSpeechSynthesizer` / `NSSpeechSynthesizer` | 调用操作系统内置合法 API，无需打包第三方受版权保护的真人发音 MP3 库；UI 明确标识“系统语音” |
| **本地 OCR** | Windows `Windows.Media.Ocr`；macOS `Vision.framework` (`VNRecognizeTextRequest`) | 调用操作系统内置离线 API，零外部闭源 SDK 依赖，无许可证冲突 |
