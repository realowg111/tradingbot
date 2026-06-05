import React, { useEffect, useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, RefreshControl, TouchableOpacity } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";

import { Card, SectionTitle, Stat, Badge, EmptyState, Sparkline, Overline } from "@/src/components/ui";
import { colors, fmt, spacing } from "@/src/theme";
import { apiGet, apiPost } from "@/src/api/client";

type BotStateResp = {
  state: any;
  config_mode: "demo" | "real";
  config_enabled: boolean;
  prices: Record<string, number | null>;
};

type Position = {
  id: string; symbol: string; side: "BUY" | "SELL"; entry_price: number;
  current_price?: number | null; unrealized_pnl?: number;
  quantity: number; stop_loss: number; take_profit: number; strategy: string; mode: string;
};

export default function Dashboard() {
  const router = useRouter();
  const [data, setData] = useState<BotStateResp | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [metrics, setMetrics] = useState<any | null>(null);
  const [equity, setEquity] = useState<number[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [st, pos, met, eq] = await Promise.all([
        apiGet<BotStateResp>("/bot/state"),
        apiGet<Position[]>("/positions/open"),
        apiGet<any>("/trades/metrics"),
        apiGet<any[]>("/trades/equity-curve"),
      ]);
      setData(st);
      setPositions(pos);
      setMetrics(met);
      setEquity(eq.map((p) => p.equity));
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  // Poll every 3s while focused
  useFocusEffect(
    useCallback(() => {
      let interval: any;
      refresh();
      interval = setInterval(refresh, 3000);
      return () => clearInterval(interval);
    }, [refresh])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await refresh();
    setRefreshing(false);
  };

  const state = data?.state;
  const mode = data?.config_mode ?? "demo";
  const enabled = data?.config_enabled ?? false;
  const equityVal = state?.equity ?? 0;
  const pnlTotal = (state?.realized_pnl ?? 0) + (state?.unrealized_pnl ?? 0);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      >
        <View style={styles.headerRow}>
          <View>
            <Overline>Console de trading</Overline>
            <Text style={styles.title}>Dashboard</Text>
          </View>
          <View style={{ flexDirection: "row", gap: 8 }}>
            <Badge variant={mode === "demo" ? "demo" : "real"} testID="mode-badge">{mode === "demo" ? "DÉMO" : "RÉEL"}</Badge>
            <Badge variant={enabled ? "success" : "neutral"} testID="bot-status-badge">{enabled ? "ACTIF" : "ARRÊTÉ"}</Badge>
          </View>
        </View>

        {state?.kill_switch_engaged ? (
          <View style={styles.killBanner} testID="kill-banner">
            <Ionicons name="warning" size={18} color={colors.white} />
            <Text style={styles.killBannerText}>KILL SWITCH ENGAGÉ — Toutes positions fermées</Text>
          </View>
        ) : null}

        {state?.paused_reason ? (
          <View style={styles.warnBanner} testID="paused-banner">
            <Ionicons name="pause-circle" size={16} color={colors.warning} />
            <Text style={styles.warnText}>Bot en pause : {state.paused_reason}</Text>
          </View>
        ) : null}

        {error ? (
          <View style={styles.errorBanner}><Text style={{ color: colors.danger }}>{error}</Text></View>
        ) : null}

        {/* Balance & Equity */}
        <Card style={{ marginTop: spacing.md }}>
          <Overline>Capital</Overline>
          <Text style={styles.balanceLarge} testID="balance-value">{fmt.money(equityVal, "USD")}</Text>
          <View style={styles.pnlRow}>
            <Ionicons
              name={pnlTotal >= 0 ? "arrow-up" : "arrow-down"}
              size={14}
              color={pnlTotal >= 0 ? colors.success : colors.danger}
            />
            <Text style={[styles.pnlText, { color: pnlTotal >= 0 ? colors.success : colors.danger }]} testID="pnl-total">
              {fmt.money(pnlTotal, "USD")} ({fmt.pct((pnlTotal / (state?.daily_start_balance || 10000)) * 100)})
            </Text>
          </View>
          {equity.length > 1 ? (
            <View style={{ marginTop: spacing.md }}>
              <Sparkline values={equity.slice(-30)} height={48} color={pnlTotal >= 0 ? colors.success : colors.danger} />
            </View>
          ) : null}
        </Card>

        {/* Stats grid */}
        <View style={styles.statGrid}>
          <Card style={styles.statCard}>
            <Stat testID="stat-realized" label="P&L Réalisé" value={fmt.money(state?.realized_pnl ?? 0, "USD")} valueColor={(state?.realized_pnl ?? 0) >= 0 ? colors.success : colors.danger} />
          </Card>
          <Card style={styles.statCard}>
            <Stat testID="stat-unrealized" label="P&L Latent" value={fmt.money(state?.unrealized_pnl ?? 0, "USD")} valueColor={(state?.unrealized_pnl ?? 0) >= 0 ? colors.success : colors.danger} />
          </Card>
          <Card style={styles.statCard}>
            <Stat testID="stat-daily" label="P&L Jour" value={fmt.money(state?.daily_pnl ?? 0, "USD")} valueColor={(state?.daily_pnl ?? 0) >= 0 ? colors.success : colors.danger} />
          </Card>
          <Card style={styles.statCard}>
            <Stat testID="stat-open" label="Positions Ouvertes" value={`${state?.open_positions ?? 0}`} />
          </Card>
        </View>

        {/* Metrics */}
        {metrics && metrics.total_trades > 0 ? (
          <Card style={{ marginTop: spacing.md }}>
            <SectionTitle>Performances</SectionTitle>
            <View style={styles.metricsGrid}>
              <Stat testID="metric-winrate" label="Winrate" value={fmt.pct(metrics.winrate)} valueColor={metrics.winrate >= 50 ? colors.success : colors.danger} />
              <Stat testID="metric-profit-factor" label="Profit Factor" value={(metrics.profit_factor || 0).toFixed(2)} />
            </View>
            <View style={[styles.metricsGrid, { marginTop: spacing.md }]}>
              <Stat testID="metric-drawdown" label="Drawdown Max" value={fmt.pct(metrics.max_drawdown_pct)} valueColor={colors.danger} />
              <Stat testID="metric-sharpe" label="Sharpe" value={(metrics.sharpe || 0).toFixed(2)} />
            </View>
            <View style={[styles.metricsGrid, { marginTop: spacing.md }]}>
              <Stat testID="metric-expectancy" label="Expectancy" value={fmt.money(metrics.expectancy, "USD")} />
              <Stat testID="metric-trades" label="Trades" value={`${metrics.total_trades}`} sub={`W${metrics.wins} / L${metrics.losses}`} />
            </View>
          </Card>
        ) : null}

        {/* Open positions */}
        <SectionTitle testID="positions-section" action={
          <TouchableOpacity onPress={() => router.push("/(tabs)/history")} testID="see-history-link">
            <Text style={{ color: colors.primary, fontSize: 13, fontWeight: "600" }}>Historique →</Text>
          </TouchableOpacity>
        }>
          Positions ouvertes ({positions.length})
        </SectionTitle>

        {positions.length === 0 ? (
          <Card>
            <EmptyState icon="trending-up-outline" title="Aucune position ouverte" subtitle="Le bot ouvrira des positions selon les stratégies activées" />
          </Card>
        ) : (
          positions.map((p) => (
            <Card key={p.id} style={{ marginBottom: spacing.sm }} testID={`position-card-${p.id}`}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                <View>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                    <Text style={styles.posSymbol}>{p.symbol}</Text>
                    <Badge variant={p.side === "BUY" ? "success" : "danger"}>{p.side}</Badge>
                  </View>
                  <Text style={styles.posStrategy}>{p.strategy}</Text>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={[styles.posPnl, { color: (p.unrealized_pnl ?? 0) >= 0 ? colors.success : colors.danger }]}>
                    {fmt.money(p.unrealized_pnl ?? 0, "USD")}
                  </Text>
                  <Text style={styles.posPrice}>{fmt.price(p.current_price ?? p.entry_price, 5)}</Text>
                </View>
              </View>
              <View style={styles.posDetails}>
                <Text style={styles.posDetail}>Entry: {fmt.price(p.entry_price, 5)}</Text>
                <Text style={styles.posDetail}>SL: {fmt.price(p.stop_loss, 5)}</Text>
                <Text style={styles.posDetail}>TP: {fmt.price(p.take_profit, 5)}</Text>
                <Text style={styles.posDetail}>Qty: {p.quantity.toFixed(2)}</Text>
              </View>
            </Card>
          ))
        )}

        {/* Market prices */}
        {data?.prices ? (
          <>
            <SectionTitle>Marchés</SectionTitle>
            <Card>
              {Object.entries(data.prices).map(([sym, price]) => (
                <View key={sym} style={styles.priceRow} testID={`market-${sym}`}>
                  <Text style={styles.priceSym}>{sym}</Text>
                  <Text style={styles.pricePrice}>{price !== null ? fmt.price(price, sym === "BTCUSD" || sym === "US100" ? 1 : sym === "XAUUSD" ? 2 : 5) : "—"}</Text>
                </View>
              ))}
            </Card>
          </>
        ) : null}

        <View style={{ height: spacing.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  scroll: { padding: spacing.md, paddingTop: spacing.sm },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end", marginTop: spacing.sm, marginBottom: spacing.sm },
  title: { fontSize: 28, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.8, marginTop: 4 },
  balanceLarge: { fontSize: 36, fontWeight: "800", color: colors.textPrimary, letterSpacing: -1.2, marginTop: 6 },
  pnlRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 },
  pnlText: { fontSize: 14, fontWeight: "700" },
  statGrid: { flexDirection: "row", flexWrap: "wrap", marginTop: spacing.md, gap: spacing.sm },
  statCard: { flexBasis: "48%", flexGrow: 1 },
  metricsGrid: { flexDirection: "row", gap: spacing.md },
  posSymbol: { fontSize: 16, fontWeight: "700", color: colors.textPrimary },
  posStrategy: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  posPnl: { fontSize: 16, fontWeight: "700" },
  posPrice: { fontSize: 12, color: colors.textSecondary, marginTop: 2 },
  posDetails: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginTop: spacing.sm },
  posDetail: { fontSize: 11, color: colors.textSecondary },
  priceRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 8, borderBottomColor: colors.border, borderBottomWidth: 1 },
  priceSym: { fontSize: 13, fontWeight: "600", color: colors.textPrimary },
  pricePrice: { fontSize: 13, color: colors.textSecondary, fontFamily: "Courier" },
  killBanner: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: colors.danger, padding: 12, borderRadius: 8, marginTop: spacing.sm },
  killBannerText: { color: colors.white, fontWeight: "700", fontSize: 13, flex: 1 },
  warnBanner: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: colors.warningBg, padding: 10, borderRadius: 8, marginTop: spacing.sm, borderColor: "#FCD34D", borderWidth: 1 },
  warnText: { color: "#92400E", fontSize: 12, fontWeight: "600", flex: 1 },
  errorBanner: { backgroundColor: colors.dangerBg, padding: 10, borderRadius: 8, marginTop: spacing.sm },
});
