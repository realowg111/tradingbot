import React, { useEffect, useState, useCallback, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Switch,
  TextInput,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { Card, Button } from "@/src/components/ui";
import { colors, spacing, radius } from "@/src/theme";
import { apiGet, apiPost } from "@/src/api/client";

type Status = {
  configured: boolean;
  authorized: boolean;
  login_in_progress: boolean;
  connected: boolean;
  channels: string[];
  phone?: string;
  last_error?: string | null;
  config: {
    enabled: boolean;
    shadow_mode: boolean;
    channels: string[];
    symbols_whitelist: string[];
    split_legs: boolean;
    max_entry_drift_pct: number;
  };
};

type Signal = {
  id: string;
  ts: string;
  chat_title?: string;
  raw_text: string;
  parsed: {
    is_signal: boolean;
    symbol?: string;
    side?: string;
    entry?: number | null;
    sl?: number | null;
    tps?: { value: number | null; runner: boolean; raw: string }[];
    confidence?: number;
  };
  status: string;
  reject_reason?: string | null;
  executed?: boolean;
  resolved_symbol?: string;
  mt5_orders?: any[];
};

const statusBadge = (s: string) => {
  switch (s) {
    case "executed":
      return { bg: "#dcfce7", fg: "#166534", label: "Exécuté" };
    case "shadow":
      return { bg: "#dbeafe", fg: "#1e40af", label: "Shadow" };
    case "rejected":
      return { bg: "#fee2e2", fg: "#991b1b", label: "Rejeté" };
    case "failed":
      return { bg: "#fef3c7", fg: "#92400e", label: "Échec" };
    default:
      return { bg: "#f1f5f9", fg: "#475569", label: s };
  }
};

export default function TelegramScreen() {
  const router = useRouter();
  const [status, setStatus] = useState<Status | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState("");
  const [password2fa, setPassword2fa] = useState("");
  const [show2fa, setShow2fa] = useState(false);
  const [testText, setTestText] = useState("");
  const [testResult, setTestResult] = useState<any | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const pollRef = useRef<any>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [st, sigs] = await Promise.all([
        apiGet("/telegram/status"),
        apiGet("/telegram/signals?limit=80"),
      ]);
      setStatus(st as Status);
      setSignals(((sigs as any).items as Signal[]) || []);
    } catch (e: any) {
      setError(e.message || "Erreur");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    pollRef.current = setInterval(load, 8000);
    return () => clearInterval(pollRef.current);
  }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const startLogin = async () => {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const r = (await apiPost("/telegram/start-login", {})) as any;
      if (r.status === "already_authorized") {
        setInfo("Déjà connecté ✅");
      } else {
        setInfo("Code SMS envoyé. Vérifie ton Telegram / SMS.");
      }
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const submitCode = async () => {
    if (!code.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await apiPost("/telegram/submit-code", { code: code.trim() });
      setInfo("Authentifié ✅ — l'écoute démarre maintenant.");
      setCode("");
      setShow2fa(false);
      await load();
    } catch (e: any) {
      if (`${e.message}`.includes("2fa_password_required")) {
        setShow2fa(true);
        setInfo("Mot de passe 2FA requis.");
      } else {
        setError(e.message);
      }
    } finally {
      setBusy(false);
    }
  };

  const submitPassword2fa = async () => {
    setBusy(true);
    setError(null);
    try {
      await apiPost("/telegram/submit-password", { password: password2fa });
      setInfo("Authentifié ✅");
      setPassword2fa("");
      setShow2fa(false);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const toggleConfig = async (key: string, value: any) => {
    setBusy(true);
    setError(null);
    try {
      await apiPost("/telegram/config", { [key]: value });
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const runTestParse = async () => {
    if (!testText.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await apiPost("/telegram/test-parse", { text: testText });
      setTestResult(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const filtered = signals.filter((s) =>
    filter === "all" ? true : s.status === filter
  );

  if (loading) {
    return (
      <SafeAreaView style={styles.safe} edges={["top"]}>
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} />
        </View>
      </SafeAreaView>
    );
  }

  const authOk = !!status?.authorized;

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {/* Header */}
        <View style={styles.headerRow}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} hitSlop={8}>
            <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={styles.overline}>COPIE DE SIGNAUX</Text>
            <Text style={styles.title}>Telegram</Text>
          </View>
          <Ionicons name="paper-plane-outline" size={24} color={colors.primary} />
        </View>

        {error && (
          <View style={styles.errorBox}>
            <Ionicons name="alert-circle" size={18} color={colors.danger} />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}
        {info && (
          <View style={styles.infoBox}>
            <Ionicons name="information-circle" size={18} color={colors.primary} />
            <Text style={styles.infoText}>{info}</Text>
          </View>
        )}

        {/* Status */}
        <Card style={{ marginTop: spacing.md }}>
          <Text style={styles.cardTitle}>État de la connexion</Text>
          <View style={styles.row}>
            <Text style={styles.lbl}>Téléphone</Text>
            <Text style={styles.val}>{status?.phone || "—"}</Text>
          </View>
          <View style={styles.row}>
            <Text style={styles.lbl}>Canaux</Text>
            <Text style={styles.val}>{(status?.channels || []).join(", ") || "—"}</Text>
          </View>
          <View style={styles.row}>
            <Text style={styles.lbl}>Connecté à Telegram</Text>
            <View style={[styles.pill, status?.connected ? styles.pillOk : styles.pillKo]}>
              <Text style={[styles.pillTxt, { color: status?.connected ? "#166534" : "#991b1b" }]}>
                {status?.connected ? "Oui" : "Non"}
              </Text>
            </View>
          </View>
          <View style={styles.row}>
            <Text style={styles.lbl}>Authentifié</Text>
            <View style={[styles.pill, authOk ? styles.pillOk : styles.pillKo]}>
              <Text style={[styles.pillTxt, { color: authOk ? "#166534" : "#991b1b" }]}>
                {authOk ? "Oui" : "Non"}
              </Text>
            </View>
          </View>
          {status?.last_error && (
            <Text style={styles.errorTextSmall}>Dernière erreur: {status.last_error}</Text>
          )}
        </Card>

        {/* Login flow */}
        {!authOk && (
          <Card style={{ marginTop: spacing.md }}>
            <Text style={styles.cardTitle}>Authentification (1 fois)</Text>
            <Text style={styles.desc}>
              Telegram va envoyer un code à <Text style={{ fontWeight: "700" }}>{status?.phone}</Text>.
              Renseigne-le ci-dessous pour activer l&apos;écoute des canaux.
            </Text>

            {!status?.login_in_progress ? (
              <Button onPress={startLogin} disabled={busy} testID="tg-start-login" title={busy ? "Envoi…" : "1. Envoyer le code SMS"} />
            ) : (
              <>
                <Text style={styles.lblTop}>Code reçu</Text>
                <TextInput
                  value={code}
                  onChangeText={setCode}
                  placeholder="12345"
                  placeholderTextColor={colors.textMuted}
                  keyboardType="number-pad"
                  style={styles.input}
                  testID="tg-code"
                />
                <Button onPress={submitCode} disabled={busy || !code} testID="tg-submit-code" title={busy ? "Vérification…" : "2. Valider le code"} />
                <TouchableOpacity onPress={startLogin} style={{ marginTop: 8 }}>
                  <Text style={styles.linkBtn}>Renvoyer un nouveau code</Text>
                </TouchableOpacity>
              </>
            )}

            {show2fa && (
              <>
                <Text style={[styles.lblTop, { marginTop: spacing.md }]}>Mot de passe 2FA</Text>
                <TextInput
                  value={password2fa}
                  onChangeText={setPassword2fa}
                  placeholder="Mot de passe cloud Telegram"
                  placeholderTextColor={colors.textMuted}
                  secureTextEntry
                  style={styles.input}
                />
                <Button onPress={submitPassword2fa} disabled={busy || !password2fa} title={busy ? "Vérification…" : "Valider le 2FA"} />
              </>
            )}
          </Card>
        )}

        {/* Config */}
        <Card style={{ marginTop: spacing.md }}>
          <Text style={styles.cardTitle}>Configuration</Text>

          <View style={styles.toggleRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.lbl}>Copie active</Text>
              <Text style={styles.descSmall}>Désactive temporairement la copie sans déconnecter Telegram</Text>
            </View>
            <Switch
              value={!!status?.config?.enabled}
              onValueChange={(v) => toggleConfig("enabled", v)}
              disabled={busy}
            />
          </View>

          <View style={styles.toggleRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.lbl}>Mode Shadow (analyse seule)</Text>
              <Text style={styles.descSmall}>
                {status?.config?.shadow_mode
                  ? "⏸️ Les signaux sont parsés mais AUCUN ordre n'est envoyé sur MT5"
                  : "🚀 Les signaux sont exécutés en LIVE sur ton MT5"}
              </Text>
            </View>
            <Switch
              value={!!status?.config?.shadow_mode}
              onValueChange={(v) => toggleConfig("shadow_mode", v)}
              disabled={busy}
            />
          </View>

          <View style={styles.toggleRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.lbl}>Split 50/50 multi-TP</Text>
              <Text style={styles.descSmall}>50% lot ferme à TP1, 50% en runner (TP2 / OUVERT)</Text>
            </View>
            <Switch
              value={!!status?.config?.split_legs}
              onValueChange={(v) => toggleConfig("split_legs", v)}
              disabled={busy}
            />
          </View>

          <View style={styles.kv}>
            <Text style={styles.lbl}>Drift max d&apos;entrée</Text>
            <Text style={styles.valSmall}>{status?.config?.max_entry_drift_pct ?? 0.5}%</Text>
          </View>
        </Card>

        {/* Test parser */}
        <Card style={{ marginTop: spacing.md }}>
          <Text style={styles.cardTitle}>Tester le parseur IA</Text>
          <Text style={styles.desc}>Colle un signal pour voir comment Claude l&apos;extrait.</Text>
          <TextInput
            value={testText}
            onChangeText={setTestText}
            placeholder={"🚨 BUY XAUUSD\n📈 ENTRY : 4340-4337\n🔴 SL : 4333\n🟢 TP1: 4343\n🟢 TP2: OUVERT"}
            placeholderTextColor={colors.textMuted}
            multiline
            style={[styles.input, { minHeight: 110, textAlignVertical: "top" }]}
          />
          <Button onPress={runTestParse} disabled={busy || !testText}>
            {busy ? "Analyse…" : "Analyser"}
          </Button>
          {testResult && (
            <View style={styles.resultBox}>
              <Text style={styles.kvRow}>
                <Text style={styles.kk}>is_signal: </Text>
                <Text style={{ color: testResult.is_signal ? colors.success : colors.danger, fontWeight: "700" }}>
                  {String(testResult.is_signal)}
                </Text>
              </Text>
              <Text style={styles.kvRow}><Text style={styles.kk}>symbol: </Text>{testResult.symbol || "—"}</Text>
              <Text style={styles.kvRow}><Text style={styles.kk}>side: </Text>{testResult.side || "—"}</Text>
              <Text style={styles.kvRow}><Text style={styles.kk}>entry: </Text>{testResult.entry ?? "—"}</Text>
              <Text style={styles.kvRow}><Text style={styles.kk}>sl: </Text>{testResult.sl ?? "—"}</Text>
              <Text style={styles.kvRow}>
                <Text style={styles.kk}>TPs: </Text>
                {(testResult.tps || []).map((t: any, i: number) =>
                  `${i + 1}: ${t.runner ? "RUNNER" : t.value}`
                ).join("  ·  ") || "—"}
              </Text>
              <Text style={styles.kvRow}><Text style={styles.kk}>confidence: </Text>{(testResult.confidence * 100).toFixed(0)}%</Text>
            </View>
          )}
        </Card>

        {/* Signals feed */}
        <Card style={{ marginTop: spacing.md }}>
          <View style={{ flexDirection: "row", alignItems: "center", marginBottom: spacing.sm }}>
            <Text style={[styles.cardTitle, { flex: 1, marginBottom: 0 }]}>Flux des signaux</Text>
            <Text style={styles.count}>{filtered.length}/{signals.length}</Text>
          </View>

          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, marginBottom: spacing.sm }}>
            {["all", "executed", "shadow", "rejected", "failed"].map((k) => (
              <TouchableOpacity
                key={k}
                onPress={() => setFilter(k)}
                style={[styles.chip, filter === k && styles.chipActive]}
              >
                <Text style={[styles.chipTxt, filter === k && styles.chipTxtActive]}>
                  {k === "all" ? "Tous" : statusBadge(k).label}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          {filtered.length === 0 && (
            <View style={{ alignItems: "center", paddingVertical: spacing.lg }}>
              <Ionicons name="hourglass-outline" size={32} color={colors.textMuted} />
              <Text style={{ color: colors.textSecondary, marginTop: 8 }}>
                {authOk ? "En attente de signaux…" : "Authentifie Telegram pour démarrer l'écoute."}
              </Text>
            </View>
          )}

          {filtered.map((s) => {
            const sb = statusBadge(s.status);
            const p = s.parsed || ({} as any);
            const isShort = (p.side || "").toUpperCase() === "SELL";
            return (
              <View key={s.id} style={styles.signalCard}>
                <View style={styles.signalHead}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flex: 1 }}>
                    {p.side && (
                      <View style={[styles.sideBadge, { backgroundColor: isShort ? "#fee2e2" : "#dcfce7" }]}>
                        <Text style={{ color: isShort ? "#991b1b" : "#166534", fontWeight: "800", fontSize: 11 }}>
                          {p.side}
                        </Text>
                      </View>
                    )}
                    <Text style={styles.signalSym}>{p.symbol || "(non signal)"}</Text>
                    <Text style={styles.signalChat}>· {s.chat_title}</Text>
                  </View>
                  <View style={[styles.statusPill, { backgroundColor: sb.bg }]}>
                    <Text style={[styles.statusPillTxt, { color: sb.fg }]}>{sb.label}</Text>
                  </View>
                </View>

                {p.is_signal && (
                  <View style={styles.signalKvs}>
                    <Text style={styles.signalKv}>Entry: <Text style={styles.bold}>{p.entry ?? "—"}</Text></Text>
                    <Text style={styles.signalKv}>SL: <Text style={[styles.bold, { color: colors.danger }]}>{p.sl ?? "—"}</Text></Text>
                    {(p.tps || []).map((t, i) => (
                      <Text key={i} style={styles.signalKv}>
                        TP{i + 1}: <Text style={[styles.bold, { color: t.runner ? colors.primary : colors.success }]}>
                          {t.runner ? "RUNNER" : t.value}
                        </Text>
                      </Text>
                    ))}
                  </View>
                )}

                {s.reject_reason && (
                  <Text style={styles.reject}>❌ {s.reject_reason}</Text>
                )}

                {(s.mt5_orders || []).length > 0 && (
                  <View style={styles.ordersBox}>
                    {s.mt5_orders!.map((o: any, i: number) => (
                      <Text key={i} style={styles.orderLine}>
                        {o.leg} · {o.result?.ok ? `✅ #${o.result?.ticket}` : `❌ ${o.result?.error || "fail"}`}
                      </Text>
                    ))}
                  </View>
                )}

                <Text style={styles.signalTs}>
                  {new Date(s.ts).toLocaleString("fr-FR")}
                  {p.confidence != null && ` · conf ${(p.confidence * 100).toFixed(0)}%`}
                </Text>
              </View>
            );
          })}
        </Card>

        <View style={{ height: spacing.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  scroll: { padding: spacing.md },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  headerRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  backBtn: { padding: 6, marginLeft: -6 },
  overline: { fontSize: 11, letterSpacing: 1.5, color: colors.textMuted, fontWeight: "700" },
  title: { fontSize: 26, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.6 },
  cardTitle: { fontSize: 14, fontWeight: "800", color: colors.textPrimary, marginBottom: spacing.sm, letterSpacing: -0.2 },
  desc: { fontSize: 12, color: colors.textSecondary, marginBottom: spacing.sm, lineHeight: 17 },
  descSmall: { fontSize: 11, color: colors.textSecondary, marginTop: 2 },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 6 },
  lbl: { fontSize: 13, color: colors.textSecondary, fontWeight: "600" },
  lblTop: { fontSize: 11, color: colors.textMuted, fontWeight: "700", marginBottom: 4, letterSpacing: 0.6, textTransform: "uppercase" },
  val: { fontSize: 13, color: colors.textPrimary, fontWeight: "700" },
  valSmall: { fontSize: 12, color: colors.textPrimary, fontWeight: "700" },
  pill: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 12 },
  pillOk: { backgroundColor: "#dcfce7" },
  pillKo: { backgroundColor: "#fee2e2" },
  pillTxt: { fontSize: 11, fontWeight: "800" },
  errorBox: { flexDirection: "row", gap: 6, backgroundColor: colors.dangerBg, padding: spacing.sm, borderRadius: radius.md, marginTop: spacing.sm },
  errorText: { color: colors.danger, fontSize: 13, flex: 1 },
  errorTextSmall: { color: colors.danger, fontSize: 11, marginTop: 6 },
  infoBox: { flexDirection: "row", gap: 6, backgroundColor: colors.surfaceAlt, padding: spacing.sm, borderRadius: radius.md, marginTop: spacing.sm },
  infoText: { color: colors.primary, fontSize: 13, flex: 1 },
  input: { backgroundColor: colors.surfaceAlt, borderRadius: radius.md, padding: 12, color: colors.textPrimary, marginBottom: spacing.sm, fontSize: 14 },
  linkBtn: { color: colors.primary, fontSize: 12, fontWeight: "700", textAlign: "center" },
  toggleRow: { flexDirection: "row", alignItems: "center", paddingVertical: 8, gap: spacing.md, borderTopWidth: 1, borderTopColor: colors.border },
  kv: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 8, borderTopWidth: 1, borderTopColor: colors.border },
  resultBox: { backgroundColor: colors.surfaceAlt, borderRadius: radius.md, padding: spacing.sm, marginTop: spacing.sm, gap: 3 },
  kvRow: { fontSize: 12, color: colors.textPrimary },
  kk: { color: colors.textMuted, fontWeight: "700" },
  count: { fontSize: 12, color: colors.textMuted, fontWeight: "700" },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, backgroundColor: colors.surfaceAlt },
  chipActive: { backgroundColor: colors.primary },
  chipTxt: { fontSize: 11, fontWeight: "700", color: colors.textSecondary },
  chipTxtActive: { color: colors.white },
  signalCard: { padding: spacing.sm, borderRadius: radius.md, backgroundColor: colors.surfaceAlt, marginBottom: 8 },
  signalHead: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 6 },
  signalSym: { fontSize: 14, fontWeight: "800", color: colors.textPrimary },
  signalChat: { fontSize: 11, color: colors.textMuted, flex: 1 },
  sideBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  statusPill: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 },
  statusPillTxt: { fontSize: 10, fontWeight: "800" },
  signalKvs: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginBottom: 4 },
  signalKv: { fontSize: 12, color: colors.textSecondary },
  bold: { fontWeight: "800", color: colors.textPrimary },
  reject: { fontSize: 11, color: colors.danger, marginTop: 2 },
  ordersBox: { marginTop: 4, paddingTop: 4, borderTopWidth: 1, borderTopColor: colors.border, gap: 2 },
  orderLine: { fontSize: 11, color: colors.textSecondary },
  signalTs: { fontSize: 10, color: colors.textMuted, marginTop: 4 },
});
