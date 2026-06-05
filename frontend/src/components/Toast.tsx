// Toast notification system
import React, { createContext, useContext, useState, useCallback, ReactNode, useEffect } from "react";
import { View, Text, StyleSheet, Animated, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius, spacing, shadow } from "@/src/theme";
import { useSafeAreaInsets } from "react-native-safe-area-context";

type ToastType = "success" | "info" | "danger" | "warning";

export type Toast = {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;
};

type ToastCtx = {
  show: (t: Omit<Toast, "id">) => void;
};

const Ctx = createContext<ToastCtx | undefined>(undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const insets = useSafeAreaInsets();

  const show = useCallback((t: Omit<Toast, "id">) => {
    const id = String(Date.now()) + Math.random().toString(36).slice(2);
    const toast = { ...t, id };
    setToasts((cur) => [...cur, toast]);
    const dur = t.duration ?? 4000;
    setTimeout(() => {
      setToasts((cur) => cur.filter((x) => x.id !== id));
    }, dur);
  }, []);

  return (
    <Ctx.Provider value={{ show }}>
      {children}
      <View style={[styles.container, { top: insets.top + 8 }]} pointerEvents="box-none">
        {toasts.map((t) => <ToastItem key={t.id} toast={t} onDismiss={() => setToasts((c) => c.filter((x) => x.id !== t.id))} />)}
      </View>
    </Ctx.Provider>
  );
}

export function useToast() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useToast must be inside ToastProvider");
  return c;
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const opacity = React.useRef(new Animated.Value(0)).current;
  const translateY = React.useRef(new Animated.Value(-20)).current;
  useEffect(() => {
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 220, useNativeDriver: true }),
      Animated.timing(translateY, { toValue: 0, duration: 220, useNativeDriver: true }),
    ]).start();
  }, []);

  const config = {
    success: { bg: colors.successBg, border: "#A7F3D0", icon: "checkmark-circle" as const, color: colors.success },
    info: { bg: colors.demoModeBg, border: "#BFDBFE", icon: "information-circle" as const, color: colors.demoMode },
    danger: { bg: colors.dangerBg, border: "#FECACA", icon: "alert-circle" as const, color: colors.danger },
    warning: { bg: colors.warningBg, border: "#FCD34D", icon: "warning" as const, color: colors.warning },
  }[toast.type];

  return (
    <Animated.View style={[styles.toast, { backgroundColor: config.bg, borderColor: config.border, opacity, transform: [{ translateY }] }]} testID={`toast-${toast.type}`}>
      <Ionicons name={config.icon} size={18} color={config.color} />
      <View style={{ flex: 1, marginLeft: 10 }}>
        <Text style={[styles.title, { color: config.color }]} numberOfLines={2}>{toast.title}</Text>
        {toast.message ? <Text style={styles.message} numberOfLines={3}>{toast.message}</Text> : null}
      </View>
      <TouchableOpacity onPress={onDismiss} hitSlop={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <Ionicons name="close" size={16} color={config.color} />
      </TouchableOpacity>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: "absolute",
    left: 0,
    right: 0,
    paddingHorizontal: spacing.md,
    zIndex: 9999,
    gap: 8,
  },
  toast: {
    flexDirection: "row",
    alignItems: "center",
    padding: 12,
    borderRadius: radius.md,
    borderWidth: 1,
    ...shadow.md,
  },
  title: { fontSize: 13, fontWeight: "700" },
  message: { fontSize: 12, color: colors.textSecondary, marginTop: 2 },
});
