---
name: Sonoma Native Intelligence
colors:
  surface: '#131315'
  surface-dim: '#131315'
  surface-bright: '#39393b'
  surface-container-lowest: '#0e0e10'
  surface-container-low: '#1b1b1d'
  surface-container: '#1f1f21'
  surface-container-high: '#2a2a2c'
  surface-container-highest: '#353437'
  on-surface: '#e4e2e4'
  on-surface-variant: '#c1c6d7'
  inverse-surface: '#e4e2e4'
  inverse-on-surface: '#303032'
  outline: '#8b90a0'
  outline-variant: '#414755'
  surface-tint: '#adc6ff'
  primary: '#adc6ff'
  on-primary: '#002e69'
  primary-container: '#4b8eff'
  on-primary-container: '#00285c'
  inverse-primary: '#005bc1'
  secondary: '#c2c1ff'
  on-secondary: '#1c0b9f'
  secondary-container: '#3834b6'
  on-secondary-container: '#b2b1ff'
  tertiary: '#61d6ee'
  on-tertiary: '#00363f'
  tertiary-container: '#059fb5'
  on-tertiary-container: '#002f37'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc6ff'
  on-primary-fixed: '#001a41'
  on-primary-fixed-variant: '#004493'
  secondary-fixed: '#e2dfff'
  secondary-fixed-dim: '#c2c1ff'
  on-secondary-fixed: '#0c006a'
  on-secondary-fixed-variant: '#3631b4'
  tertiary-fixed: '#a5eeff'
  tertiary-fixed-dim: '#61d6ee'
  on-tertiary-fixed: '#001f25'
  on-tertiary-fixed-variant: '#004e5a'
  background: '#131315'
  on-background: '#e4e2e4'
  surface-variant: '#353437'
typography:
  display-term:
    fontFamily: Inter
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.03em
  headline-lg:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 34px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.015em
  headline-sm:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
    letterSpacing: -0.005em
  body-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 19px
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 15px
    letterSpacing: 0.01em
  label-code:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0em
  label-phonetic:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0.02em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-sidebar: 0.75rem
  margin: 1.25rem
  margin-window: 0.75rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style

This design system reflects the precision, tactile tactility, and optical translucency of modern macOS (Sonoma / Sequoia). Engineered specifically for a local-first, Apple Silicon-accelerated AI dictionary and semantic lexicon, the interface prioritizes immediate comprehension, frictionless desktop utility, and uncompromising native fidelity.

The aesthetic fuses Apple's vibrant material vibrancy with an ultra-refined, architectural workspace:
- **Materials over flat surfaces:** Vibrant frosted glass (`backdrop-blur-2xl`), fluid vibrancy passes, and specular edge lighting emulate native AppKit and SwiftUI split-view experiences.
- **Local-first visual sovereignty:** Visual indicators deliberately communicate on-device neural processing (Metal acceleration badges, offline stability tags, zero-network indicators).
- **Pro desktop posture:** Native structural conventions—traffic light window controls, integrated toolbar titlebars, collapsible sidebar navigators, and inset inspector sheets—anchor the application firmly in macOS desktop ergonomics.

## Colors

The color architecture is built directly on macOS system dynamic levels, optimized by default for a rich, deep-slate dark mode with liquid material vibrancy.

### Core System Accents
- **System Blue (`#007AFF`):** Primary interactive accent, key selection states, primary actions, and phonetic audio playback indicators.
- **System Indigo (`#5856D6`):** Secondary semantic accent denoting neural AI synthesis, etymological trees, and semantic similarity clusters.
- **System Teal (`#30B0C7`):** Tertiary indicator reserved for on-device hardware telemetry (Apple Silicon Neural Engine compute, instant query latency).
- **Traffic Light Signifiers:** Close (`#FF5F56`), Minimize (`#FFBD2E`), Zoom (`#27C93F`), rendered with native 12px circular geometry and subtle inset strokes.

### Material & Surface Palette
- **Window Base Surface:** `#161618` with deep ambient pass-through.
- **Translucent Sidebar Fill:** `rgba(28, 28, 30, 0.65)` layered with `backdrop-filter: blur(40px) saturate(190%)`.
- **Active Canvas Surface:** `#1C1C1E` (solid or layered at 85% opacity over window backing).
- **Elevated Popovers & Menus:** `#2C2C2E` with an inner specular ring of `rgba(255, 255, 255, 0.12)`.
- **Separators & Specular Borders:** `rgba(255, 255, 255, 0.08)` on surfaces, elevating to `rgba(255, 255, 255, 0.18)` on active modal dialog borders.

## Typography

Typography adheres strictly to Apple's Human Interface Guidelines typographic scaling, targeting `-apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display"` natively, mapped here with precision metrics via standard optical fallbacks.

