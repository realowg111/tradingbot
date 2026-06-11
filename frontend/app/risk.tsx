import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Switch } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { Card, Button, Input, SectionTitle, Overline } from "@/src/components/ui";
import { colors, spacing } from "@/src/theme";
import { apiGet, apiPut, apiPost } from "@/src/api/client";

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
      // Also persist strategy + top-level paper validation fields via config update
      // (we PUT strategy too so paper_validation fields get saved via re-fetch)
      await apiPut("/bot/strategy", config.strategy);
      // Persist config-level toggles (paper_validation_*, live_mt5_trading_enabled)
      await apiPost("/bot/config-flags", {
        paper_validation_enabled: config.paper_validation_enabled,
        paper_validation_days: config.paper_validation_days,
        paper_validation_min_trades: config.paper_validation_min_trades,
        paper_validation_min_winrate: config.paper_validation_min_winrate,
        live_mt5_trading_enabled: config.live_mt5_trading_enabled,
      });
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
              <Text style={styles.switchHint}>{"Suspend l'ouverture si stddev relative > 5%"}</Text>
            </View>
            <Switch
              testID="risk-volpause-switch"
              value={r.volatility_pause}
              onValueChange={(v) => upd("volatility_pause", v)}
              trackColor={{ false: colors.borderStrong, true: colors.primary }}
            />
          </View>
        </Card>

        <SectionTitle>Garde-fous avancés</SectionTitle>
        <Card>
          <Text style={styles.helperText}>
            {"Protections automatiques du capital : le bot arrête de prendre des positions dès qu'une limite est atteinte."}
          </Text>
          <Input label="Perte hebdomadaire max (%)" value={`${r.weekly_loss_limit_pct ?? 10}`} onChangeText={(v) => updNum("weekly_loss_limit_pct", v)} keyboardType="numeric" testID="risk-weekly-input" />
          <Text style={styles.fieldHint}>{"Pause des nouveaux trades si l'équity perd ce % depuis le début de la semaine"}</Text>
          <Input label="Drawdown total max (%)" value={`${r.max_total_drawdown_pct ?? 20}`} onChangeText={(v) => updNum("max_total_drawdown_pct", v)} keyboardType="numeric" testID="risk-maxdd-input" />
          <Text style={styles.fieldHint}>{"Pause si l'équity chute de ce % sous son plus haut historique"}</Text>
          <Input label="Spread max (%)" value={`${r.max_spread_pct ?? 0.1}`} onChangeText={(v) => updNum("max_spread_pct", v)} keyboardType="numeric" testID="risk-spread-input" />
          <Text style={styles.fieldHint}>{"Aucune entrée si l'écart achat/vente dépasse ce % du prix (spread anormal)"}</Text>
        </Card>

        <Button title="Enregistrer la gestion du risque" onPress={save} loading={busy} testID="risk-save-button" icon="save" style={{ marginTop: spacing.md }} />

        {/* Validation passage en mode réel - configurable */}
        <SectionTitle>Validation passage en mode RÉEL</SectionTitle>
        <Card>
          <Text style={styles.helperText}>
            {"Garde-fou avant d'activer le capital réel. Configurez ou désactivez complètement la validation."}
          </Text>
          <View style={styles.switchRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.switchLabel}>Validation paper trading activée</Text>
              <Text style={styles.switchHint}>Si désactivée, passage direct en réel possible</Text>
            </View>
            <Switch
              testID="validation-enabled-switch"
              value={config.paper_validation_enabled}
              onValueChange={(v) => { setConfig((c: any) => ({ ...c, paper_validation_enabled: v })); setSuccess(false); }}
              trackColor={{ false: colors.borderStrong, true: colors.primary }}
            />
          </View>
          {config.paper_validation_enabled ? (
            <View style={{ marginTop: spacing.md }}>
              <Input label="Jours de paper trading minimum" value={`${config.paper_validation_days}`} onChangeText={(v) => { const n = parseInt(v, 10); if (!isNaN(n)) { setConfig((c: any) => ({ ...c, paper_validation_days: n })); setSuccess(false); } }} keyboardType="numeric" testID="validation-days-input" />
              <Input label="Trades démo minimum" value={`${config.paper_validation_min_trades}`} onChangeText={(v) => { const n = parseInt(v, 10); if (!isNaN(n)) { setConfig((c: any) => ({ ...c, paper_validation_min_trades: n })); setSuccess(false); } }} keyboardType="numeric" testID="validation-trades-input" />
              <Input label="Winrate minimum (%)" value={`${config.paper_validation_min_winrate}`} onChangeText={(v) => { const n = parseFloat(v); if (!isNaN(n)) { setConfig((c: any) => ({ ...c, paper_validation_min_winrate: n })); setSuccess(false); } }} keyboardType="numeric" testID="validation-winrate-input" />
            </View>
          ) : (
            <View style={styles.warnBox}>
              <Ionicons name="warning" size={16} color={colors.warning} />
              <Text style={styles.warnText}>Validation désactivée : tu pourras passer en RÉEL immédiatement après la phrase de confirmation. Utilise avec précaution.</Text>
            </View>
          )}
        </Card>

        {/* Live MT5 trading toggle */}
        <SectionTitle>Trading live MT5</SectionTitle>
        <Card>
          <Text style={styles.helperText}>
            Quand activé : le bot place les ordres directement sur MT5 (visibles live dans ton terminal MT5). Nécessite MT5 connecté + mode RÉEL + capital débloqué.
          </Text>
          <View style={styles.switchRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.switchLabel}>Routage des ordres vers MT5</Text>
              <Text style={styles.switchHint}>Sinon : exécution simulée (paper trading)</Text>
            </View>
            <Switch
              testID="live-mt5-switch"
              value={config.live_mt5_trading_enabled}
              onValueChange={(v) => { setConfig((c: any) => ({ ...c, live_mt5_trading_enabled: v })); setSuccess(false); }}
              trackColor={{ false: colors.borderStrong, true: colors.success }}
            />
          </View>
        </Card>

        <Button title="Enregistrer tous les paramètres" onPress={save} loading={busy} testID="risk-save-all-button" icon="save" style={{ marginTop: spacing.md }} variant="primary" />
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
  helperText: { fontSize: 12, color: colors.textSecondary, lineHeight: 18, marginBottom: spacing.md },
  fieldHint: { fontSize: 11, color: colors.textMuted, marginTop: -6, marginBottom: spacing.sm, lineHeight: 16 },
  warnBox: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginTop: spacing.md, padding: 10, backgroundColor: colors.warningBg, borderColor: "#FCD34D", borderWidth: 1, borderRadius: 8 },
  warnText: { color: "#92400E", fontSize: 12, flex: 1, lineHeight: 18 },
});
