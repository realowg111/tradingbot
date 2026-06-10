import React, { useEffect, useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import * as Clipboard from "expo-clipboard";

import { Card, Button, Input, SectionTitle, Overline, Badge } from "@/src/components/ui";
import { colors, spacing, fmt, radius } from "@/src/theme";
import { apiGet, apiPost, apiPatch } from "@/src/api/client";
import { useToast } from "@/src/components/Toast";

export default function MT5Screen() {
  const router = useRouter();
  const toast = useToast();
  const [existing, setExisting] = useState<any>(null);
  const [mt5Status, setMt5Status] = useState<any>(null);
  const [mt5Account, setMt5Account] = useState<any>(null);
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [server, setServer] = useState("");
  const [broker, setBroker] = useState("");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshAll = useCallback(async () => {
    try {
      const [creds, st] = await Promise.all([
        apiGet("/mt5/credentials").catch(() => null),
        apiGet("/mt5/status").catch(() => null),
      ]);
      if (creds) {
        setExisting(creds);
        setLogin(creds.login);
        setServer(creds.server);
        setBroker(creds.broker || "");
        setPath(creds.path || "");
      }
      if (st) {
        setMt5Status(st.status);
        setMt5Account(st.account);
      }
    } catch {}
  }, []);

  useFocusEffect(useCallback(() => {
    let interval: any;
    refreshAll();
    interval = setInterval(refreshAll, 3000);
    return () => clearInterval(interval);
  }, [refreshAll]));

  const save = async () => {
    setError(null);
    if (!login || !server) { setError("Login et serveur requis"); return; }
    if (!existing && !password) { setError("Mot de passe requis pour la première sauvegarde"); return; }
    setBusy(true);
    try {
      await apiPost("/mt5/credentials", { login, password: password || null, server, broker, path: path || null });
      toast.show({ type: "success", title: "Identifiants chiffrés", message: "AES-256 sauvegardés en sécurité" });
      setPassword("");
      await refreshAll();
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  };

  const savePathOnly = async () => {
    if (!path) { toast.show({ type: "warning", title: "Champ vide", message: "Renseigne le chemin d'abord" }); return; }
    setBusy(true);
    try {
      await apiPatch("/mt5/credentials/path", { path });
      toast.show({ type: "success", title: "Chemin sauvegardé", message: "Cliquez Connecter à MT5 pour tester" });
      await refreshAll();
    } catch (e: any) {
      toast.show({ type: "danger", title: "Erreur", message: e.message });
    } finally { setBusy(false); }
  };

  const connect = async () => {
    setConnecting(true);
    try {
      const r = await apiPost<any>("/mt5/connect");
      if (r.connected) {
        toast.show({ type: "success", title: "MT5 connecté", message: `Mode ${r.mode === "native" ? "natif Windows" : "bridge"}` });
      } else {
        toast.show({ type: "warning", title: "MT5 non connecté", message: r.last_error || "Connexion refusée" });
      }
      await refreshAll();
    } catch (e: any) {
      toast.show({ type: "danger", title: "Erreur", message: e.message });
    } finally {
      setConnecting(false);
    }
  };

  const disconnect = async () => {
    try {
      await apiPost("/mt5/disconnect");
      toast.show({ type: "info", title: "MT5 déconnecté" });
      await refreshAll();
    } catch (e: any) {
      toast.show({ type: "danger", title: "Erreur", message: e.message });
    }
  };

  const isConnected = mt5Status?.connected;
  const hasNative = mt5Status?.has_native_lib;
  const hasBridge = mt5Status?.has_bridge_url;
  const canConnect = (hasNative || hasBridge) && existing;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backRow} testID="mt5-back">
          <Ionicons name="chevron-back" size={20} color={colors.textPrimary} />
          <Text style={{ color: colors.textPrimary, fontSize: 15 }}>Retour</Text>
        </TouchableOpacity>
        <Overline>Connexion broker</Overline>
        <Text style={styles.title}>MetaTrader 5</Text>

        {/* Live status card */}
        <View style={[styles.statusCard, { borderColor: isConnected ? colors.success : colors.warning }]}>
          <View style={styles.statusHeader}>
            <View style={[styles.statusIconBox, { backgroundColor: isConnected ? colors.successBg : colors.warningBg }]}>
              <Ionicons name={isConnected ? "checkmark-circle" : "alert-circle"} size={24} color={isConnected ? colors.success : colors.warning} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.statusTitle}>{isConnected ? "MT5 connecté en live" : "MT5 non connecté"}</Text>
              <Text style={styles.statusSubtitle}>
                {isConnected
                  ? `Mode ${mt5Status.mode === "native" ? "natif (Windows)" : "bridge HTTP"} · ${mt5Status.login}@${mt5Status.server}`
                  : hasNative
                    ? "Lib MetaTrader5 disponible. Cliquez sur Connecter pour synchroniser."
                    : hasBridge
                      ? "Bridge HTTP configuré. Cliquez sur Connecter."
                      : "Aucune lib MT5 disponible (backend Linux). Le simulateur reste actif. Configurez un bridge agent sur Windows pour activer le live."}
              </Text>
            </View>
          </View>

          {mt5Status?.last_error ? (
            <View style={styles.errorRow}>
              <Ionicons name="warning-outline" size={14} color={colors.danger} />
              <Text style={styles.errorRowText}>{mt5Status.last_error}</Text>
            </View>
          ) : null}

          {/* Live account data */}
          {isConnected && mt5Account ? (
            <View style={styles.accountGrid}>
              <AccountStat label="Balance" value={fmt.money(mt5Account.balance, mt5Account.currency || "USD")} />
              <AccountStat label="Equity" value={fmt.money(mt5Account.equity, mt5Account.currency || "USD")} />
              <AccountStat label="Margin libre" value={fmt.money(mt5Account.free_margin, mt5Account.currency || "USD")} />
              <AccountStat label="Profit" value={fmt.money(mt5Account.profit, mt5Account.currency || "USD")} accent={mt5Account.profit >= 0 ? colors.success : colors.danger} />
            </View>
          ) : null}

          {/* Connect / disconnect actions */}
          <View style={{ flexDirection: "row", gap: 8, marginTop: spacing.md }}>
            {isConnected ? (
              <Button title="Se déconnecter" variant="outline" onPress={disconnect} icon="log-out-outline" testID="mt5-disconnect-button" style={{ flex: 1 }} />
            ) : (
              <Button
                title="Connecter à MT5"
                onPress={connect}
                disabled={!canConnect}
                loading={connecting}
                icon="link-outline"
                testID="mt5-connect-button"
                style={{ flex: 1 }}
              />
            )}
            <Button title="Actualiser" variant="ghost" onPress={refreshAll} icon="refresh" testID="mt5-refresh-button" />
          </View>
        </View>

        {/* Existing credentials */}
        {existing ? (
          <Card style={{ marginTop: spacing.md, backgroundColor: colors.surfaceAlt, borderColor: colors.borderStrong }}>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <View>
                <Text style={styles.existingLabel}>Identifiants chiffrés enregistrés</Text>
                <Text style={styles.existingLogin} testID="mt5-existing-login">Compte: {existing.login}</Text>
                <Text style={styles.existingServer}>Serveur: {existing.server}{existing.broker ? ` · ${existing.broker}` : ""}</Text>
              </View>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                <Ionicons name="lock-closed" size={14} color={colors.success} />
                <Text style={{ color: colors.success, fontSize: 11, fontWeight: "800" }}>AES-256</Text>
              </View>
            </View>
          </Card>
        ) : null}

        {/* Help banner */}
        {!hasNative && !hasBridge ? (
          <Card style={{ marginTop: spacing.md, backgroundColor: colors.warningBg, borderColor: "#FCD34D" }}>
            <View style={{ flexDirection: "row", gap: 8, alignItems: "flex-start" }}>
              <Ionicons name="information-circle" size={18} color={colors.warning} />
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 13, fontWeight: "700", color: "#92400E", marginBottom: 4 }}>Activer la synchro live MT5</Text>
                <Text style={{ fontSize: 12, color: "#92400E", lineHeight: 18 }}>
                  Notre backend tourne sur Linux. La librairie MetaTrader5 nécessite Windows. 2 options :{"\n\n"}
                  <Text style={{ fontWeight: "700" }}>1. Backend Windows</Text> : déployer le code sur un VPS Windows + installer `pip install MetaTrader5`.{"\n"}
                  <Text style={{ fontWeight: "700" }}>2. Bridge Agent</Text> : lancer notre script `scripts/mt5_agent.py` sur votre PC/VPS Windows (avec MT5 + Python), puis configurer `MT5_BRIDGE_URL=http://...` dans le `.env` du backend.{"\n\n"}
                  En attendant, le simulateur interne reste actif et fournit du paper trading réaliste.
                </Text>
              </View>
            </View>
          </Card>
        ) : null}

        {/* Specific tip for VPS service not finding MT5 */}
        {hasNative && !isConnected && mt5Status?.last_error?.includes("introuvable") ? (
          <Card style={{ marginTop: spacing.md, backgroundColor: "#EEF2FF", borderColor: "#C7D2FE", borderWidth: 1 }}>
            <View style={{ flexDirection: "row", gap: 8, alignItems: "flex-start" }}>
              <Ionicons name="bulb-outline" size={18} color={colors.primary} />
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 13, fontWeight: "800", color: colors.primary, marginBottom: 6 }}>
                  Comment résoudre sur votre VPS Windows
                </Text>
                <Text style={{ fontSize: 12, color: colors.textPrimary, lineHeight: 18 }}>
                  Le backend tourne en tant que service Windows (compte SYSTEM) → il ne voit pas le MT5 ouvert dans votre session.{"\n\n"}
                  <Text style={{ fontWeight: "700" }}>Solution la plus simple :</Text> renseignez le <Text style={{ fontWeight: "700" }}>chemin complet vers terminal64.exe</Text> dans le formulaire ci-dessous. La lib lancera MT5 automatiquement.{"\n\n"}
                  <Text style={{ fontWeight: "700" }}>Chemin typique RoboForex :</Text>{"\n"}
                  <Text style={{ fontFamily: "Courier", fontSize: 11 }}>
                    C:\Program Files\RoboForex - MetaTrader 5\terminal64.exe
                  </Text>{"\n\n"}
                  {"Pour le trouver : clic droit sur l'icône MT5 du bureau → Propriétés → Cible."}
                </Text>
              </View>
            </View>
          </Card>
        ) : null}

        {/* Credentials form */}
        <SectionTitle>{existing ? "Mettre à jour les identifiants" : "Saisir les identifiants"}</SectionTitle>
        <Card>
          <Input label="Login MT5 (numéro de compte)" value={login} onChangeText={setLogin} placeholder="12345678" keyboardType="numeric" testID="mt5-login-input" />
          <Input label="Mot de passe (chiffré AES-256)" value={password} onChangeText={setPassword} placeholder="••••••••" secureTextEntry testID="mt5-password-input" />
          <Input label="Serveur" value={server} onChangeText={setServer} placeholder="ICMarketsSC-Demo" autoCapitalize="none" testID="mt5-server-input" />
          <Input label="Broker (optionnel)" value={broker} onChangeText={setBroker} placeholder="RoboForex" testID="mt5-broker-input" />

          {/* Path field — dedicated TextInput with paste button (handles long backslash paths) */}
          <View style={{ marginBottom: 16 }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <Text style={styles.pathLabel}>{"Chemin terminal64.exe (recommandé sur VPS)"}</Text>
              <TouchableOpacity
                onPress={async () => {
                  try {
                    const txt = await Clipboard.getStringAsync();
                    if (txt) {
                      // Strip wrapping quotes that Windows "Copy as path" adds
                      const cleaned = txt.replace(/^["']|["']$/g, "").trim();
                      setPath(cleaned);
                      toast.show({ type: "success", title: "Chemin collé", message: cleaned.length > 40 ? cleaned.slice(0, 40) + "…" : cleaned });
                    } else {
                      toast.show({ type: "warning", title: "Presse-papiers vide" });
                    }
                  } catch {
                    toast.show({ type: "danger", title: "Impossible de coller", message: "Permission refusée" });
                  }
                }}
                style={styles.pasteBtn}
                testID="mt5-path-paste"
              >
                <Ionicons name="clipboard-outline" size={14} color={colors.primary} />
                <Text style={styles.pasteBtnText}>Coller</Text>
              </TouchableOpacity>
            </View>
            <View style={styles.pathInputWrap}>
              <TextInput
                value={path}
                onChangeText={setPath}
                placeholder="C:\Program Files\RoboForex - MetaTrader 5\terminal64.exe"
                placeholderTextColor={colors.textMuted}
                style={styles.pathInput}
                autoCapitalize="none"
                autoCorrect={false}
                spellCheck={false}
                autoComplete="off"
                multiline={false}
                testID="mt5-path-input"
                {...({ dataDetectorTypes: "none" } as any)}
              />
              {path ? (
                <TouchableOpacity onPress={() => setPath("")} style={styles.clearBtn} testID="mt5-path-clear">
                  <Ionicons name="close-circle" size={18} color={colors.textMuted} />
                </TouchableOpacity>
              ) : null}
            </View>
            <Text style={styles.pathHint}>
              {"Astuce : sur le VPS, clic droit sur l'icône MT5 → Copier comme chemin d'accès → cliquez 'Coller' ci-dessus."}
            </Text>
          </View>
          {mt5Status?.autodetected_path && !path ? (
            <Text style={{ fontSize: 11, color: colors.success, marginTop: -8, marginBottom: 12 }}>
              {"✓ Détecté automatiquement : "}{mt5Status.autodetected_path}
            </Text>
          ) : null}
          {error ? <Text style={{ color: colors.danger, fontSize: 13, marginBottom: 8 }}>{error}</Text> : null}
          <Button title="Chiffrer & sauvegarder" onPress={save} loading={busy} icon="lock-closed" testID="mt5-save-button" />
          {existing && path && path !== existing.path ? (
            <View style={{ marginTop: 8 }}>
              <Button
                title="Sauvegarder uniquement le chemin"
                onPress={savePathOnly}
                loading={busy}
                variant="outline"
                icon="folder-outline"
                testID="mt5-save-path-only-button"
              />
              <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 6, textAlign: "center", fontStyle: "italic" }}>
                {"Met à jour le chemin sans toucher au login/mot de passe."}
              </Text>
            </View>
          ) : null}
        </Card>

        <View style={{ height: spacing.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function AccountStat({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <View style={styles.accountStat}>
      <Text style={styles.accountStatLabel}>{label}</Text>
      <Text style={[styles.accountStatValue, accent ? { color: accent } : null]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  scroll: { padding: spacing.md },
  backRow: { flexDirection: "row", alignItems: "center", gap: 4, marginBottom: spacing.md },
  title: { fontSize: 28, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.8, marginTop: 4, marginBottom: spacing.md },

  statusCard: {
    backgroundColor: colors.white,
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 2,
  },
  statusHeader: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
  statusIconBox: { width: 40, height: 40, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  statusTitle: { fontSize: 16, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.3 },
  statusSubtitle: { fontSize: 12, color: colors.textSecondary, marginTop: 4, lineHeight: 18 },

  errorRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.sm, padding: 8, backgroundColor: colors.dangerBg, borderRadius: 6 },
  errorRowText: { color: colors.danger, fontSize: 11, flex: 1 },

  accountGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: spacing.md, paddingTop: spacing.md, borderTopColor: colors.border, borderTopWidth: 1 },
  accountStat: { flexBasis: "48%", flexGrow: 1 },
  accountStatLabel: { fontSize: 10, color: colors.textSecondary, textTransform: "uppercase", letterSpacing: 1, fontWeight: "700" },
  accountStatValue: { fontSize: 15, fontWeight: "800", color: colors.textPrimary, marginTop: 2, letterSpacing: -0.3 },

  existingLabel: { fontSize: 10, color: colors.textSecondary, fontWeight: "700", textTransform: "uppercase", letterSpacing: 1 },
  existingLogin: { fontSize: 14, color: colors.textPrimary, fontWeight: "700", marginTop: 2 },
  existingServer: { fontSize: 12, color: colors.textSecondary, marginTop: 2 },

  pathLabel: { fontSize: 12, fontWeight: "600", color: colors.textSecondary, textTransform: "uppercase", letterSpacing: 1, flex: 1 },
  pasteBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: 10, paddingVertical: 4,
    backgroundColor: "#EEF2FF", borderRadius: radius.sm,
    borderWidth: 1, borderColor: "#C7D2FE",
  },
  pasteBtnText: { fontSize: 11, fontWeight: "700", color: colors.primary, letterSpacing: 0.3 },
  pathInputWrap: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.white,
    borderColor: colors.borderStrong, borderWidth: 1,
    borderRadius: radius.md, paddingHorizontal: 14,
    minHeight: 48,
  },
  pathInput: {
    flex: 1, paddingVertical: 12,
    fontSize: 13, color: colors.textPrimary,
    fontFamily: "monospace",
  },
  clearBtn: { padding: 6 },
  pathHint: { fontSize: 11, color: colors.textMuted, marginTop: 6, fontStyle: "italic" },
});
