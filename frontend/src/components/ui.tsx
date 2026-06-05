// Reusable UI components
import React from "react";
import { View, Text, TouchableOpacity, StyleSheet, ViewStyle, TextStyle, TextInput, TextInputProps, ActivityIndicator } from "react-native";
import { colors, radius, spacing, shadow } from "@/src/theme";
import { Ionicons } from "@expo/vector-icons";

export function Card({ children, style, testID }: { children: React.ReactNode; style?: ViewStyle; testID?: string }) {
  return (
    <View testID={testID} style={[styles.card, style]}>
      {children}
    </View>
  );
}

export function SectionTitle({ children, style, action, testID }: { children: React.ReactNode; style?: TextStyle; action?: React.ReactNode; testID?: string }) {
  return (
    <View style={styles.sectionRow}>
      <Text testID={testID} style={[styles.sectionTitle, style]}>{children}</Text>
      {action}
    </View>
  );
}

export function Overline({ children, color }: { children: React.ReactNode; color?: string }) {
  return <Text style={[styles.overline, color ? { color } : null]}>{children}</Text>;
}

export function Stat({ label, value, valueColor, testID, sub }: { label: string; value: string; valueColor?: string; testID?: string; sub?: string }) {
  return (
    <View style={styles.stat} testID={testID}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={[styles.statValue, valueColor ? { color: valueColor } : null]}>{value}</Text>
      {sub ? <Text style={styles.statSub}>{sub}</Text> : null}
    </View>
  );
}

type ButtonVariant = "primary" | "danger" | "outline" | "ghost" | "success";
export function Button({
  title, onPress, variant = "primary", loading, disabled, icon, testID, style,
}: {
  title: string;
  onPress: () => void;
  variant?: ButtonVariant;
  loading?: boolean;
  disabled?: boolean;
  icon?: keyof typeof Ionicons.glyphMap;
  testID?: string;
  style?: ViewStyle;
}) {
  const palettes: Record<ButtonVariant, { bg: string; text: string; border?: string }> = {
    primary: { bg: colors.primary, text: colors.white },
    danger: { bg: colors.danger, text: colors.white },
    success: { bg: colors.success, text: colors.white },
    outline: { bg: colors.white, text: colors.textPrimary, border: colors.border },
    ghost: { bg: "transparent", text: colors.primary },
  };
  const p = palettes[variant];
  return (
    <TouchableOpacity
      testID={testID}
      onPress={onPress}
      disabled={disabled || loading}
      activeOpacity={0.85}
      style={[
        styles.button,
        { backgroundColor: p.bg, borderColor: p.border ?? "transparent", borderWidth: p.border ? 1 : 0 },
        (disabled || loading) && { opacity: 0.5 },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={p.text} />
      ) : (
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          {icon ? <Ionicons name={icon} size={18} color={p.text} /> : null}
          <Text style={[styles.buttonText, { color: p.text }]}>{title}</Text>
        </View>
      )}
    </TouchableOpacity>
  );
}

export function Badge({ children, variant = "demo", testID }: { children: React.ReactNode; variant?: "demo" | "real" | "success" | "danger" | "warning" | "neutral"; testID?: string }) {
  const map: Record<string, { bg: string; color: string; border: string }> = {
    demo: { bg: colors.demoModeBg, color: colors.demoMode, border: "#BFDBFE" },
    real: { bg: colors.realModeBg, color: colors.realMode, border: "#FCD34D" },
    success: { bg: colors.successBg, color: colors.success, border: "#A7F3D0" },
    danger: { bg: colors.dangerBg, color: colors.danger, border: "#FECACA" },
    warning: { bg: colors.warningBg, color: colors.warning, border: "#FCD34D" },
    neutral: { bg: colors.surfaceAlt, color: colors.textSecondary, border: colors.border },
  };
  const s = map[variant];
  return (
    <View testID={testID} style={[styles.badge, { backgroundColor: s.bg, borderColor: s.border }]}>
      <Text style={[styles.badgeText, { color: s.color }]}>{children}</Text>
    </View>
  );
}

export function Input(props: TextInputProps & { label?: string; testID?: string }) {
  const { label, style, testID, ...rest } = props;
  return (
    <View style={{ marginBottom: spacing.md }}>
      {label ? <Text style={styles.inputLabel}>{label}</Text> : null}
      <TextInput
        testID={testID}
        placeholderTextColor={colors.textMuted}
        style={[styles.input, style]}
        {...rest}
      />
    </View>
  );
}

export function Divider() {
  return <View style={{ height: 1, backgroundColor: colors.border, marginVertical: spacing.md }} />;
}

export function EmptyState({ icon = "document-text-outline", title, subtitle, testID }: { icon?: keyof typeof Ionicons.glyphMap; title: string; subtitle?: string; testID?: string }) {
  return (
    <View style={styles.empty} testID={testID}>
      <Ionicons name={icon} size={42} color={colors.textMuted} />
      <Text style={styles.emptyTitle}>{title}</Text>
      {subtitle ? <Text style={styles.emptySub}>{subtitle}</Text> : null}
    </View>
  );
}

export function Sparkline({ values, height = 40, color = colors.primary }: { values: number[]; height?: number; color?: string }) {
  if (!values || values.length < 2) {
    return <View style={{ height }} />;
  }
  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = max - min || 1;
  const last = values.length;
  return (
    <View style={{ flexDirection: "row", alignItems: "flex-end", height, gap: 1 }}>
      {values.map((v, i) => {
        const h = ((v - min) / range) * height;
        return <View key={i} style={{ flex: 1, height: Math.max(2, h), backgroundColor: color, opacity: 0.4 + (i / last) * 0.6, borderRadius: 1 }} />;
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.white,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.md,
    ...shadow.sm,
  },
  sectionRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: spacing.sm,
    marginTop: spacing.md,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: colors.textPrimary,
    letterSpacing: -0.3,
  },
  overline: {
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 2,
    color: colors.textSecondary,
  },
  stat: { flex: 1 },
  statLabel: {
    fontSize: 11,
    color: colors.textSecondary,
    textTransform: "uppercase",
    letterSpacing: 1.5,
    marginBottom: 4,
    fontWeight: "600",
  },
  statValue: {
    fontSize: 22,
    fontWeight: "800",
    color: colors.textPrimary,
    letterSpacing: -0.5,
  },
  statSub: {
    fontSize: 12,
    color: colors.textMuted,
    marginTop: 2,
  },
  button: {
    paddingVertical: 14,
    paddingHorizontal: 18,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 48,
  },
  buttonText: {
    fontSize: 15,
    fontWeight: "700",
    letterSpacing: 0.2,
  },
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 100,
    borderWidth: 1,
    alignSelf: "flex-start",
  },
  badgeText: {
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 1,
    textTransform: "uppercase",
  },
  inputLabel: {
    fontSize: 12,
    fontWeight: "600",
    color: colors.textSecondary,
    marginBottom: 6,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  input: {
    backgroundColor: colors.white,
    borderColor: colors.borderStrong,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    color: colors.textPrimary,
    minHeight: 48,
  },
  empty: {
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.xl,
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: "700",
    color: colors.textPrimary,
    marginTop: spacing.md,
  },
  emptySub: {
    fontSize: 13,
    color: colors.textSecondary,
    marginTop: 4,
    textAlign: "center",
  },
});
