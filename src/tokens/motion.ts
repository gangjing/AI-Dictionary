// AI Dictionary — Design System & Physics Motion Tokens (Stitch Design Spec v1.0)
// Matches Windows 11 Fluent Motion Engine (WinUI 3) & macOS Sonoma/Sequoia Liquid Glass

export const FLUENT_MOTION = {
  spring: { stiffness: 420, damping: 0.82, mass: 1.0 },
  duration: { hudEntry: 120, dismiss: 80, windowMorph: 500 },
  curves: { fluentSpring: 'cubic-bezier(0.16, 1.0, 0.3, 1.0)' },
} as const;

export const MACOS_MOTION = {
  spring: { stiffness: 380, damping: 0.78, mass: 1.0 },
  duration: { popoverDrop: 240, quickDismiss: 80, heroExpansion: 600 },
  curves: { liquidFluid: 'cubic-bezier(0.2, 0.9, 0.2, 1.0)' },
} as const;

export const SONOMA_COLORS = {
  surface: '#131315',
  surfaceDim: '#131315',
  surfaceBright: '#39393b',
  surfaceContainerLowest: '#0e0e10',
  surfaceContainerLow: '#1b1b1d',
  surfaceContainer: '#1f1f21',
  surfaceContainerHigh: '#2a2a2c',
  surfaceContainerHighest: '#353437',
  onSurface: '#e4e2e4',
  onSurfaceVariant: '#c1c6d7',
  outline: '#8b90a0',
  outlineVariant: '#414755',
  primary: '#adc6ff',
  primaryContainer: '#4b8eff',
  secondary: '#c2c1ff',
  tertiary: '#61d6ee',
  trafficLights: {
    close: '#FF5F56',
    minimize: '#FFBD2E',
    zoom: '#27C93F',
  },
} as const;

export const FLUENT_COLORS = {
  surfaceLight: '#fbf9f8',
  surfaceDark: '#131313',
  cardDark: '#202020',
  primaryBlue: '#0067c0',
  accentCyan: '#60cdff',
  telemetryTeal: '#00727a',
  offlineGreen: '#107c41',
} as const;
