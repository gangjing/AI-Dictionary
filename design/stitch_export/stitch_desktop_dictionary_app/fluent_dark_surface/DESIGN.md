---
name: Fluent Dark Surface
colors:
  surface: '#131313'
  surface-dim: '#131313'
  surface-bright: '#393939'
  surface-container-lowest: '#0e0e0e'
  surface-container-low: '#1b1c1c'
  surface-container: '#202020'
  surface-container-high: '#2a2a2a'
  surface-container-highest: '#353535'
  on-surface: '#e5e2e1'
  on-surface-variant: '#bdc8cf'
  inverse-surface: '#e5e2e1'
  inverse-on-surface: '#303030'
  outline: '#889299'
  outline-variant: '#3e484e'
  surface-tint: '#74d1ff'
  primary: '#b4e4ff'
  on-primary: '#003548'
  primary-container: '#60cdff'
  on-primary-container: '#005572'
  inverse-primary: '#006687'
  secondary: '#8fcff0'
  on-secondary: '#003548'
  secondary-container: '#025976'
  on-secondary-container: '#8fcef0'
  tertiary: '#c0e1ff'
  on-tertiary: '#003450'
  tertiary-container: '#85c8fd'
  on-tertiary-container: '#00547d'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#c1e8ff'
  primary-fixed-dim: '#74d1ff'
  on-primary-fixed: '#001e2b'
  on-primary-fixed-variant: '#004d67'
  secondary-fixed: '#c1e8ff'
  secondary-fixed-dim: '#8fcff0'
  on-secondary-fixed: '#001e2b'
  on-secondary-fixed-variant: '#004d66'
  tertiary-fixed: '#cbe6ff'
  tertiary-fixed-dim: '#8fcdff'
  on-tertiary-fixed: '#001e30'
  on-tertiary-fixed-variant: '#004b71'
  background: '#131313'
  on-background: '#e5e2e1'
  surface-variant: '#353535'
typography:
  display:
    fontFamily: Segoe UI Variable, Inter, sans-serif
    fontSize: 40px
    fontWeight: '600'
    lineHeight: 52px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Segoe UI Variable, Inter, sans-serif
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.015em
  headline-lg-mobile:
    fontFamily: Segoe UI Variable, Inter, sans-serif
    fontSize: 26px
    fontWeight: '600'
    lineHeight: 34px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Segoe UI Variable, Inter, sans-serif
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Segoe UI Variable, Inter, sans-serif
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Segoe UI Variable, Inter, sans-serif
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Segoe UI Variable, Inter, sans-serif
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Segoe UI Variable, Inter, sans-serif
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-md:
    fontFamily: Segoe UI Variable, Inter, sans-serif
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  label-sm:
    fontFamily: Segoe UI Variable, Inter, sans-serif
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  caption:
    fontFamily: Segoe UI Variable, Inter, sans-serif
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 14px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1rem
  margin: 1.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system expresses the quiet authority, tactile craftsmanship, and desktop-grade precision of Windows 11 Fluent Design. Crafted for intensive modern productivity, creative suites, and native system applications, it balances utility with high aesthetic restraint.

Key visual pillars:
- **Atmospheric Materials:** Translucent, blurred backdrops (Mica Alt and Acrylic) let the underlying canvas or desktop context bleed subtly through without sacrificing contrast.
- **Layered Hierarchy:** Spatial depth is achieved through quiet tonal stepping rather than aggressive drop shadows.
- **Precise Geometry:** Measured 8px corner radii harmonize soft modernism with structural utility.
- **Micro-detail Light Borders:** Hairline inner strokes (1px with 8% white opacity) simulate top-lit bevel edges common in native glass and slate surfaces.

## Colors

The palette is engineered around dark surfaces with high legibility and precise visual grouping.

### Palette Architecture
- **Primary Accent (`#60cdff`):** Windows 11 Fluent Accent Blue tuned for dark mode. Used for high-priority interactive states, focus rings, progress tracks, active indicators, and critical primary buttons.
- **Secondary Accent (`#9cdcfe`):** Lighter tint for hover states and secondary active accents.
- **Tertiary Accent (`#76b9ed`):** Deeper tint for pressed states and active selection backgrounds in soft mode.
- **Neutral Canvas (`#202020`):** Solid base window canvas when backdrop materials are inactive or unsupported.

### Layered Surface Hierarchy
- **Canvas Base / Mica (`#202020`):** Window backdrop level.
- **Layer 1 / Surface Container Default (`#2b2b2b`):** Side navigation, toolbars, and grouped card containers.
- **Layer 2 / Surface Container High (`#323232`):** Flyouts, elevated dialogs, context menus, and elevated input controls.
- **Hairline Strokes:** `rgba(255, 255, 255, 0.08)` applied universally on containers to separate dark layers cleanly.

