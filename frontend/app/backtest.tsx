import React, { useState } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { Card, Button, Input, SectionTitle, Overline, Stat, Badge } from "@/src/components/ui";
import { colors, spacing, fmt } from "@/src/theme";
import { apiPost } from "@/src/api/client";

const SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD", "US100", "BTCUSD"];
const STRATS = [
  { id: "multi", label: "Multi-indicateurs" },
  { id: "ema_macd", label: "EMA/MACD" },
  { id: "rsi", label: "RSI" },
  { id: "bollinger", label: "Bollinger" },
];

export default function Backtest() {
  const router = useRouter();
  const [symbol, setSymbol] = useState("EURUSD");
  const [strategy, setStrategy] = useState("multi");
  const [candles, setCandles] = useState("500");
  const [balance, setBalance] = useState("10000");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setError(null); setResult(null); setBusy(true);
    try {
      const r = await apiPost("/backtest/run", {
        symbol, strategy,
        candles: parseInt(candles, 10) || 500,
        starting_balance: parseFloat(balance) || 10000,
      });
      setResult(r);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backRow} testID="backtest-back">
          <Ionicons name="chevron-back" size={20} color={colors.textPrimary} />
          <Text style={{ color: colors.textPrimary, fontSize: 15 }}>Retour</Text>
        </TouchableOpacity>
        <Overline>Simulation</Overline>
        <Text style={styles.title}>Backtesting</Text>
        <Text style={styles.subtitle}>Test sur historique synthétique avec frais & slippage réalistes</Text>

        <SectionTitle>Paramètres</SectionTitle>
        <Card>
          <Text style={styles.label}>Symbole</Text>
          <View style={styles.chipRow}>
            {SYMBOLS.map((s) => (
              <TouchableOpacity key={s} onPress={() => setSymbol(s)} style={[styles.chip, symbol === s && styles.chipOn]} testID={`backtest-symbol-${s}`}>
                <Text style={[styles.chipText, symbol === s && styles.chipTextOn]}>{s}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={[styles.label, { marginTop: spacing.md }]}>Stratégie</Text>
          <View style={styles.chipRow}>
            {STRATS.map((s) => (
              <TouchableOpacity key={s.id} onPress={() => setStrategy(s.id)} style={[styles.chip, strategy === s.id && styles.chipOn]} testID={`backtest-strat-${s.id}`}>
                <Text style={[styles.chipText, strategy === s.id && styles.chipTextOn]}>{s.label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
            <View style={{ flex: 1 }}><Input label="Bougies" value={candles} onChangeText={setCandles} keyboardType="numeric" testID="backtest-candles-input" /></View>
            <View style={{ flex: 1 }}><Input label="Capital initial" value={balance} onChangeText={setBalance} keyboardType="numeric" testID="backtest-balance-input" /></View>
          </View>

          {error ? <Text style={{ color: colors.danger, fontSize: 13, marginBottom: 8 }}>{error}</Text> : null}
          <Button title="Lancer le backtest" onPress={run} loading={busy} icon="play" testID="backtest-run-button" />
        </Card>

        {result ? (
          <>
            <SectionTitle>Résultats</SectionTitle>
            <Card>
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>Solde final</Text>
                  <Text style={[styles.endBalance, { color: result.ending_balance >= result.starting_balance ? colors.success : colors.danger }]} testID="backtest-end-balance">
                    {fmt.money(result.ending_balance, "USD")}
                  </Text>
                  <Text style={{ fontSize: 12, color: colors.textSecondary, marginTop: 2 }}>
                    {fmt.money(result.ending_balance - result.starting_balance, "USD")} ({fmt.pct(((result.ending_balance - result.starting_balance) / result.starting_balance) * 100)})
                  </Text>
                </View>
                <Badge variant={result.winrate >= 50 ? "success" : "danger"}>{fmt.pct(result.winrate)} WR</Badge>
              </View>
              <View style={{ flexDirection: "row", marginTop: spacing.md }}>
                <Stat label="Trades" value={`${result.total_trades}`} sub={`W${result.wins} / L${result.losses}`} testID="backtest-trades" />
                <Stat label="Profit Factor" value={(result.profit_factor || 0).toFixed(2)} testID="backtest-pf" />
              </View>
              <View style={{ flexDirection: "row", marginTop: spacing.md }}>
                <Stat label="Drawdown" value={fmt.pct(result.max_drawdown_pct)} valueColor={colors.danger} testID="backtest-dd" />
                <Stat label="Sharpe" value={(result.sharpe || 0).toFixed(2)} testID="backtest-sharpe" />
              </View>
              <View style={{ marginTop: spacing.md }}>
                <Stat label="Expectancy par trade" value={fmt.money(result.expectancy, "USD")} testID="backtest-exp" />
              </View>
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
  scroll: { padding: spacing.md },
  backRow: { flexDirection: "row", alignItems: "center", gap: 4, marginBottom: spacing.md },
  title: { fontSize: 28, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.8, marginTop: 4 },
  subtitle: { fontSize: 13, color: colors.textSecondary, marginTop: 4 },
  label: { fontSize: 11, color: colors.textSecondary, textTransform: "uppercase", letterSpacing: 1, fontWeight: "700", marginBottom: 6 },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 18, borderColor: colors.borderStrong, borderWidth: 1, backgroundColor: colors.white },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: 12, color: colors.textPrimary, fontWeight: "600" },
  chipTextOn: { color: colors.white },
  endBalance: { fontSize: 26, fontWeight: "800", letterSpacing: -0.5 },
});
