import React, { useEffect, useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Linking, Platform } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect } from "expo-router";

import { Card, Badge, SectionTitle, EmptyState, Overline, Button } from "@/src/components/ui";
import { colors, fmt, spacing } from "@/src/theme";
import { apiGet, getToken } from "@/src/api/client";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";

type Trade = {
  id: string; symbol: string; side: "BUY" | "SELL"; entry_price: number; exit_price: number;
  quantity: number; pnl: number; pnl_pct: number; strategy: string; close_reason: string;
  opened_at: string; closed_at: string; mode: string; fees: number;
};

export default function History() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [filter, setFilter] = useState<"all" | "demo" | "real">("all");
  const [metrics, setMetrics] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const q = filter === "all" ? "" : `?mode=${filter}`;
      const [list, met] = await Promise.all([
        apiGet<Trade[]>(`/trades${q}`),
        apiGet<any>(`/trades/metrics${q}`),
      ]);
      setTrades(list);
      setMetrics(met);
    } catch {}
  }, [filter]);

  useFocusEffect(useCallback(() => {
    let interval: any;
    refresh();
    interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]));

  const exportFile = async (format: "csv" | "json") => {
    setBusy(true);
    try {
      const token = await getToken();
      const url = `${BASE}/api/trades/export?format=${format}${filter !== "all" ? `&mode=${filter}` : ""}`;
      if (Platform.OS === "web") {
        // For web, open in new tab with auth header is tricky; we fall back to fetching as blob.
        const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
        const blob = await res.blob();
        const dl = URL.createObjectURL(blob);
        // @ts-ignore
        const a = document.createElement("a");
        a.href = dl;
        a.download = `trades.${format}`;
        a.click();
        URL.revokeObjectURL(dl);
      } else {
        // Native: copy URL to clipboard or attempt Linking
        await Linking.openURL(url);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll} stickyHeaderIndices={[1]}>
        <View>
          <Overline>Journal</Overline>
          <Text style={styles.title}>Historique des trades</Text>
        </View>

        {/* Sticky filter row */}
        <View style={styles.filterBg}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterRow}>
            {(["all", "demo", "real"] as const).map((f) => (
              <TouchableOpacity
                key={f}
                testID={`filter-${f}`}
                onPress={() => setFilter(f)}
                style={[styles.chip, filter === f && styles.chipActive]}
              >
                <Text style={[styles.chipText, filter === f && styles.chipTextActive]}>
                  {f === "all" ? "Tous" : f.toUpperCase()}
                </Text>
              </TouchableOpacity>
            ))}
            <TouchableOpacity onPress={() => exportFile("csv")} style={styles.exportChip} testID="export-csv-button">
              <Ionicons name="download-outline" size={14} color={colors.primary} />
              <Text style={styles.exportText}>CSV</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => exportFile("json")} style={styles.exportChip} testID="export-json-button">
              <Ionicons name="download-outline" size={14} color={colors.primary} />
              <Text style={styles.exportText}>JSON</Text>
            </TouchableOpacity>
          </ScrollView>
        </View>

        {/* Metrics summary */}
        {metrics && metrics.total_trades > 0 ? (
          <Card style={{ marginTop: spacing.md }}>
            <View style={styles.metricsGrid}>
              <View style={styles.metricCell}>
                <Text style={styles.metricLabel}>Total</Text>
                <Text style={styles.metricVal} testID="hist-metric-total">{metrics.total_trades}</Text>
              </View>
              <View style={styles.metricCell}>
                <Text style={styles.metricLabel}>Winrate</Text>
                <Text style={[styles.metricVal, { color: metrics.winrate >= 50 ? colors.success : colors.danger }]} testID="hist-metric-winrate">{fmt.pct(metrics.winrate)}</Text>
              </View>
              <View style={styles.metricCell}>
                <Text style={styles.metricLabel}>P&L</Text>
                <Text style={[styles.metricVal, { color: metrics.total_pnl >= 0 ? colors.success : colors.danger }]} testID="hist-metric-pnl">{fmt.money(metrics.total_pnl, "USD")}</Text>
              </View>
            </View>
          </Card>
        ) : null}

        {trades.length === 0 ? (
          <Card style={{ marginTop: spacing.md }}>
            <EmptyState icon="time-outline" title="Aucun trade clôturé" subtitle="Démarrez le bot pour générer des trades" testID="empty-trades" />
          </Card>
        ) : (
          trades.map((t) => (
            <Card key={t.id} style={{ marginTop: spacing.sm }} testID={`trade-${t.id}`}>
              <View style={styles.tradeHeader}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Text style={styles.tradeSym}>{t.symbol}</Text>
                  <Badge variant={t.side === "BUY" ? "success" : "danger"}>{t.side}</Badge>
                  <Badge variant={t.mode === "real" ? "real" : "demo"}>{t.mode.toUpperCase()}</Badge>
                </View>
                <Text style={[styles.tradePnl, { color: t.pnl >= 0 ? colors.success : colors.danger }]}>
                  {t.pnl >= 0 ? "+" : ""}{fmt.money(t.pnl, "USD")}
                </Text>
              </View>
              <View style={styles.tradeDetails}>
                <Text style={styles.tradeDetail}>Entry: {fmt.price(t.entry_price, 5)}</Text>
                <Text style={styles.tradeDetail}>Exit: {fmt.price(t.exit_price, 5)}</Text>
                <Text style={styles.tradeDetail}>{t.strategy}</Text>
                <Text style={styles.tradeDetail}>{t.close_reason}</Text>
                <Text style={styles.tradeDetail}>{fmt.pct(t.pnl_pct, 3)}</Text>
              </View>
              <Text style={styles.tradeTs}>{new Date(t.closed_at).toLocaleString("fr-FR")}</Text>
            </Card>
          ))
        )}

        <View style={{ height: spacing.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  scroll: { padding: spacing.md, paddingTop: spacing.sm },
  title: { fontSize: 28, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.8, marginTop: 4, marginBottom: spacing.sm },
  filterBg: { backgroundColor: colors.surface, paddingVertical: spacing.sm },
  filterRow: { flexDirection: "row", gap: 8, paddingHorizontal: 2 },
  chip: { paddingHorizontal: 14, height: 36, borderRadius: 18, borderColor: colors.borderStrong, borderWidth: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.white, flexShrink: 0 },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: 13, color: colors.textPrimary, fontWeight: "600" },
  chipTextActive: { color: colors.white },
  exportChip: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, height: 36, borderRadius: 18, borderColor: colors.primary, borderWidth: 1, backgroundColor: colors.white, flexShrink: 0 },
  exportText: { color: colors.primary, fontWeight: "700", fontSize: 12 },
  metricsGrid: { flexDirection: "row" },
  metricCell: { flex: 1 },
  metricLabel: { fontSize: 11, color: colors.textSecondary, textTransform: "uppercase", letterSpacing: 1, fontWeight: "600" },
  metricVal: { fontSize: 18, fontWeight: "800", marginTop: 2 },
  tradeHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  tradeSym: { fontSize: 16, fontWeight: "700", color: colors.textPrimary },
  tradePnl: { fontSize: 16, fontWeight: "800" },
  tradeDetails: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 6 },
  tradeDetail: { fontSize: 11, color: colors.textSecondary },
  tradeTs: { fontSize: 10, color: colors.textMuted, marginTop: 6 },
});