## Typography

Typography prioritizes maximum scan-efficiency and optical balance.

- Primary typeface is `Segoe UI Variable`, falling back seamlessly to `Inter` for web/cross-platform parity.
- Font hierarchy employs tight line height ratios suitable for information-dense desktop interfaces.
- Headings use optical negative tracking (`-0.01em` to `-0.02em`) to maintain tightness at larger scale.
- Body copy adheres strictly to a 14px default baseline (`body-md`), standard in desktop system software.

## Layout & Spacing

The layout model uses a disciplined 4px / 8px grid foundation tailored for multi-pane application windows, master-detail interfaces, and responsive panels.

### Layout Grid Structure
- **Desktop (>= 1024px):** Fixed or collapsable side rail (48px collapsed, 240px expanded) paired with a fluid content area with 16px gutters and 24px margins.
- **Tablet (641px - 1023px):** Overlay navigation drawer, 16px gutters, 16px page margins.
- **Mobile (<= 640px):** Single-column stacked layout, bottom navigation bar or pivot tabs, 12px gutters, 12px outer canvas margins.

## Elevation & Depth

Visual hierarchy uses physical material properties, backdrop blurs, and surface illumination rather than deep drop shadows.

### Material Stack
1. **Mica Alt Window Base:** Canvas layer with ambient desktop blur (`backdrop-filter: blur(30px) saturate(125%)`) and neutral `#202020` base tint.
2. **Layer 1 Surface (`#2b2b2b`):** Subordinate cards and sections. Framed by a subtle top-lit inner border `1px solid rgba(255, 255, 255, 0.08)`.
3. **Layer 2 Acrylic Surface (`#323232` with 85% opacity):** Applied to floating flyouts, context menus, tooltips, and modal sheets (`backdrop-filter: blur(40px)`).

### Shadows
- **Base Components & In-line Cards:** No cast shadow; differentiation relies solely on `#2b2b2b` fill and the `1px rgba(255,255,255,0.08)` border stroke.
- **Floating Modals & Menus:** Ambient diffused drop shadow: `0 8px 16px rgba(0, 0, 0, 0.28), 0 0 2px rgba(0, 0, 0, 0.12)`.

## Shapes

The geometric rule follows Fluent Design's unified 8px radius standard:
- Standard controls (Buttons, Text Inputs, Segmented Pickers, Dropdowns) use `roundedness: 2` (8px).
- Internal items within lists, breadcrumb nodes, and tabs mirror the outer rounding at 4px-6px to maintain concentric nested radiuses.
- Modal dialogues and master flyout panels scale to 12px-16px (`rounded-lg` / `rounded-xl`).

## Components

### Buttons
- **Accent Primary:** Background `#60cdff`, text `#000000` (high contrast black), 8px radius, height 32px. Hover state changes background to `#9cdcfe`. Active/pressed state deepens to `#76b9ed`.
- **Standard Neutral:** Background `rgba(255, 255, 255, 0.06)`, border `1px solid rgba(255, 255, 255, 0.08)`, text `#ffffff`. Hover: `rgba(255, 255, 255, 0.09)`. Pressed: `rgba(255, 255, 255, 0.04)`.
- **Subtle (Ghost):** Transparent background. Hover: `rgba(255, 255, 255, 0.06)`.

### Input Fields & Controls
- **Text Inputs:** Height 32px, background `#2b2b2b`, 8px radius, border `1px solid rgba(255, 255, 255, 0.08)`. On focus, border transitions to a 2px bottom accent highlight in `#60cdff` with an active glow border.
- **Checkboxes & Radios:** 18px size, border `1px solid rgba(255, 255, 255, 0.35)`, 4px radius for checkbox, full circular for radio. Checked state fills with `#60cdff` with `#000000` check glyph.

### Cards & Grouping
- **Surface Cards:** Background `#2b2b2b`, border `1px solid rgba(255, 255, 255, 0.08)`, border-radius 8px, padding 16px.
- **Interactive Action Cards:** Same base styling, transitioning on hover to `#323232` with border lightened to `rgba(255, 255, 255, 0.12)`.

### Lists & Navigation Rails
- **Navigation Items:** Height 36px, horizontal padding 12px, border-radius 6px.
- **Active State:** Left edge hosts an animated 3px vertical accent pill in `#60cdff`, background set to `rgba(255, 255, 255, 0.06)`.
- **Dividers:** `1px solid rgba(255, 255, 255, 0.06)`, inset by 12px from container edges.