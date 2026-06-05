// Trading Bot - Theme (adapté du design_guidelines.json en StyleSheet React Native)
export const colors = {
  primary: "#002FA7",
  primaryHover: "#002280",
  background: "#FFFFFF",
  surface: "#F8FAFC",
  surfaceAlt: "#F1F5F9",
  textPrimary: "#0F172A",
  textSecondary: "#64748B",
  textMuted: "#94A3B8",
  border: "#E2E8F0",
  borderStrong: "#CBD5E1",
  success: "#10B981",
  successBg: "#D1FAE5",
  danger: "#EF4444",
  dangerHover: "#DC2626",
  dangerBg: "#FEE2E2",
  warning: "#F59E0B",
  warningBg: "#FEF3C7",
  demoMode: "#3B82F6",
  demoModeBg: "#DBEAFE",
  realMode: "#F59E0B",
  realModeBg: "#FEF3C7",
  killSwitch: "#EF4444",
  killSwitchActive: "#B91C1C",
  white: "#FFFFFF",
  black: "#000000",
};

export const radius = {
  sm: 6,
  md: 8,
  lg: 12,
  xl: 16,
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const fonts = {
  // Using system fonts since Cabinet Grotesk / IBM Plex Sans not installed
  heading: undefined as string | undefined,
  body: undefined as string | undefined,
  mono: "Courier",
};

export const shadow = {
  sm: {
    shadowColor: colors.black,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  md: {
    shadowColor: colors.black,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 2,
  },
  lg: {
    shadowColor: colors.black,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.12,
    shadowRadius: 12,
    elevation: 4,
  },
};

export const fmt = {
  money: (v: number | null | undefined, currency = "USD") => {
    if (v === null || v === undefined || isNaN(v)) return "—";
    const sign = v < 0 ? "-" : "";
    const abs = Math.abs(v);
    return `${sign}${abs.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
  },
  pct: (v: number | null | undefined, decimals = 2) => {
    if (v === null || v === undefined || isNaN(v)) return "—";
    return `${v.toFixed(decimals)}%`;
  },
  price: (v: number | null | undefined, decimals = 5) => {
    if (v === null || v === undefined || isNaN(v)) return "—";
    return v.toFixed(decimals);
  },
};
