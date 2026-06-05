import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Switch } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { Card, Button, Input, SectionTitle, Overline, Stat } from "@/src/components/ui";
import { colors, spacing } from "@/src/theme";
import { apiGet, apiPut } from "@/src/api/client";

export default function RiskSettings() {
  const router = useRouter();
  const [config, setConfig] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    apiGet("/bot/config").then(setConfig).catch((e) => setError(e.message));
  }, []);

  const upd = (key: string, val: any) => {
    setConfig((c: any) => ({ ...c, risk: { ...c.risk, [key]: val } }));
    setSuccess(false);
  };
  const updNum = (key: string, v: string) => {
    const n = parseFloat(v);
    if (!isNaN(n)) upd(key, n);
  };
  const updInt = (key: string, v: string) => {
    const n = parseInt(v, 10);
    if (!isNaN(n)) upd(key, n);
  };

  const save = async () => {
    setBusy(true); setError(null); setSuccess(false);
    try {
      await apiPut("/bot/risk", config.risk);
      setSuccess(true);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  };

  if (!config) {
    return <SafeAreaView style={styles.safe}><Text style={{ padding: 24 }}>Chargement…</Text></SafeAreaView>;
  }

  const r = config.risk;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backRow} testID="risk-back">
          <Ionicons name="chevron-back" size={20} color={colors.textPrimary} />
          <Text style={{ color: colors.textPrimary, fontSize: 15 }}>Retour</Text>
        </TouchableOpacity>
        <Overline>Configuration</Overline>
        <Text style={styles.title}>Gestion du risque</Text>
        <Text style={styles.subtitle}>Paramètres SL/TP, exposition et limites journalières</Text>

        {error ? <View style={styles.errBox}><Text style={{ color: colors.danger }}>{error}</Text></View> : null}
        {success ? <View style={styles.okBox} testID="risk-save-success"><Ionicons name="checkmark-circle" size={16} color={colors.success} /><Text style={{ color: colors.success, fontSize: 13, fontWeight: "600" }}>Risque sauvegardé</Text></View> : null}

        <SectionTitle>Exposition</SectionTitle>
        <Card>
          <Input label="Allocation capital (%)" value={`${r.capital_allocation_pct}`} onChangeText={(v) => updNum("capital_allocation_pct", v)} keyboardType="numeric" testID="risk-allocation-input" />
          <Input label="Risque par trade (% du capital alloué)" value={`${r.risk_per_trade_pct}`} onChangeText={(v) => updNum("risk_per_trade_pct", v)} keyboardType="numeric" testID="risk-pertrade-input" />
        </Card>

        <SectionTitle>Stop Loss / Take Profit</SectionTitle>
        <Card>
          <Input label="Stop Loss (%)" value={`${r.stop_loss_pct}`} onChangeText={(v) => updNum("stop_loss_pct", v)} keyboardType="numeric" testID="risk-sl-input" />
          <Input label="Take Profit (%)" value={`${r.take_profit_pct}`} onChangeText={(v) => updNum("take_profit_pct", v)} keyboardType="numeric" testID="risk-tp-input" />
          <Input label="Ratio Risk/Reward (TP = R/R × SL)" value={`${r.risk_reward_ratio}`} onChangeText={(v) => updNum("risk_reward_ratio", v)} keyboardType="numeric" testID="risk-rr-input" />
        </Card>

        <SectionTitle>Limites</SectionTitle>
        <Card>
          <Input label="Drawdown journalier max (%)" value={`${r.daily_drawdown_limit_pct}`} onChangeText={(v) => updNum("daily_drawdown_limit_pct", v)} keyboardType="numeric" testID="risk-dd-input" />
          <Input label="Positions ouvertes max" value={`${r.max_open_positions}`} onChangeText={(v) => updInt("max_open_positions", v)} keyboardType="numeric" testID="risk-maxopen-input" />
          <Input label="Trades par jour max" value={`${r.max_trades_per_day}`} onChangeText={(v) => updInt("max_trades_per_day", v)} keyboardType="numeric" testID="risk-maxtrades-input" />
          <View style={styles.switchRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.switchLabel}>Pause sur volatilité extrême</Text>
              <Text style={styles.switchHint}>Suspend l'ouverture si stddev relative {">"} 5%</Text>
            </View>
            <Switch
              testID="risk-volpause-switch"
              value={r.volatility_pause}
              onValueChange={(v) => upd("volatility_pause", v)}
              trackColor={{ false: colors.borderStrong, true: colors.primary }}
            />
          </View>
        </Card>

        <Button title="Enregistrer la gestion du risque" onPress={save} loading={busy} testID="risk-save-button" icon="save" style={{ marginTop: spacing.md }} />
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
  switchRow: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm },
  switchLabel: { fontSize: 14, fontWeight: "600", color: colors.textPrimary },
  switchHint: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  errBox: { backgroundColor: colors.dangerBg, padding: 10, borderRadius: 8, marginTop: spacing.sm },
  okBox: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.successBg, padding: 10, borderRadius: 8, marginTop: spacing.sm },
});
