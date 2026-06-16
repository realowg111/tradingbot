import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { Card, Button } from "@/src/components/ui";
import { colors, spacing, radius } from "@/src/theme";
import { setBaseUrl, getBaseUrl, getEnvBaseUrl } from "@/src/api/client";

export default function SettingsScreen() {
  const router = useRouter();
  const [currentBase, setCurrentBase] = useState<string>("");
  const [envBase, setEnvBase] = useState<string>("");
  const [input, setInput] = useState<string>("");
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const b = await getBaseUrl();
      const e = getEnvBaseUrl();
      setCurrentBase(b);
      setEnvBase(e);
      setInput(b === e ? "" : b);
    })();
  }, []);

  const normalize = (raw: string): string => {
    let v = (raw || "").trim();
    if (v && !v.startsWith("http")) v = "https://" + v;
    return v.replace(/\/+$/, "");
  };

  const testConnection = async (urlToTest?: string) => {
    const target = urlToTest != null ? normalize(urlToTest) : normalize(input);
    if (!target) {
      setTestResult({ ok: false, msg: "URL vide" });
      return;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const ctrl = new AbortController();
      const timeoutId = setTimeout(() => ctrl.abort(), 8000);
      const res = await fetch(`${target}/api/health`, { signal: ctrl.signal });
      clearTimeout(timeoutId);
      if (!res.ok) {
        setTestResult({ ok: false, msg: `HTTP ${res.status}: ${res.statusText}` });
        return;
      }
      const data = await res.json();
      setTestResult({
        ok: true,
        msg: `✅ Connecté · ${data.status || "OK"}${data.platform ? ` · ${data.platform}` : ""}`,
      });
    } catch (e: any) {
      const msg = e?.name === "AbortError" ? "Timeout (8s)" : (e?.message || "Échec de connexion");
      setTestResult({ ok: false, msg: `❌ ${msg}` });
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    const target = normalize(input);
    setSaving(true);
    setInfo(null);
    try {
      await setBaseUrl(target);
      const b = await getBaseUrl();
      setCurrentBase(b);
      setInfo(`URL backend sauvegardée : ${b || "(env par défaut)"}\n\nRecharge l'app (pull-to-refresh ou ferme/rouvre) pour appliquer.`);
    } finally {
      setSaving(false);
    }
  };

  const resetToEnv = async () => {
    setSaving(true);
    setInfo(null);
    try {
      await setBaseUrl("");
      setInput("");
      const b = await getBaseUrl();
      setCurrentBase(b);
      setInfo(`Réinitialisé à l'URL par défaut : ${b}`);
    } finally {
      setSaving(false);
    }
  };

  const isOverride = currentBase !== envBase;

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.headerRow}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} hitSlop={8}>
            <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={styles.overline}>CONFIGURATION</Text>
            <Text style={styles.title}>Réglages</Text>
          </View>
          <Ionicons name="settings-outline" size={24} color={colors.primary} />
        </View>

        <Card style={{ marginTop: spacing.md }}>
          <Text style={styles.cardTitle}>URL du backend (VPS)</Text>
          <Text style={styles.desc}>
            Par défaut, l&apos;app utilise le backend Emergent (Linux, sans MT5). Pour voir les vraies
            données de ton compte MT5, saisis ici l&apos;URL HTTPS de ton VPS Windows (Cloudflare Tunnel).
          </Text>

          <View style={styles.statusBox}>
            <Text style={styles.lbl}>URL active actuellement</Text>
            <Text style={styles.urlVal} numberOfLines={2}>{currentBase || "—"}</Text>
            {isOverride && (
              <View style={styles.overridePill}>
                <Text style={styles.overrideTxt}>⚙️ URL personnalisée (override)</Text>
              </View>
            )}
            {!isOverride && (
              <Text style={styles.envHint}>URL par défaut (Emergent sandbox)</Text>
            )}
          </View>

          <Text style={styles.lblTop}>Nouvelle URL du backend</Text>
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder="https://abc-xyz-12.trycloudflare.com"
            placeholderTextColor={colors.textMuted}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            style={styles.input}
            testID="settings-backend-url"
          />

          <View style={{ flexDirection: "row", gap: 8 }}>
            <View style={{ flex: 1 }}>
              <Button
                onPress={() => testConnection()}
                disabled={testing || !input}
                variant="outline"
                title={testing ? "Test…" : "🔍 Tester"}
                testID="settings-test-btn"
              />
            </View>
            <View style={{ flex: 1 }}>
              <Button
                onPress={save}
                disabled={saving || !input}
                title={saving ? "Save…" : "💾 Sauvegarder"}
                testID="settings-save-btn"
              />
            </View>
          </View>

          {testResult && (
            <View style={[styles.resultBox, { backgroundColor: testResult.ok ? colors.successBg : colors.dangerBg }]}>
              <Text style={[styles.resultTxt, { color: testResult.ok ? colors.success : colors.danger }]}>
                {testResult.msg}
              </Text>
            </View>
          )}

          {info && (
            <View style={styles.infoBox}>
              <Text style={styles.infoTxt}>{info}</Text>
            </View>
          )}

          {isOverride && (
            <TouchableOpacity onPress={resetToEnv} style={styles.resetBtn} disabled={saving}>
              <Text style={styles.resetTxt}>↩ Revenir à l&apos;URL par défaut</Text>
            </TouchableOpacity>
          )}
        </Card>

        <Card style={{ marginTop: spacing.md }}>
          <Text style={styles.cardTitle}>Comment trouver mon URL de tunnel ?</Text>
          <Text style={styles.desc}>Sur ton VPS Windows, ouvre PowerShell et lance :</Text>
          <View style={styles.codeBlock}>
            <Text style={styles.code}>cd C:\trading-bot{"\n"}.\scripts\vps_windows\get_tunnel_url.ps1</Text>
          </View>
          <Text style={styles.desc}>
            Ça affichera ton URL actuelle (ex: <Text style={styles.mono}>https://abc-def-123.trycloudflare.com</Text>).
            Copie-la et colle-la ci-dessus.
          </Text>
          <Text style={styles.descSmall}>
            💡 Cette URL change à chaque redémarrage de cloudflared. Pour une URL fixe permanente,
            il faut configurer un <Text style={{ fontWeight: "700" }}>Named Tunnel</Text> (Cloudflare account + domaine, ~2€/an).
          </Text>
        </Card>

        <Card style={{ marginTop: spacing.md, marginBottom: spacing.xl }}>
          <Text style={styles.cardTitle}>Conseils</Text>
          <Text style={styles.tip}>
            🟢 <Text style={styles.bold}>URL de TON VPS</Text> → données MT5 réelles (recommandé pour le trading)
          </Text>
          <Text style={styles.tip}>
            🟡 <Text style={styles.bold}>URL Emergent sandbox</Text> → simulateur uniquement, pas de MT5 (par défaut)
          </Text>
          <Text style={styles.tip}>
            ℹ️ Tu peux switcher entre les deux à tout moment, c&apos;est sauvegardé localement.
          </Text>
        </Card>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  scroll: { padding: spacing.md },
  headerRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  backBtn: { padding: 6, marginLeft: -6 },
  overline: { fontSize: 11, letterSpacing: 1.5, color: colors.textMuted, fontWeight: "700" },
  title: { fontSize: 26, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.6 },
  cardTitle: { fontSize: 14, fontWeight: "800", color: colors.textPrimary, marginBottom: spacing.sm, letterSpacing: -0.2 },
  desc: { fontSize: 13, color: colors.textSecondary, marginBottom: spacing.sm, lineHeight: 19 },
  descSmall: { fontSize: 11, color: colors.textMuted, marginTop: 6, lineHeight: 16 },
  lblTop: { fontSize: 11, color: colors.textMuted, fontWeight: "700", marginBottom: 4, marginTop: spacing.sm, letterSpacing: 0.6, textTransform: "uppercase" },
  lbl: { fontSize: 11, color: colors.textMuted, fontWeight: "700", marginBottom: 4 },
  statusBox: { backgroundColor: colors.surfaceAlt, borderRadius: radius.md, padding: spacing.sm, marginBottom: spacing.sm },
  urlVal: { fontSize: 13, color: colors.textPrimary, fontWeight: "700", fontFamily: "monospace" },
  overridePill: { alignSelf: "flex-start", backgroundColor: "#dbeafe", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, marginTop: 6 },
  overrideTxt: { fontSize: 10, color: "#1e40af", fontWeight: "800" },
  envHint: { fontSize: 11, color: colors.textMuted, marginTop: 4 },
  input: { backgroundColor: colors.surfaceAlt, borderRadius: radius.md, padding: 12, color: colors.textPrimary, marginBottom: spacing.sm, fontSize: 14, fontFamily: "monospace" },
  resultBox: { padding: spacing.sm, borderRadius: radius.md, marginTop: spacing.sm },
  resultTxt: { fontSize: 13, fontWeight: "700" },
  infoBox: { padding: spacing.sm, borderRadius: radius.md, marginTop: spacing.sm, backgroundColor: colors.successBg },
  infoTxt: { color: colors.success, fontSize: 12, lineHeight: 17 },
  resetBtn: { marginTop: spacing.sm, alignItems: "center" },
  resetTxt: { fontSize: 12, color: colors.primary, fontWeight: "700" },
  codeBlock: { backgroundColor: "#1e293b", padding: 12, borderRadius: radius.md, marginBottom: spacing.sm },
  code: { color: "#a5f3fc", fontFamily: "monospace", fontSize: 12, lineHeight: 18 },
  mono: { fontFamily: "monospace", fontSize: 12 },
  tip: { fontSize: 12, color: colors.textSecondary, marginBottom: 6, lineHeight: 18 },
  bold: { fontWeight: "800", color: colors.textPrimary },
});
