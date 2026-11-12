---
name: Fluent Lexicon
colors:
  surface: '#fbf9f8'
  surface-dim: '#dbdad9'
  surface-bright: '#fbf9f8'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f5f3f3'
  surface-container: '#efeded'
  surface-container-high: '#e9e8e7'
  surface-container-highest: '#e4e2e2'
  on-surface: '#1b1c1c'
  on-surface-variant: '#414752'
  inverse-surface: '#303030'
  inverse-on-surface: '#f2f0f0'
  outline: '#717783'
  outline-variant: '#c1c6d4'
  surface-tint: '#005eb1'
  primary: '#004f96'
  on-primary: '#ffffff'
  primary-container: '#0067c0'
  on-primary-container: '#dbe7ff'
  inverse-primary: '#a6c8ff'
  secondary: '#0060ab'
  on-secondary: '#ffffff'
  secondary-container: '#4ca0ff'
  on-secondary-container: '#003664'
  tertiary: '#00585e'
  on-tertiary: '#ffffff'
  tertiary-container: '#00727a'
  on-tertiary-container: '#93f5ff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d5e3ff'
  primary-fixed-dim: '#a6c8ff'
  on-primary-fixed: '#001c3b'
  on-primary-fixed-variant: '#004787'
  secondary-fixed: '#d3e3ff'
  secondary-fixed-dim: '#a3c9ff'
  on-secondary-fixed: '#001c39'
  on-secondary-fixed-variant: '#004883'
  tertiary-fixed: '#7ff4ff'
  tertiary-fixed-dim: '#4bd9e5'
  on-tertiary-fixed: '#002022'
  on-tertiary-fixed-variant: '#004f55'
  background: '#fbf9f8'
  on-background: '#1b1c1c'
  surface-variant: '#e4e2e2'
typography:
  display:
    fontFamily: Segoe UI Variable
    fontSize: 40px
    fontWeight: '600'
    lineHeight: 52px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Segoe UI Variable
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.015em
  headline-lg-mobile:
    fontFamily: Segoe UI Variable
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Segoe UI Variable
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  headline-sm:
    fontFamily: Segoe UI Variable
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 22px
  phonetic-ipa:
    fontFamily: Segoe UI Variable
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0.02em
  body-lg:
    fontFamily: Segoe UI Variable
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
  body-md:
    fontFamily: Segoe UI Variable
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Segoe UI Variable
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  pos-tag:
    fontFamily: Segoe UI Variable
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.04em
  mono-metric:
    fontFamily: Segoe UI Variable
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.01em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 0.75rem
  gutter-desktop: 1rem
  margin: 1rem
  margin-desktop: 1.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system embodies the Microsoft Fluent Design System language tailored for native, offline-first local intelligence. Built for an on-device neural translator and linguistic dictionary powered by Hy-MT2 and a local SQLite database, the design communicates precision, absolute privacy, immediate responsiveness, and modern desktop refinement.

The experience fuses two primary visual tenets:
- **Fluent Desktop Modernism:** Translucent Mica/Acrylic surfaces that sample the user's desktop canvas or window backdrop, delicate 1px light-reactive containment borders, authentic Windows 11 window controls, and calm, unhurried typography.
- **Cognitive Clarity:** Dense lexical information—IPA transcriptions, inflections, etymologies, and semantic clusters—organized into frictionless visual hierarchies that prevent mental fatigue.

The emotional signature is instantaneous, dependable, and whisper-quiet: an offline cognitive instrument that feels as integral to the desktop as the operating system shell itself.

## Colors

The palette directly honors the Windows 11 Fluent aesthetic, emphasizing layered grays, ambient light strokes, and luminous telemetry accents.

- **Primary Accent (`#0067c0` / `#0078d4`):** Authentic Microsoft Fluent System Blue, used for primary actions, focused stroke states, and active linguistic anchors.
- **Tertiary Cyan/Teal (`#00b7c3`):** Reserved for on-device AI runtime telemetry, local model inference badges (Hy-MT2 1.8B Q4), and instant vector lookup status.
- **Canvas Base (`#f3f3f3` light / `#202020` dark):** Natural Mica smoke background supporting depth through translucent overlay layers (`#ffffff` at variable opacity for cards and elevated dialogs).
- **Text & Foreground:** Primary text sits at `#1a1a1a` (90% optical contrast against canvas), secondary lexical context at `#5e5e5e`, and muted phonetic brackets/POS markers at `#767676`.
- **System States:** Subtle mint green (`#107c41`) for offline private security indicators and amber (`#d83b01`) for dictionary update notices.

## Typography

The typographic hierarchy relies on **Segoe UI Variable** (with fallback to `Segoe UI`, `Inter`, and system sans-serif), employing its optical sizing axes (`Display`, `Text`, and `Small`) to maintain razor-sharp legibility across desktop scaling factors (100% to 200% DPI).

