import React, { useEffect, useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl, Animated } from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";

import { Card, Badge, Sparkline, EmptyState } from "@/src/components/ui";
import { colors, fmt, spacing, radius, shadow } from "@/src/theme";
import { apiGet, apiPost } from "@/src/api/client";
import { useLiveData, type LivePosition } from "@/src/hooks/useLiveData";
import { useToast } from "@/src/components/Toast";

export default function Dashboard() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const { snapshot, status, lastUpdate } = useLiveData();
  const [metrics, setMetrics] = useState<any | null>(null);
  const [equity, setEquity] = useState<number[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);

  const refreshSecondary = useCallback(async () => {
    try {
      const [met, eq] = await Promise.all([
        apiGet<any>("/trades/metrics"),
        apiGet<any[]>("/trades/equity-curve"),
      ]);
      setMetrics(met);
      setEquity(eq.map((p) => p.equity));
    } catch {}
  }, []);

  useFocusEffect(useCallback(() => {
    let interval: any;
    refreshSecondary();
    interval = setInterval(refreshSecondary, 5000);
    return () => clearInterval(interval);
  }, [refreshSecondary]));

  const onRefresh = async () => {
    setRefreshing(true);
    await refreshSecondary();
    setRefreshing(false);
  };

  const toggleBot = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await apiPost<{ enabled: boolean }>("/bot/toggle");
      toast.show({
        type: r.enabled ? "success" : "info",
        title: r.enabled ? "Bot activé" : "Bot désactivé",
        message: r.enabled ? "Le bot va commencer à analyser les marchés" : "Aucune nouvelle position ne sera ouverte",
      });
    } catch (e: any) {
      toast.show({ type: "danger", title: "Erreur", message: e.message });
    } finally {
      setBusy(false);
    }
  };

  const state = snapshot?.state;
  const positions = snapshot?.positions ?? [];
  const prices = snapshot?.prices ?? {};
  const mode = snapshot?.config_mode ?? "demo";
  const enabled = snapshot?.config_enabled ?? false;
  const mt5 = snapshot?.mt5_status;
  const equityVal = state?.equity ?? 0;
  const balanceVal = state?.balance ?? 0;
  const dailyPnl = state?.daily_pnl ?? 0;
  const unrealized = state?.unrealized_pnl ?? 0;
  const totalPnl = (state?.realized_pnl ?? 0) + unrealized;
  const dailyPct = state?.daily_start_balance ? (dailyPnl / state.daily_start_balance) * 100 : 0;

  return (
    <View style={styles.container}>
      {/* Top Sticky Header */}
      <View style={[styles.stickyHeader, { paddingTop: insets.top + 10 }]}>
        <View style={styles.headerRow}>
          <View>
            <Text style={styles.headerLabel}>Console de trading</Text>
            <Text style={styles.headerTitle}>Dashboard</Text>
          </View>
          <View style={styles.headerBadges}>
            <LiveIndicator status={status} />
          </View>
        </View>

        {/* Connection state pills */}
        <View style={styles.pillRow}>
          <Pill
            icon={mode === "demo" ? "flask-outline" : "cash-outline"}
            label={mode === "demo" ? "MODE DÉMO" : "MODE RÉEL"}
            color={mode === "demo" ? colors.demoMode : colors.realMode}
            bg={mode === "demo" ? colors.demoModeBg : colors.realModeBg}
            testID="header-mode-pill"
          />
          <Pill
            icon={enabled ? "radio" : "power"}
            label={enabled ? "BOT ACTIF" : "BOT ARRÊTÉ"}
            color={enabled ? colors.success : colors.textSecondary}
            bg={enabled ? colors.successBg : colors.surfaceAlt}
            pulse={enabled}
            testID="header-bot-pill"
          />
          <Pill
            icon={mt5?.connected ? "link" : "cloud-offline-outline"}
            label={mt5?.connected ? `MT5 ${mt5.mode === "native" ? "NATIF" : "BRIDGE"}` : "MT5 SIMULÉ"}
            color={mt5?.connected ? colors.success : colors.warning}
            bg={mt5?.connected ? colors.successBg : colors.warningBg}
            testID="header-mt5-pill"
            onPress={() => router.push("/mt5")}
          />
        </View>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.md, paddingBottom: insets.bottom + 100 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      >
        {/* Alert banners */}
        {state?.kill_switch_engaged ? (
          <AlertBanner
            type="danger"
            icon="warning"
            title="KILL SWITCH ENGAGÉ"
            subtitle="Toutes les positions ont été fermées en urgence"
            testID="kill-banner"
          />
        ) : state?.paused_reason ? (
          <AlertBanner
            type="warning"
            icon="pause-circle"
            title="Bot en pause"
            subtitle={`Cause : ${state.paused_reason}`}
            testID="paused-banner"
          />
        ) : null}

        {/* Hero Balance Card */}
        <View style={styles.heroCard}>
          <View style={styles.heroTop}>
            <View>
              <Text style={styles.heroLabel}>Équity totale</Text>
              <Text style={styles.heroValue} testID="balance-value">{fmt.money(equityVal, "USD")}</Text>
              <View style={styles.heroPnlRow}>
                <View style={[styles.miniBadge, { backgroundColor: totalPnl >= 0 ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)" }]}>
                  <Ionicons name={totalPnl >= 0 ? "trending-up" : "trending-down"} size={12} color={totalPnl >= 0 ? "#34D399" : "#FCA5A5"} />
                  <Text style={[styles.miniBadgeText, { color: totalPnl >= 0 ? "#6EE7B7" : "#FCA5A5" }]} testID="pnl-total">
                    {totalPnl >= 0 ? "+" : ""}{fmt.money(totalPnl, "USD")}
                  </Text>
                </View>
                <Text style={styles.heroPct}>
                  {dailyPnl >= 0 ? "+" : ""}{fmt.pct(dailyPct)} aujourd'hui
                </Text>
              </View>
            </View>
            {/* ON/OFF Toggle Button - prominent */}
            <TouchableOpacity
              testID="dashboard-bot-toggle"
              onPress={toggleBot}
              disabled={busy || state?.kill_switch_engaged}
              activeOpacity={0.85}
              style={[
                styles.heroToggle,
                { backgroundColor: enabled ? colors.success : "rgba(255,255,255,0.15)" },
                (busy || state?.kill_switch_engaged) && { opacity: 0.5 },
              ]}
            >
              <Ionicons name="power" size={24} color={colors.white} />
              <Text style={styles.heroToggleText}>{enabled ? "ON" : "OFF"}</Text>
            </TouchableOpacity>
          </View>
          {equity.length > 1 ? (
            <View style={styles.heroChart}>
              <Sparkline values={equity.slice(-50)} height={36} color={totalPnl >= 0 ? "#34D399" : "#FCA5A5"} />
            </View>
          ) : null}
          <View style={styles.heroFooterRow}>
            <View style={styles.heroFooterCell}>
              <Text style={styles.heroFooterLabel}>Balance</Text>
              <Text style={styles.heroFooterValue} testID="hero-balance">{fmt.money(balanceVal, "USD")}</Text>
            </View>
            <View style={styles.heroFooterDivider} />
            <View style={styles.heroFooterCell}>
              <Text style={styles.heroFooterLabel}>P&L latent</Text>
              <Text style={[styles.heroFooterValue, { color: unrealized >= 0 ? "#6EE7B7" : "#FCA5A5" }]} testID="hero-unrealized">
                {fmt.money(unrealized, "USD")}
              </Text>
            </View>
            <View style={styles.heroFooterDivider} />
            <View style={styles.heroFooterCell}>
              <Text style={styles.heroFooterLabel}>Positions</Text>
              <Text style={styles.heroFooterValue} testID="hero-positions-count">{positions.length}</Text>
            </View>
          </View>
        </View>

        {/* Quick stats */}
        <View style={styles.statRow}>
          <StatTile
            icon="trending-up"
            label="P&L jour"
            value={fmt.money(dailyPnl, "USD")}
            tone={dailyPnl >= 0 ? "success" : "danger"}
            testID="tile-daily-pnl"
          />
          <StatTile
            icon="checkmark-circle"
            label="Winrate"
            value={metrics?.total_trades > 0 ? fmt.pct(metrics.winrate) : "—"}
            tone={metrics && metrics.winrate >= 50 ? "success" : metrics?.total_trades > 0 ? "danger" : "neutral"}
            testID="tile-winrate"
          />
          <StatTile
            icon="bar-chart"
            label="Trades"
            value={`${metrics?.total_trades ?? 0}`}
            tone="neutral"
            testID="tile-trades"
          />
        </View>

        {/* Open positions */}
        <SectionRow
          title="Positions ouvertes"
          count={positions.length}
          action={<RouterLink onPress={() => router.push("/(tabs)/history")}>Historique</RouterLink>}
        />
        {positions.length === 0 ? (
          <Card style={styles.emptyCard}>
            <EmptyState icon="trending-up-outline" title="Aucune position ouverte" subtitle={enabled ? "Le bot analyse les marchés..." : "Activez le bot pour commencer"} />
          </Card>
        ) : (
          positions.map((p) => <PositionRow key={p.id} pos={p} testID={`pos-${p.id}`} />)
        )}

        {/* Metrics */}
        {metrics && metrics.total_trades > 0 ? (
          <>
            <SectionRow title="Performances" count={null} />
            <Card style={{ marginTop: 0 }}>
              <View style={styles.metricsGrid}>
                <MetricCell label="Winrate" value={fmt.pct(metrics.winrate)} accent={metrics.winrate >= 50 ? colors.success : colors.danger} testID="metric-winrate" />
                <MetricCell label="Profit Factor" value={(metrics.profit_factor || 0).toFixed(2)} accent={colors.textPrimary} testID="metric-pf" />
                <MetricCell label="Sharpe" value={(metrics.sharpe || 0).toFixed(2)} accent={colors.textPrimary} testID="metric-sharpe" />
              </View>
              <View style={[styles.metricsGrid, { marginTop: spacing.md }]}>
                <MetricCell label="Drawdown" value={fmt.pct(metrics.max_drawdown_pct)} accent={colors.danger} testID="metric-dd" />
                <MetricCell label="Expectancy" value={fmt.money(metrics.expectancy, "USD")} accent={metrics.expectancy >= 0 ? colors.success : colors.danger} testID="metric-exp" />
                <MetricCell label="W/L" value={`${metrics.wins}/${metrics.losses}`} accent={colors.textPrimary} testID="metric-wl" />
              </View>
            </Card>
          </>
        ) : null}

        {/* Markets */}
        <SectionRow title="Marchés (live)" count={Object.keys(prices).length} />
        <Card>
          {Object.entries(prices).map(([sym, price], idx) => (
            <View key={sym} style={[styles.priceRow, idx === Object.keys(prices).length - 1 && { borderBottomWidth: 0 }]} testID={`market-${sym}`}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
                <View style={[styles.symbolDot, { backgroundColor: symbolColor(sym) }]} />
                <Text style={styles.priceSym}>{sym}</Text>
              </View>
              <View style={{ alignItems: "flex-end" }}>
                <Text style={styles.pricePrice}>{price !== null && price !== undefined ? fmt.price(price, decimalsFor(sym)) : "—"}</Text>
                <View style={styles.liveDot} />
              </View>
            </View>
          ))}
        </Card>

        {lastUpdate ? (
          <Text style={styles.lastUpdate}>Dernière mise à jour: {lastUpdate.toLocaleTimeString("fr-FR")}</Text>
        ) : null}
      </ScrollView>
    </View>
  );
}

// -------- Sub components --------

function LiveIndicator({ status }: { status: "connecting" | "live" | "polling" | "offline" }) {
  const map = {
    connecting: { color: colors.warning, label: "CONNEXION" },
    live: { color: colors.success, label: "TEMPS RÉEL" },
    polling: { color: colors.demoMode, label: "POLLING" },
    offline: { color: colors.danger, label: "HORS LIGNE" },
  } as const;
  const s = map[status];
  return (
    <View style={styles.liveIndicator} testID={`live-status-${status}`}>
      <View style={[styles.liveDotSmall, { backgroundColor: s.color }]} />
      <Text style={[styles.liveIndicatorText, { color: s.color }]}>{s.label}</Text>
    </View>
  );
}

function Pill({ icon, label, color, bg, pulse, testID, onPress }: { icon: keyof typeof Ionicons.glyphMap; label: string; color: string; bg: string; pulse?: boolean; testID?: string; onPress?: () => void }) {
  const Wrap: any = onPress ? TouchableOpacity : View;
  return (
    <Wrap onPress={onPress} activeOpacity={0.7} style={[styles.pill, { backgroundColor: bg, borderColor: color + "33" }]} testID={testID}>
      <Ionicons name={icon} size={11} color={color} />
      <Text style={[styles.pillText, { color }]}>{label}</Text>
    </Wrap>
  );
}

function AlertBanner({ type, icon, title, subtitle, testID }: { type: "danger" | "warning"; icon: keyof typeof Ionicons.glyphMap; title: string; subtitle?: string; testID?: string }) {
  const config = {
    danger: { bg: colors.danger, fg: colors.white },
    warning: { bg: colors.warningBg, fg: "#92400E" },
  }[type];
  return (
    <View style={[styles.banner, { backgroundColor: config.bg }]} testID={testID}>
      <Ionicons name={icon} size={20} color={config.fg} />
      <View style={{ flex: 1, marginLeft: 10 }}>
        <Text style={[styles.bannerTitle, { color: config.fg }]}>{title}</Text>
        {subtitle ? <Text style={[styles.bannerSubtitle, { color: config.fg, opacity: 0.85 }]}>{subtitle}</Text> : null}
      </View>
    </View>
  );
}

function StatTile({ icon, label, value, tone, testID }: { icon: keyof typeof Ionicons.glyphMap; label: string; value: string; tone: "success" | "danger" | "neutral"; testID?: string }) {
  const toneMap = {
    success: { iconBg: colors.successBg, iconColor: colors.success },
    danger: { iconBg: colors.dangerBg, iconColor: colors.danger },
    neutral: { iconBg: colors.surfaceAlt, iconColor: colors.textSecondary },
  } as const;
  const t = toneMap[tone];
  return (
    <View style={styles.statTile} testID={testID}>
      <View style={[styles.statTileIcon, { backgroundColor: t.iconBg }]}>
        <Ionicons name={icon} size={14} color={t.iconColor} />
      </View>
      <Text style={styles.statTileLabel}>{label}</Text>
      <Text style={styles.statTileValue}>{value}</Text>
    </View>
  );
}

function PositionRow({ pos, testID }: { pos: LivePosition; testID?: string }) {
  const pnl = pos.unrealized_pnl ?? 0;
  const isBuy = pos.side === "BUY";
  return (
    <View style={styles.posCard} testID={testID}>
      <View style={styles.posLeft}>
        <View style={[styles.posSideDot, { backgroundColor: isBuy ? colors.success : colors.danger }]} />
        <View>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <Text style={styles.posSym}>{pos.symbol}</Text>
            <Text style={[styles.posSide, { color: isBuy ? colors.success : colors.danger }]}>{isBuy ? "↑ ACHAT" : "↓ VENTE"}</Text>
          </View>
          <Text style={styles.posMeta}>{pos.strategy} · {pos.quantity.toFixed(2)}</Text>
        </View>
      </View>
      <View style={styles.posRight}>
        <Text style={[styles.posPnl, { color: pnl >= 0 ? colors.success : colors.danger }]}>
          {pnl >= 0 ? "+" : ""}{fmt.money(pnl, "USD")}
        </Text>
        <Text style={styles.posPrice}>{fmt.price(pos.current_price ?? pos.entry_price, decimalsFor(pos.symbol))}</Text>
      </View>
    </View>
  );
}

function SectionRow({ title, count, action }: { title: string; count?: number | null; action?: React.ReactNode }) {
  return (
    <View style={styles.sectionRow}>
      <View style={{ flexDirection: "row", alignItems: "baseline", gap: 8 }}>
        <Text style={styles.sectionTitle}>{title}</Text>
        {count !== null && count !== undefined ? <Text style={styles.sectionCount}>{count}</Text> : null}
      </View>
      {action}
    </View>
  );
}

function RouterLink({ children, onPress }: { children: React.ReactNode; onPress: () => void }) {
  return (
    <TouchableOpacity onPress={onPress} hitSlop={{ top: 8, right: 8, bottom: 8, left: 8 }}>
      <Text style={styles.routerLink}>{children} →</Text>
    </TouchableOpacity>
  );
}

function MetricCell({ label, value, accent, testID }: { label: string; value: string; accent: string; testID?: string }) {
  return (
    <View style={styles.metricCell} testID={testID}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, { color: accent }]}>{value}</Text>
    </View>
  );
}

