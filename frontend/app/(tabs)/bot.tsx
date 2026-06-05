import React, { useEffect, useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Modal, TextInput } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect } from "expo-router";

import { Card, Button, Badge, SectionTitle, Stat, Overline } from "@/src/components/ui";
import { colors, fmt, spacing, radius } from "@/src/theme";
import { apiGet, apiPost } from "@/src/api/client";

export default function BotControl() {
  const [data, setData] = useState<any>(null);
  const [config, setConfig] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showRealModal, setShowRealModal] = useState(false);
  const [phrase, setPhrase] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [st, cfg] = await Promise.all([apiGet("/bot/state"), apiGet("/bot/config")]);
      setData(st);
      setConfig(cfg);
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    let interval: any;
    refresh();
    interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  }, [refresh]));

  const toggleBot = async () => {
    setBusy(true); setError(null);
    try { await apiPost("/bot/toggle"); await refresh(); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  const killSwitch = async () => {
    setBusy(true); setError(null);
    try { await apiPost("/bot/kill-switch"); await refresh(); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  const resetKill = async () => {
    setBusy(true);
    try { await apiPost("/bot/kill-switch/reset"); await refresh(); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  const switchToDemo = async () => {
    setBusy(true); setError(null);
    try { await apiPost("/bot/mode", { target_mode: "demo" }); await refresh(); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  const confirmReal = async () => {
    setBusy(true); setError(null);
    try {
      await apiPost("/bot/mode", { target_mode: "real", confirmation_phrase: phrase });
      setShowRealModal(false);
      setPhrase("");
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const resetPaper = async () => {
    setBusy(true);
    try { await apiPost("/bot/reset-paper"); await refresh(); }
    catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };

  const state = data?.state;
  const mode = data?.config_mode ?? "demo";
  const enabled = data?.config_enabled ?? false;
  const killEngaged = state?.kill_switch_engaged;

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Overline>Console</Overline>
        <Text style={styles.title}>Contrôle du Bot</Text>

        {error ? <View style={styles.errorBanner} testID="bot-error"><Text style={{ color: colors.danger, fontSize: 13 }}>{error}</Text></View> : null}

        {/* Mode */}
        <SectionTitle>Mode d'exécution</SectionTitle>
        <Card>
          <View style={styles.modeRow}>
            <View>
              <Text style={styles.modeLabel}>Mode actuel</Text>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginTop: 6 }}>
                <Badge variant={mode === "demo" ? "demo" : "real"} testID="current-mode-badge">{mode === "demo" ? "DÉMO" : "RÉEL"}</Badge>
                {state?.real_unlocked ? <Badge variant="success">RÉEL DÉBLOQUÉ</Badge> : null}
              </View>
            </View>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <Button title="Démo" variant={mode === "demo" ? "primary" : "outline"} onPress={switchToDemo} testID="switch-demo-button" />
              <Button title="Réel" variant={mode === "real" ? "primary" : "outline"} onPress={() => setShowRealModal(true)} testID="switch-real-button" />
            </View>
          </View>
          {mode === "demo" ? (
            <Text style={styles.modeHint} testID="mode-hint">
              💡 Paper trading sans engagement financier. Validation min: {config?.paper_validation_days ?? 7} jours + 10 trades + winrate ≥ 40% pour activer le mode réel.
            </Text>
          ) : (
            <Text style={styles.modeHint}>⚠️ Mode RÉEL — Capital réel exposé. Validation manuelle requise pour chaque changement.</Text>
          )}
        </Card>

        {/* ON/OFF */}
        <SectionTitle>Activation</SectionTitle>
        <Card>
          <View style={{ alignItems: "center", padding: spacing.md }}>
            <TouchableOpacity
              testID="bot-onoff-button"
              onPress={toggleBot}
              disabled={busy || killEngaged}
              activeOpacity={0.8}
              style={[
                styles.onoffButton,
                { backgroundColor: enabled ? colors.success : colors.surfaceAlt, borderColor: enabled ? colors.success : colors.borderStrong },
                (busy || killEngaged) && { opacity: 0.5 },
              ]}
            >
              <Ionicons name="power" size={48} color={enabled ? colors.white : colors.textSecondary} />
              <Text style={[styles.onoffText, { color: enabled ? colors.white : colors.textSecondary }]}>
                {enabled ? "ACTIF" : "ARRÊTÉ"}
              </Text>
            </TouchableOpacity>
            <Text style={styles.onoffHint}>Toucher pour {enabled ? "désactiver" : "activer"} le bot</Text>
          </View>
        </Card>

        {/* Kill Switch */}
        <SectionTitle>Urgence</SectionTitle>
        <Card>
          {killEngaged ? (
            <View>
              <View style={styles.killStatus}>
                <Ionicons name="warning" size={20} color={colors.danger} />
                <Text style={{ color: colors.danger, fontWeight: "700", flex: 1 }}>Kill Switch engagé — toutes positions fermées</Text>
              </View>
              <Button title="Réarmer (autoriser nouveau trading)" onPress={resetKill} variant="outline" testID="kill-reset-button" loading={busy} />
            </View>
          ) : (
            <View>
              <Text style={styles.killWarn}>Arrêt d'urgence immédiat : ferme TOUTES les positions ouvertes et désactive le bot.</Text>
              <TouchableOpacity
                testID="kill-switch-button"
                onPress={killSwitch}
                disabled={busy}
                activeOpacity={0.85}
                style={styles.killButton}
              >
                <Ionicons name="warning" size={24} color={colors.white} />
                <Text style={styles.killButtonText}>KILL SWITCH</Text>
              </TouchableOpacity>
            </View>
          )}
        </Card>

        {/* Paper actions */}
        {mode === "demo" && (
          <>
            <SectionTitle>Outils Démo</SectionTitle>
            <Card>
              <Text style={{ fontSize: 13, color: colors.textSecondary, marginBottom: spacing.md }}>
                Réinitialise le solde démo et efface l'historique des trades simulés (le mode réel n'est pas affecté).
              </Text>
              <Button title="Reset Paper Trading" onPress={resetPaper} variant="outline" testID="reset-paper-button" icon="refresh" loading={busy} />
            </Card>
          </>
        )}

        {/* State summary */}
        <SectionTitle>État actuel</SectionTitle>
        <Card>
          <View style={styles.summaryGrid}>
            <Stat label="Balance" value={fmt.money(state?.balance, "USD")} testID="summary-balance" />
            <Stat label="Équity" value={fmt.money(state?.equity, "USD")} testID="summary-equity" />
          </View>
          <View style={[styles.summaryGrid, { marginTop: spacing.md }]}>
            <Stat label="Positions ouvertes" value={`${state?.open_positions ?? 0}`} testID="summary-positions" />
            <Stat label="Trades aujourd'hui" value={`${state?.trades_today ?? 0}`} testID="summary-trades-today" />
          </View>
          {state?.paused_reason ? (
            <View style={styles.pausedBox}>
              <Ionicons name="pause-circle" size={16} color={colors.warning} />
              <Text style={{ color: "#92400E", fontSize: 12, fontWeight: "600" }}>Pause: {state.paused_reason}</Text>
            </View>
          ) : null}
        </Card>

        <View style={{ height: spacing.xxl }} />
      </ScrollView>

      {/* Modal validation passage réel */}
      <Modal visible={showRealModal} animationType="slide" transparent onRequestClose={() => setShowRealModal(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalBox}>
            <View style={styles.modalHeader}>
              <Ionicons name="alert-circle" size={24} color={colors.warning} />
              <Text style={styles.modalTitle}>Validation Mode RÉEL</Text>
            </View>
            <Text style={styles.modalText}>
              Passage en capital réel. Avant validation, le bot vérifiera :{"\n"}
              • Min {config?.paper_validation_days ?? 7} jours de paper trading{"\n"}
              • Min 10 trades démo{"\n"}
              • Winrate ≥ 40%{"\n\n"}
              Saisissez exactement la phrase ci-dessous :
            </Text>
            <View style={styles.phraseBox}>
              <Text style={styles.phraseText} selectable>JE CONFIRME LE PASSAGE EN REEL</Text>
            </View>
            <TextInput
              testID="real-confirm-input"
              value={phrase}
              onChangeText={setPhrase}
              placeholder="Saisir la phrase…"
              placeholderTextColor={colors.textMuted}
              style={styles.modalInput}
              autoCapitalize="characters"
            />
            <View style={{ flexDirection: "row", gap: 8, marginTop: spacing.md }}>
              <Button title="Annuler" variant="outline" onPress={() => { setShowRealModal(false); setPhrase(""); setError(null); }} style={{ flex: 1 }} testID="real-cancel-button" />
              <Button title="Confirmer RÉEL" variant="danger" onPress={confirmReal} loading={busy} style={{ flex: 1 }} testID="real-confirm-button" />
            </View>
            {error ? <Text style={{ color: colors.danger, fontSize: 12, marginTop: 10 }}>{error}</Text> : null}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  scroll: { padding: spacing.md },
  title: { fontSize: 28, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.8, marginTop: 4 },
  modeRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: spacing.md },
  modeLabel: { fontSize: 13, color: colors.textSecondary, fontWeight: "600" },
  modeHint: { fontSize: 12, color: colors.textSecondary, marginTop: spacing.md, lineHeight: 18 },
  onoffButton: {
    width: 160, height: 160, borderRadius: 80, borderWidth: 3,
    alignItems: "center", justifyContent: "center", gap: 4,
  },
  onoffText: { fontSize: 18, fontWeight: "800", letterSpacing: 2 },
  onoffHint: { fontSize: 12, color: colors.textMuted, marginTop: spacing.md },
  killButton: {
    backgroundColor: colors.killSwitch,
    flexDirection: "row", alignItems: "center", justifyContent: "center",
    gap: 12, paddingVertical: 22, borderRadius: radius.md,
    borderColor: "#7F1D1D", borderWidth: 2,
    shadowColor: colors.danger, shadowOpacity: 0.4, shadowRadius: 12, shadowOffset: { width: 0, height: 0 }, elevation: 6,
  },
  killButtonText: { color: colors.white, fontSize: 18, fontWeight: "900", letterSpacing: 3 },
  killWarn: { fontSize: 13, color: colors.textSecondary, marginBottom: spacing.md, lineHeight: 18 },
  killStatus: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: colors.dangerBg, padding: 12, borderRadius: 8, marginBottom: spacing.md },
  summaryGrid: { flexDirection: "row", gap: spacing.md },
  pausedBox: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.md, padding: 8, backgroundColor: colors.warningBg, borderRadius: 6 },
  errorBanner: { backgroundColor: colors.dangerBg, padding: 10, borderRadius: 8, marginTop: spacing.sm },
  modalBackdrop: { flex: 1, backgroundColor: "rgba(15,23,42,0.6)", justifyContent: "center", padding: spacing.lg },
  modalBox: { backgroundColor: colors.white, borderRadius: radius.lg, padding: spacing.lg },
  modalHeader: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: spacing.md },
  modalTitle: { fontSize: 18, fontWeight: "800", color: colors.textPrimary },
  modalText: { fontSize: 13, color: colors.textSecondary, lineHeight: 20 },
  phraseBox: { backgroundColor: colors.surfaceAlt, padding: 10, borderRadius: 6, marginTop: spacing.md },
  phraseText: { fontFamily: "Courier", fontSize: 13, color: colors.textPrimary, textAlign: "center", fontWeight: "700" },
  modalInput: { borderColor: colors.borderStrong, borderWidth: 1, borderRadius: radius.md, padding: 12, marginTop: spacing.md, fontSize: 14, color: colors.textPrimary, fontFamily: "Courier" },
});