- **Display Term (`40px/-0.03em`):** Scaled for primary dictionary lemmas and root definitions, carrying commanding optical weight without bleeding vertically.
- **Headlines & Subheads (`15px–28px`):** Used for categorical semantic partitions (Definitions, Synonyms, Morphological Roots, AI Contextual Embeddings).
- **Body (`13px/19px`):** macOS native standard reading size. Offers supreme legibility across dense etymological texts and comparative contextual usages.
- **Code & Telemetry Labels (`11px JetBrains Mono`):** Dedicated to Apple Silicon vector latency metrics (e.g., `ANE: 1.4ms`, `Float16 CoreML`), grammatic POS tags (`[noun: countable]`), and keyboard command glyphs (`⌘K`, `⌥Return`).

## Layout & Spacing

The structural layout strictly mirrors a standard macOS 3-column or split-view workspace architecture:
- **Titlebar Header (52px fixed height):** Integrates the traffic light controls inset `16px` horizontally, followed by unified toolbar navigation, search capsule, and Neural Engine processing badges.
- **Left Sidebar (220px–280px flexible):** Hosts pinned lexicons, search history, favorite semantic tags, and local model selector.
- **Central Detail Canvas:** Main definition body, vector similarity visualization, and AI context generator.
- **Right Inspector (Optional 260px collapsible):** Houses etymology trees, grammar attributes, and phonetic audio spectrograms.

### Density & Rhythms
A base unit of `4px / 8px` governs all internal element distances. Component gaps within lists maintain compact desktop density (`space-xs` to `space-sm`), while panel viewports breathe using `space-lg` to `space-xl` padding.

## Elevation & Depth

Visual hierarchy is constructed through material density and optical refraction rather than diffuse drop shadows.

- **Level 0 (Desktop Pass-Through):** Translucent vibrancy layer with `backdrop-filter: blur(48px) saturate(200%) brightness(85%)`. The OS wallpaper subtly bleeds through without interfering with text contrast.
- **Level 1 (Window Content Panels):** Semi-opaque background (`rgba(30, 30, 32, 0.78)`) overlaid with an outer 1px high-resolution rim border (`rgba(255, 255, 255, 0.08)`).
- **Level 2 (Floating Popovers & Flyout Menus):** Background `#28282A` with dual-stage edge lighting: an inner highlight of `inset 0 1px 0 rgba(255, 255, 255, 0.14)` and a deep ambient drop-shadow: `0 18px 38px rgba(0, 0, 0, 0.45), 0 4px 12px rgba(0, 0, 0, 0.25)`.
- **Level 3 (Modal Sheets):** Inset drops falling from the native top titlebar with a 1px boundary of `rgba(255, 255, 255, 0.22)`.

## Shapes

The design system incorporates Apple's continuous curvature (squircle geometry) throughout:
- **Window Enclosure:** `20px` to `24px` outer radius (macOS Sonoma standard frame).
- **Floating Controls & Segmented Pickers:** `rounded-lg` (`8px` to `10px`), providing comfortable mechanical tactility.
- **Search Capsules & Badge Pills:** Full pill-geometry (`9999px`) for search fields, phonetic pronunciation pills, and on-device compute chips.
- **Selection Highlights:** `6px` radius on sidebar list item hover and selection backings.

## Components

### Titlebar & Window Controls
- **Traffic Lights:** Three 12px circular controls aligned `14px` from top and left. Close (`#FF5F56`), Minimize (`#FFBD2E`), Zoom (`#27C93F`), displaying native symbol glyphs (`×`, `−`, `+`) exclusively on group hover.
- **Integrated Search Capsule:** 32px height, pill-shaped input positioned centrally or in the toolbar. Features a leading macOS magnifying glass glyph, placeholder text in `body-md`, and a trailing `⌘K` keyboard shortcut badge.

### Segmented Controls & Buttons
- **macOS Segmented Control:** Encapsulated capsule container in `rgba(0, 0, 0, 0.25)` with a sliding white/subtle-gray pill pill-thumb (`rgba(255, 255, 255, 0.14)`) carrying an inset border and micro-shadow.
- **Primary Action Buttons:** Filled with `#007AFF`, white label, 1px top edge specular highlight `rgba(255, 255, 255, 0.25)`, scaling slightly down (`scale(0.98)`) on physical click.
- **Ghost/Icon Toolbars:** 28x28px squircle targets with hover state `rgba(255, 255, 255, 0.08)`.

### Lists & Navigation
- **Sidebar Rows:** 28px height, 6px corner radius. Selected row uses active accent `#007AFF` (or vibrant translucent white `rgba(255, 255, 255, 0.12)` when window is unfocused), accompanied by SF Pro-styled monochrome icons.

### Badges & Hardware Telemetry
- **Apple Silicon Status Tag:** Pill badge displaying a micro microchip icon, label `M-Series Local Neural Engine`, and a glowing Teal dot (`#30B0C7`) certifying zero cloud ingress/egress.
- **Etymological Pills:** Subtle dark slate backdrop `rgba(255, 255, 255, 0.06)` with refined `label-code` typography.

### Form Inputs & Switches
- **Native macOS Toggle Switch:** Pill toggle with green fill (`#34C759`) on active, moving an opaque white circular thumb with soft directional shadow.