function symbolColor(sym: string) {
  const map: Record<string, string> = {
    EURUSD: "#3B82F6", GBPUSD: "#8B5CF6", XAUUSD: "#F59E0B", US100: "#10B981", BTCUSD: "#F97316",
  };
  return map[sym] || colors.textSecondary;
}
function decimalsFor(sym: string) {
  if (sym === "BTCUSD" || sym === "US100") return 1;
  if (sym === "XAUUSD") return 2;
  return 5;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  stickyHeader: {
    backgroundColor: colors.white,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.md,
  },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  headerLabel: { fontSize: 10, color: colors.textMuted, textTransform: "uppercase", letterSpacing: 2, fontWeight: "700" },
  headerTitle: { fontSize: 26, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.8, marginTop: 2 },
  headerBadges: { flexDirection: "row", gap: 6, marginTop: 4 },
  liveIndicator: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 8, paddingVertical: 5, borderRadius: 100, backgroundColor: colors.surfaceAlt },
  liveDotSmall: { width: 6, height: 6, borderRadius: 3 },
  liveIndicatorText: { fontSize: 9, fontWeight: "800", letterSpacing: 1.2 },
  pillRow: { flexDirection: "row", gap: 6, marginTop: spacing.md, flexWrap: "wrap" },
  pill: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 100, borderWidth: 1 },
  pillText: { fontSize: 10, fontWeight: "800", letterSpacing: 1 },

  banner: { flexDirection: "row", alignItems: "center", padding: 12, borderRadius: radius.md, marginBottom: spacing.md },
  bannerTitle: { fontSize: 13, fontWeight: "800", letterSpacing: 0.5 },
  bannerSubtitle: { fontSize: 12, marginTop: 2 },

  heroCard: {
    backgroundColor: colors.primary,
    borderRadius: radius.lg,
    padding: spacing.lg,
    overflow: "hidden",
    ...shadow.lg,
  },
  heroTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  heroLabel: { fontSize: 11, color: "rgba(255,255,255,0.7)", textTransform: "uppercase", letterSpacing: 1.5, fontWeight: "700" },
  heroValue: { fontSize: 36, fontWeight: "800", color: colors.white, letterSpacing: -1.2, marginTop: 4 },
  heroPnlRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 6 },
  miniBadge: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 100 },
  miniBadgeText: { fontSize: 12, fontWeight: "700" },
  heroPct: { fontSize: 12, color: "rgba(255,255,255,0.7)" },
  heroToggle: {
    width: 64, height: 64, borderRadius: 16, alignItems: "center", justifyContent: "center", gap: 1,
    borderWidth: 1, borderColor: "rgba(255,255,255,0.2)",
  },
  heroToggleText: { color: colors.white, fontSize: 12, fontWeight: "800", letterSpacing: 1 },
  heroChart: { marginTop: spacing.md, opacity: 0.5 },
  heroFooterRow: { flexDirection: "row", marginTop: spacing.lg, paddingTop: spacing.md, borderTopColor: "rgba(255,255,255,0.1)", borderTopWidth: 1 },
  heroFooterCell: { flex: 1 },
  heroFooterDivider: { width: 1, backgroundColor: "rgba(255,255,255,0.1)", marginHorizontal: 8 },
  heroFooterLabel: { fontSize: 10, color: "rgba(255,255,255,0.6)", textTransform: "uppercase", letterSpacing: 1, fontWeight: "700" },
  heroFooterValue: { fontSize: 15, fontWeight: "800", color: colors.white, marginTop: 2, letterSpacing: -0.3 },

  statRow: { flexDirection: "row", gap: 8, marginTop: spacing.md },
  statTile: { flex: 1, backgroundColor: colors.white, borderRadius: radius.md, padding: 12, borderColor: colors.border, borderWidth: 1 },
  statTileIcon: { width: 26, height: 26, borderRadius: 13, alignItems: "center", justifyContent: "center" },
  statTileLabel: { fontSize: 11, color: colors.textSecondary, marginTop: 8, fontWeight: "600" },
  statTileValue: { fontSize: 16, fontWeight: "800", color: colors.textPrimary, marginTop: 2, letterSpacing: -0.3 },

  sectionRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.sm },
  sectionTitle: { fontSize: 16, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.3 },
  sectionCount: { fontSize: 13, color: colors.textMuted, fontWeight: "700" },
  routerLink: { fontSize: 12, color: colors.primary, fontWeight: "700" },

  emptyCard: { paddingVertical: spacing.lg },

  posCard: {
    backgroundColor: colors.white,
    borderRadius: radius.md,
    padding: 14,
    borderColor: colors.border,
    borderWidth: 1,
    marginBottom: 6,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  posLeft: { flexDirection: "row", alignItems: "center", gap: 12 },
  posSideDot: { width: 4, height: 36, borderRadius: 2 },
  posSym: { fontSize: 14, fontWeight: "800", color: colors.textPrimary },
  posSide: { fontSize: 10, fontWeight: "800", letterSpacing: 1 },
  posMeta: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  posRight: { alignItems: "flex-end" },
  posPnl: { fontSize: 14, fontWeight: "800" },
  posPrice: { fontSize: 11, color: colors.textSecondary, fontFamily: "Courier", marginTop: 2 },

  metricsGrid: { flexDirection: "row" },
  metricCell: { flex: 1 },
  metricLabel: { fontSize: 10, color: colors.textSecondary, textTransform: "uppercase", letterSpacing: 1, fontWeight: "700" },
  metricValue: { fontSize: 18, fontWeight: "800", marginTop: 4, letterSpacing: -0.3 },

  priceRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 12, borderBottomColor: colors.border, borderBottomWidth: 1 },
  symbolDot: { width: 8, height: 8, borderRadius: 4 },
  priceSym: { fontSize: 13, fontWeight: "700", color: colors.textPrimary, letterSpacing: 0.5 },
  pricePrice: { fontSize: 14, color: colors.textPrimary, fontFamily: "Courier", fontWeight: "700" },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.success, marginTop: 4 },

  lastUpdate: { textAlign: "center", color: colors.textMuted, fontSize: 10, marginTop: spacing.md, letterSpacing: 0.5 },
});
