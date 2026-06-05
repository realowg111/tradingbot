import React, { useEffect, useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Switch } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { Card, Button, Badge, SectionTitle, Input, Overline } from "@/src/components/ui";
import { colors, spacing, radius } from "@/src/theme";
import { apiGet, apiPut } from "@/src/api/client";

type StrategyInfo = { id: string; name: string; description: string };

export default function StrategiesScreen() {
  const [list, setList] = useState<StrategyInfo[]>([]);
  const [config, setConfig] = useState<any>(null);
  const [enabled, setEnabled] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [l, c] = await Promise.all([apiGet<StrategyInfo[]>("/strategies/list"), apiGet("/bot/config")]);
      setList(l);
      setConfig(c);
      setEnabled(c.strategy.enabled || []);
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const toggleStrat = (id: string) => {
    setEnabled((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
    setSuccess(false);
  };

  const save = async () => {
    setBusy(true); setError(null); setSuccess(false);
    try {
      const updated = { ...config.strategy, enabled };
      await apiPut("/bot/strategy", updated);
      setSuccess(true);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const updateParam = (key: string, value: string) => {
    const num = parseFloat(value);
    if (!isNaN(num)) {
      setConfig((c: any) => ({ ...c, strategy: { ...c.strategy, [key]: num } }));
      setSuccess(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Overline>Configuration</Overline>
        <Text style={styles.title}>Stratégies</Text>
        <Text style={styles.subtitle}>Sélectionnez et configurez les stratégies actives</Text>

        {error ? <View style={styles.errorBox}><Text style={{ color: colors.danger }}>{error}</Text></View> : null}
        {success ? (
          <View style={styles.successBox} testID="strategy-save-success">
            <Ionicons name="checkmark-circle" size={16} color={colors.success} />
            <Text style={{ color: colors.success, fontSize: 13, fontWeight: "600" }}>Stratégies sauvegardées</Text>
          </View>
        ) : null}

        <SectionTitle>Stratégies disponibles</SectionTitle>
        {list.map((s) => {
          const isOn = enabled.includes(s.id);
          return (
            <Card key={s.id} style={{ marginBottom: spacing.sm }} testID={`strategy-card-${s.id}`}>
              <View style={styles.stratRow}>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                    <Text style={styles.stratName}>{s.name}</Text>
                    {isOn ? <Badge variant="success">ACTIVÉE</Badge> : null}
                  </View>
                  <Text style={styles.stratDesc}>{s.description}</Text>
                </View>
                <Switch
                  testID={`strategy-toggle-${s.id}`}
                  value={isOn}
                  onValueChange={() => toggleStrat(s.id)}
                  trackColor={{ false: colors.borderStrong, true: colors.primary }}
                  thumbColor={colors.white}
                />
              </View>
            </Card>
          );
        })}

        {/* Indicator parameters */}
        {config && (
          <>
            <SectionTitle>Paramètres des indicateurs</SectionTitle>
            <Card>
              <Text style={styles.paramGroup}>RSI</Text>
              <View style={styles.row2}>
                <View style={{ flex: 1 }}><Input label="Période" value={`${config.strategy.rsi_period}`} onChangeText={(v) => updateParam("rsi_period", v)} keyboardType="numeric" testID="rsi-period-input" /></View>
                <View style={{ flex: 1 }}><Input label="Survente" value={`${config.strategy.rsi_oversold}`} onChangeText={(v) => updateParam("rsi_oversold", v)} keyboardType="numeric" testID="rsi-oversold-input" /></View>
                <View style={{ flex: 1 }}><Input label="Surachat" value={`${config.strategy.rsi_overbought}`} onChangeText={(v) => updateParam("rsi_overbought", v)} keyboardType="numeric" testID="rsi-overbought-input" /></View>
              </View>

              <Text style={styles.paramGroup}>EMA</Text>
              <View style={styles.row2}>
                <View style={{ flex: 1 }}><Input label="EMA rapide" value={`${config.strategy.ema_fast}`} onChangeText={(v) => updateParam("ema_fast", v)} keyboardType="numeric" testID="ema-fast-input" /></View>
                <View style={{ flex: 1 }}><Input label="EMA lente" value={`${config.strategy.ema_slow}`} onChangeText={(v) => updateParam("ema_slow", v)} keyboardType="numeric" testID="ema-slow-input" /></View>
              </View>

              <Text style={styles.paramGroup}>MACD</Text>
              <View style={styles.row2}>
                <View style={{ flex: 1 }}><Input label="Rapide" value={`${config.strategy.macd_fast}`} onChangeText={(v) => updateParam("macd_fast", v)} keyboardType="numeric" testID="macd-fast-input" /></View>
                <View style={{ flex: 1 }}><Input label="Lent" value={`${config.strategy.macd_slow}`} onChangeText={(v) => updateParam("macd_slow", v)} keyboardType="numeric" testID="macd-slow-input" /></View>
                <View style={{ flex: 1 }}><Input label="Signal" value={`${config.strategy.macd_signal}`} onChangeText={(v) => updateParam("macd_signal", v)} keyboardType="numeric" testID="macd-signal-input" /></View>
              </View>

              <Text style={styles.paramGroup}>Bollinger Bands</Text>
              <View style={styles.row2}>
                <View style={{ flex: 1 }}><Input label="Période" value={`${config.strategy.bb_period}`} onChangeText={(v) => updateParam("bb_period", v)} keyboardType="numeric" testID="bb-period-input" /></View>
                <View style={{ flex: 1 }}><Input label="Écart-type" value={`${config.strategy.bb_std}`} onChangeText={(v) => updateParam("bb_std", v)} keyboardType="numeric" testID="bb-std-input" /></View>
              </View>
            </Card>
          </>
        )}

        <Button title="Enregistrer les stratégies" onPress={save} loading={busy} testID="strategy-save-button" style={{ marginTop: spacing.md }} icon="save" />
        <View style={{ height: spacing.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  scroll: { padding: spacing.md },
  title: { fontSize: 28, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.8, marginTop: 4 },
  subtitle: { fontSize: 13, color: colors.textSecondary, marginTop: 4 },
  stratRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  stratName: { fontSize: 15, fontWeight: "700", color: colors.textPrimary },
  stratDesc: { fontSize: 12, color: colors.textSecondary, marginTop: 4 },
  paramGroup: { fontSize: 11, color: colors.textSecondary, fontWeight: "700", textTransform: "uppercase", letterSpacing: 1.5, marginTop: spacing.md, marginBottom: spacing.sm },
  row2: { flexDirection: "row", gap: spacing.sm },
  errorBox: { backgroundColor: colors.dangerBg, padding: 10, borderRadius: 8, marginTop: spacing.sm },
  successBox: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.successBg, padding: 10, borderRadius: 8, marginTop: spacing.sm },
});