- **Headwords (`display`, `headline-lg`):** Strong, clean weight (`600`) with tight letter spacing for dictionary headwords and target language equivalents.
- **IPA Phonetics (`phonetic-ipa`):** Sized and spaced specifically to avoid clipping Unicode tonal contour markers, diacritics, and stress ticks (`ˈ`, `ˌ`, `θ`, `ð`, `ŋ`).
- **POS Badges (`pos-tag`):** Rendered in uppercase/semi-bold styling for rapid visual anchoring during vertical scannability (`N.`, `V.`, `ADJ.`, `ADV.`).
- **Telemetry & Engine Readouts (`mono-metric`):** Designed for real-time local compute stats (`Hy-MT2 1.8B Q4`, `0.0ms DB SQLite`).

## Layout & Spacing

The layout model simulates a desktop utility shell featuring an asymmetric, split-view pane structure:
- **Left Navigation & Query Rail (Fixed 320px–360px):** Search bar, quick history, offline model toggle, and frequency lists.
- **Primary Content Viewport (Fluid):** Dynamic definition stream, neural example generator, syntax tree, and localized synonyms.
- **Integrated Acrylic Window Frame:** An edge-to-edge top bar (36px–40px height) hosting window drag affordances, breadcrumbs, local offline privacy badges, and native Windows 11 Min/Max/Close glyph buttons.

Adapts gracefully from compact popover mode (400px width for global hotkey quick-lookup) to multi-column desktop workstation layout (1200px+ width with simultaneous comparative definitions and local context cards).

## Elevation & Depth

Fluent elevation is produced through **material composition and compound strokes**, never opaque heavy drop shadows:

1. **Mica Base (Canvas Layer):** The master canvas foundation. Incorporates high-performance native wallpaper bleed-through (`backdrop-filter: blur(30px) saturate(125%)`) with 85% opacity tint.
2. **Layered Card Elevation (Acrylic Substrate):** Elevated surfaces (`#ffffff` at 70% opacity in light mode, `#2d2d2d` at 80% in dark mode) sit atop Mica.
3. **Compound Fluent Border System:** Components use a dual 1px perimeter border composed of:
   - Top edge: `rgba(255, 255, 255, 0.45)` for top-down simulated lighting.
   - Sides and bottom: `rgba(0, 0, 0, 0.08)` for precise optical containment.
4. **Elevation Shadows:**
   - **Resting:** `0px 2px 4px rgba(0, 0, 0, 0.04), 0px 0px 1px rgba(0, 0, 0, 0.08)`
   - **Interactive / Flyout Search:** `0px 8px 16px rgba(0, 0, 0, 0.08), 0px 2px 4px rgba(0, 0, 0, 0.04)`

## Shapes

In strict harmony with Windows 11 design guidelines, shapes adhere to a disciplined **8px to 12px** geometry:
- Standard control elements (text fields, lexical cards, button controls): **8px** (`rounded-md` / level 2 base).
- Flyout dialogs, search modal overlays, and elevated definition containers: **12px** (`rounded-lg`).
- Lexical POS badges, phonetic chips, and system status indicators: **Full pill shape** (`9999px`) to create clear differentiation against structured square cards.

## Components

### Title Bar & Desktop Controls
- **Window Bar:** Unobtrusive, 38px height, integrated Mica background. Houses the application icon, centered model status pill, and native Windows control buttons on the far right.
- **Window Controls:** 46px wide interactive hits. Close button transitions to `#c42b1c` with white glyph on hover; Minimize/Maximize use `#0000000a` subtle hover states.

### Search Input Bar
- **Surface:** `#ffffff` (light mode) with a 1px compound border (`#00000012` base) transitioning to a 2px `#0067c0` bottom accent stroke on focus.
- **Leading & Trailing Accessories:** Fluent search glyph (`Segoe Fluent Icons` or vector symbol) on the left; instant shortcut indicator (`Ctrl + Space`) and clear button on the right.

### Definition & Inflection Cards
- **Structure:** Light acrylic background with 8px radius, padded with `space-lg` (16px).
- **Headword Header:** Accompanied by inline audio phonetic speaker button (28px circle button, transparent with light-blue hover state) and pill tags.
- **Divider:** Subtle `1px solid rgba(0, 0, 0, 0.06)` horizontal separator.

### Part of Speech (POS) Badges & Phonetic Chips
- **Noun / Verb / Adj Badges:** Pill-shaped tags (`roundedness: 3`) with muted tints:
  - *Noun:* Pale blue fill (`#ebf3fc`), navy text (`#005fb8`).
  - *Verb:* Soft teal fill (`#e6f7f8`), dark teal text (`#006e75`).
  - *Adj:* Neutral warm gray fill (`#f0f0f0`), slate text (`#444444`).
- **Phonetics:** Muted italic container with subtle bracket glyphs `[ ]` and single-click to copy pronunciation.

### Neural Engine Status Indicator (Hy-MT2 1.8B)
- **Local Engine Capsule:** Compact pill in the status bar or title frame.
- **Visuals:** 6px glowing green or cyan dot (`#107c41`), followed by `Hy-MT2 1.8B Q4 • 0ms Local`. Hover reveals a lightweight flyout showing active SQLite word count (e.g., `842,109 entries`) and absolute offline zero-telemetry guarantee.

### Buttons & Selection Controls
- **Accent Button:** `#0067c0` solid background, white text, 8px border radius, subtle inner white highlight border.
- **Subtle / Ghost Button:** Transparent background, visible 1px light outline on hover, used for secondary dictionary filters and bookmark actions.