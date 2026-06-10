import React, { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Switch,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { Stack, useRouter } from "expo-router";

import { Card, Badge, Overline, EmptyState } from "@/src/components/ui";
import { colors, spacing, radius } from "@/src/theme";
import { apiGet, apiPost } from "@/src/api/client";

type RegimeKey = "TREND_UP" | "TREND_DOWN" | "RANGE" | "VOLATILE" | "UNKNOWN";

type SymbolRegime = {
  regime: RegimeKey;
  confidence: number;
  metrics: {
    stdev_pct: number;
    range_pct: number;
    ema_slope_pct: number;
    n: number;
  };
  updated_at: string;
};

type RegimeResponse = {
  adaptive_enabled: boolean;
  symbols: Record<string, SymbolRegime>;
};

const REGIME_META: Record<RegimeKey, {
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  bg: string;
  border: string;
  strategies: string;
  sizing: string;
}> = {
  TREND_UP: {
    label: "Tendance haussière",
    icon: "trending-up",
    color: colors.success,
    bg: colors.successBg,
    border: "#A7F3D0",
    strategies: "EMA/MACD, Multi",
    sizing: "100% (×1.0)",
  },
  TREND_DOWN: {
    label: "Tendance baissière",
    icon: "trending-down",
    color: colors.danger,
    bg: colors.dangerBg,
    border: "#FECACA",
    strategies: "EMA/MACD, Multi",
    sizing: "100% (×1.0)",
  },
  RANGE: {
    label: "Range / Latéral",
    icon: "swap-horizontal",
    color: colors.primary,
    bg: "#DBEAFE",
    border: "#BFDBFE",
    strategies: "Bollinger, RSI",
    sizing: "75% (×0.75)",
  },
  VOLATILE: {
    label: "Forte volatilité",
    icon: "flash",
    color: colors.warning,
    bg: colors.warningBg,
    border: "#FCD34D",
    strategies: "Multi (consensus)",
    sizing: "50% (×0.5)",
  },
  UNKNOWN: {
    label: "Indéterminé",
    icon: "help-circle-outline",
    color: colors.textMuted,
    bg: colors.surfaceAlt,
    border: colors.border,
    strategies: "Multi (par défaut)",
    sizing: "100% (×1.0)",
  },
};

export default function RegimeScreen() {
  const router = useRouter();
  const [data, setData] = useState<RegimeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [toggleBusy, setToggleBusy] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const res = await apiGet<RegimeResponse>("/market/regime");
      setData(res);
    } catch {
      // ignore
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const i = setInterval(fetchData, 6000);
    return () => clearInterval(i);
  }, [fetchData]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const toggleAdaptive = async () => {
    if (!data || toggleBusy) return;
    setToggleBusy(true);
    try {
      const res = await apiPost<{ adaptive_enabled: boolean }>("/bot/adaptive", {
        enabled: !data.adaptive_enabled,
      });
      setData({ ...data, adaptive_enabled: res.adaptive_enabled });
    } catch {
      // ignore
    } finally {
      setToggleBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={10} testID="regime-back">
          <Ionicons name="chevron-back" size={26} color={colors.textPrimary} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Overline>Adaptatif</Overline>
          <Text style={styles.title}>Régime de marché</Text>
        </View>
        <View style={styles.pill}>
          <Ionicons name="pulse" size={12} color={colors.primary} />
          <Text style={styles.pillText}>Auto</Text>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {/* Toggle */}
        <Card>
          <View style={styles.toggleRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.toggleTitle}>Adaptation automatique</Text>
              <Text style={styles.toggleSubtitle}>
                {data?.adaptive_enabled
                  ? "Le bot ajuste stratégies et sizing selon le régime détecté"
                  : "Le bot utilise les stratégies configurées sans adaptation"}
              </Text>
            </View>
            <Switch
              value={!!data?.adaptive_enabled}
              onValueChange={toggleAdaptive}
              disabled={toggleBusy || loading}
              trackColor={{ false: colors.borderStrong, true: colors.primary }}
              thumbColor={colors.white}
              testID="adaptive-toggle"
            />
          </View>
        </Card>

        {/* Legend */}
        <Card style={{ marginTop: spacing.md }}>
          <Text style={styles.cardTitle}>{"Règles d'adaptation"}</Text>
          {(["TREND_UP", "TREND_DOWN", "RANGE", "VOLATILE"] as RegimeKey[]).map((k) => {
            const meta = REGIME_META[k];
            return (
              <View key={k} style={styles.legendRow}>
                <View style={[styles.legendIcon, { backgroundColor: meta.bg, borderColor: meta.border }]}>
                  <Ionicons name={meta.icon} size={16} color={meta.color} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.legendLabel}>{meta.label}</Text>
                  <Text style={styles.legendDetail}>
                    {meta.strategies} · Sizing {meta.sizing}
                  </Text>
                </View>
              </View>
            );
          })}
        </Card>

        {/* Per-symbol */}
        <Card style={{ marginTop: spacing.md }}>
          <Text style={styles.cardTitle}>État par symbole</Text>
          {loading && !data ? (
            <View style={{ paddingVertical: spacing.lg, alignItems: "center" }}>
              <ActivityIndicator color={colors.primary} />
            </View>
          ) : data && Object.keys(data.symbols).length > 0 ? (
            Object.entries(data.symbols).map(([sym, r]) => {
              const meta = REGIME_META[r.regime] || REGIME_META.UNKNOWN;
              const conf = Math.round((r.confidence || 0) * 100);
              return (
                <View key={sym} style={styles.symRow}>
                  <View style={styles.symLeft}>
                    <Text style={styles.symLabel}>{sym}</Text>
                    <View style={[styles.regimeChip, { backgroundColor: meta.bg, borderColor: meta.border }]}>
                      <Ionicons name={meta.icon} size={12} color={meta.color} />
                      <Text style={[styles.regimeChipText, { color: meta.color }]}>{meta.label}</Text>
                    </View>
                  </View>
                  <View style={styles.symRight}>
                    <Text style={styles.metricMain}>{conf}%</Text>
                    <Text style={styles.metricLabel}>confiance</Text>
                  </View>
                  <View style={styles.metricsBlock}>
                    <MetricBlob label="σ" value={`${r.metrics.stdev_pct.toFixed(2)}%`} />
                    <MetricBlob label="slope" value={`${r.metrics.ema_slope_pct.toFixed(2)}%`} />
                    <MetricBlob label="range" value={`${r.metrics.range_pct.toFixed(2)}%`} />
                  </View>
                </View>
              );
            })
          ) : (
            <EmptyState title="Aucune donnée" subtitle="Le bot collecte les ticks, patiente quelques secondes" />
          )}
        </Card>

        <Text style={styles.footnote}>
          Mise à jour automatique toutes les ~2s. Détection sur les 50 dernières bougies.
        </Text>

        <View style={{ height: spacing.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function MetricBlob({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.blob}>
      <Text style={styles.blobLabel}>{label}</Text>
      <Text style={styles.blobValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.white,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
  },
  title: { fontSize: 22, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.5 },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
    backgroundColor: "#EEF2FF",
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: "#C7D2FE",
  },
  pillText: { fontSize: 11, fontWeight: "700", color: colors.primary },
  scroll: { padding: spacing.md },
  cardTitle: { fontSize: 14, fontWeight: "700", color: colors.textPrimary, marginBottom: spacing.sm },
  toggleRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  toggleTitle: { fontSize: 14, fontWeight: "700", color: colors.textPrimary },
  toggleSubtitle: { fontSize: 12, color: colors.textSecondary, marginTop: 2 },
  legendRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 6 },
  legendIcon: {
    width: 28, height: 28, borderRadius: 14, alignItems: "center", justifyContent: "center",
    borderWidth: 1,
  },
  legendLabel: { fontSize: 13, fontWeight: "700", color: colors.textPrimary },
  legendDetail: { fontSize: 11, color: colors.textSecondary, marginTop: 1 },
  symRow: {
    paddingVertical: spacing.sm,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
  },
  symLeft: { flex: 1, minWidth: "60%" },
  symLabel: { fontSize: 15, fontWeight: "800", color: colors.textPrimary, marginBottom: 4 },
  regimeChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    alignSelf: "flex-start",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  regimeChipText: { fontSize: 11, fontWeight: "700" },
  symRight: { alignItems: "flex-end" },
  metricMain: { fontSize: 18, fontWeight: "800", color: colors.textPrimary },
  metricLabel: { fontSize: 10, color: colors.textMuted },
  metricsBlock: {
    flexDirection: "row",
    gap: 6,
    width: "100%",
    marginTop: 8,
  },
  blob: {
    flex: 1,
    backgroundColor: colors.surfaceAlt,
    paddingVertical: 6,
    paddingHorizontal: 8,
    borderRadius: radius.sm,
    alignItems: "center",
  },
  blobLabel: { fontSize: 10, color: colors.textSecondary },
  blobValue: { fontSize: 12, fontWeight: "700", color: colors.textPrimary, marginTop: 1 },
  footnote: {
    fontSize: 11,
    color: colors.textMuted,
    textAlign: "center",
    marginTop: spacing.lg,
    fontStyle: "italic",
  },
});
