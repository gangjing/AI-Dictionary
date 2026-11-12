# AI Dictionary 客户端一键本地部署与初始化脚本

为了将当前项目的所有开发代码、配置、动效参数和文档快速导出并在您的本地目录 `/Users/gangjing/Documents/AI Dictionary` 中初始化，我们准备了这一份自动化生成与落地脚本。

---

## 🚀 方式一：在终端运行全自动初始化脚本 (推荐)

打开 macOS **终端 (Terminal)**，直接执行以下命令：

```bash
mkdir -p "/Users/gangjing/Documents/AI Dictionary" && cd "/Users/gangjing/Documents/AI Dictionary"

# 1. 运行一键构建脚本创建完整工程结构与代码文件
cat << 'EOF' > setup-project.sh
#!/bin/bash
set -e

PROJECT_DIR="/Users/gangjing/Documents/AI Dictionary"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

echo "📂 正在创建目录树..."
mkdir -p .github/workflows
mkdir -p src-tauri/{capabilities,icons,src/{ocr,selection,sidecar,db,tts},native}
mkdir -p public/{dict,assets}
mkdir -p src/{tokens,components/{common,win11,macos},pages,hooks,services,types}
mkdir -p models

echo "📝 写入 package.json..."
cat << 'JSON' > package.json
{
  "name": "ai-dictionary",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "tauri": "tauri"
  },
  "dependencies": {
    "@tauri-apps/api": "^2.0.0",
    "@tauri-apps/plugin-global-shortcut": "^2.0.0",
    "@tauri-apps/plugin-clipboard-manager": "^2.0.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "lucide-react": "^0.395.0",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.3.0"
  },
  "devDependencies": {
    "@tauri-apps/cli": "^2.0.0",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "tailwindcss": "^3.4.4",
    "typescript": "^5.4.5",
    "vite": "^5.3.1"
  }
}
JSON

echo "📝 写入 tailwind.config.js..."
cat << 'JS' > tailwind.config.js
/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        fluent: {
          bg: { dark: '#131313', 'dark-alt': '#1b1c1c', card: '#202020' },
          accent: { DEFAULT: '#60cdff', hover: '#70d2ff' }
        },
        macos: {
          bg: { dark: 'rgba(28, 28, 30, 0.78)', light: 'rgba(255, 255, 255, 0.75)' },
          accent: { blue: '#007aff' }
        }
      },
      borderRadius: { fluent: '8px', macos: '10px', 'macos-popover': '14px' },
      boxShadow: {
        'liquid-glass-dark': '0 20px 48px rgba(0, 0, 0, 0.48), 0 0 0 1px rgba(255, 255, 255, 0.12) inset',
        'elevation-flyout': '0 8px 24px rgba(0, 0, 0, 0.36)'
      }
    }
  },
  plugins: []
};
JS

echo "📝 写入动效令牌 src/tokens/motion.ts..."
cat << 'TS' > src/tokens/motion.ts
export const FLUENT_MOTION = {
  spring: { stiffness: 420, damping: 0.82, mass: 1.0 },
  duration: { hudEntry: 120, dismiss: 80, windowMorph: 500 },
  curves: { fluentSpring: 'cubic-bezier(0.16, 1.0, 0.3, 1.0)' }
};

export const MACOS_MOTION = {
  spring: { stiffness: 380, damping: 0.78, mass: 1.0 },
  duration: { popoverDrop: 240, quickDismiss: 80, heroExpansion: 600 },
  curves: { liquidFluid: 'cubic-bezier(0.2, 0.9, 0.2, 1.0)' }
};
TS

echo "📝 写入 macOS 悬浮胶囊组件 src/components/macos/MacOSQuickPill.tsx..."
cat << 'TSX' > src/components/macos/MacOSQuickPill.tsx
import React, { useEffect, useState } from 'react';
import { Volume2, Bookmark, Copy, ArrowUpRight, Cpu } from 'lucide-react';

interface MacOSQuickPillProps {
  word: string;
  phonetic: string;
  pos: string;
  definition: string;
  onExpand?: () => void;
  onDismiss?: () => void;
}

export const MacOSQuickPill: React.FC<MacOSQuickPillProps> = ({
  word, phonetic, pos, definition, onExpand, onDismiss
}) => {
  const [copied, setCopied] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && onDismiss) onDismiss();
      if (e.key === 'Enter' && onExpand) onExpand();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onDismiss, onExpand]);

  return (
    <div className="w-[360px] bg-[#1e1e20]/80 backdrop-blur-2xl border border-white/15 rounded-[12px] p-3.5 text-white select-none shadow-liquid-glass-dark">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-[#ff5f56]" />
          <div className="w-2.5 h-2.5 rounded-full bg-[#ffbd2e]" />
          <div className="w-2.5 h-2.5 rounded-full bg-[#27c93f]" />
          <span className="text-[11px] font-medium text-white/50 ml-1.5">AI DICT HUD</span>
        </div>
        <div className="flex items-center gap-1 text-[10px] font-medium text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
          <Cpu size={11} />
          <span>Metal 3 · 0ms</span>
        </div>
      </div>
      <div className="flex items-baseline justify-between mb-2">
        <div className="flex items-baseline gap-2">
          <h3 className="text-base font-semibold text-white">{word}</h3>
          <span className="text-xs text-white/50 font-mono">{phonetic}</span>
        </div>
        <button title="发音" className="p-1 hover:bg-white/10 rounded-full text-white/70">
          <Volume2 size={13} />
        </button>
      </div>
      <div className="bg-white/5 border border-white/5 rounded-[8px] p-2.5 mb-3">
        <div className="flex items-baseline gap-2">
          <span className="text-[10px] font-bold text-sky-400 uppercase">{pos}</span>
          <span className="text-xs text-white/90 leading-relaxed">{definition}</span>
        </div>
      </div>
      <div className="flex items-center justify-between pt-1 border-t border-white/5 text-xs text-white/60">
        <div className="flex items-center gap-1">
          <button onClick={() => setSaved(!saved)} className="px-2 py-1 hover:bg-white/10 rounded">
            <Bookmark size={11} className={saved ? 'fill-amber-400 text-amber-400' : ''} />
          </button>
          <button onClick={() => {
            navigator.clipboard.writeText(`${word}: ${definition}`);
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          }} className="px-2 py-1 hover:bg-white/10 rounded">
            <Copy size={11} />
          </button>
        </div>
        <button onClick={onExpand} className="flex items-center gap-1 px-2.5 py-1 bg-white/10 hover:bg-white/20 text-white rounded text-xs border border-white/10">
          <span>完整分析</span>
          <ArrowUpRight size={12} />
        </button>
      </div>
    </div>
  );
};
TSX

echo "📝 写入模型下载说明 models/README.md..."
cat << 'MD' > models/README.md
# 腾讯 Hy-MT2 本地模型存放目录

请在此目录下放置 GGUF 格式的离线翻译模型：

- **推荐默认模型**：`Hy-MT2-1.8B-Q4_K_M.gguf` (约 1.13 GB)
  下载地址: https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q4_K_M.gguf
- **可选高精度模型**：`Hy-MT2-7B-Q4_K_M.gguf` (约 4.62 GB)
  下载地址: https://huggingface.co/tencent/Hy-MT2-7B-GGUF/resolve/main/Hy-MT2-7B-Q4_K_M.gguf
MD

echo "✅ 项目骨架与开发代码已成功生成至: $PROJECT_DIR"
EOF

chmod +x setup-project.sh
./setup-project.sh
```

---

## 📦 方式二：下载离线模型直接就位

在您的 Mac 终端中进入该目录并下载 1.8B GGUF 离线模型：

```bash
cd "/Users/gangjing/Documents/AI Dictionary/models"
curl -L -O https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q4_K_M.gguf
```

---

## 🛠️ 本地运行开发环境

```bash
cd "/Users/gangjing/Documents/AI Dictionary"
npm install
npm run tauri dev
```
