import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Platform,
  Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { Stack, useRouter } from "expo-router";

import { Card, Badge, Overline, Button, EmptyState } from "@/src/components/ui";
import { colors, spacing, radius, fmt } from "@/src/theme";
import { apiGet, getToken } from "@/src/api/client";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";

type ModeFilter = "all" | "demo" | "real";
type Period = 7 | 30 | 90;

type Stats = {
  total_trades: number;
  wins: number;
  losses: number;
  winrate: number;
  total_pnl: number;
  avg_pnl: number;
  best_trade: number;
  worst_trade: number;
  profit_factor: number;
  expectancy: number;
  avg_duration_min: number;
  by_symbol: Record<string, { n: number; wins: number; winrate: number; pnl: number }>;
  by_strategy: Record<string, { n: number; wins: number; winrate: number; pnl: number; profit_factor: number }>;
  by_side: { BUY: number; SELL: number };
  by_close_reason: Record<string, number>;
};

type Report = {
  id: string;
  created_at: string;
  period_days: number;
  mode: string | null;
  stats: Stats;
  report_md: string;
  model: string;
};

export default function JournalScreen() {
  const router = useRouter();
  const [period, setPeriod] = useState<Period>(30);
  const [modeFilter, setModeFilter] = useState<ModeFilter>("all");
  const [preview, setPreview] = useState<Stats | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [report, setReport] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Report[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<ScrollView>(null);

  const loadPreview = useCallback(async () => {
    setLoadingPreview(true);
    try {
      const q = modeFilter === "all" ? "" : `&mode=${modeFilter}`;
      const res = await apiGet<{ stats: Stats }>(`/journal/preview?days=${period}${q}`);
      setPreview(res.stats);
    } catch (e: any) {
      setError(e?.message || "Erreur de chargement");
    } finally {
      setLoadingPreview(false);
    }
  }, [period, modeFilter]);

  const loadHistory = useCallback(async () => {
    try {
      const list = await apiGet<Report[]>(`/journal/reports?limit=20`);
      setHistory(list || []);
    } catch {}
  }, []);

  useEffect(() => {
    loadPreview();
  }, [loadPreview]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const handleAnalyze = async () => {
    if (streaming) return;
    setError(null);
    setReport("");
    setStreaming(true);
    abortRef.current?.abort();
    abortRef.current = new AbortController();

    try {
      const token = await getToken();
      const res = await fetch(`${BASE}/api/journal/analyze`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          days: period,
          mode: modeFilter === "all" ? null : modeFilter,
        }),
        signal: abortRef.current.signal,
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      // SSE parsing : try ReadableStream first, fallback to .text()
      const reader = (res.body as any)?.getReader?.();
      if (reader) {
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          for (const line of lines) {
            if (!line.startsWith("data:")) continue;
            const data = line.slice(5).trim();
            if (!data) continue;
            try {
              const obj = JSON.parse(data);
              if (obj.delta) {
                setReport((prev) => prev + obj.delta);
                // auto-scroll
                requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: false }));
              } else if (obj.error) {
                setError(obj.error);
              } else if (obj.done) {
                // end
              }
            } catch {}
          }
        }
      } else {
        // Fallback: parse entire body at once (no streaming on this env)
        const text = await res.text();
        for (const raw of text.split("\n")) {
          if (!raw.startsWith("data:")) continue;
          const data = raw.slice(5).trim();
          if (!data) continue;
          try {
            const obj = JSON.parse(data);
            if (obj.delta) setReport((prev) => prev + obj.delta);
            if (obj.error) setError(obj.error);
          } catch {}
        }
      }
      // Reload history once done
      loadHistory();
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        setError(e?.message || "Erreur d'analyse");
      }
    } finally {
      setStreaming(false);
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const loadReport = async (r: Report) => {
    setReport(r.report_md);
    setPreview(r.stats);
    setPeriod((r.period_days as Period) || 30);
    setModeFilter((r.mode as ModeFilter) || "all");
    scrollRef.current?.scrollTo({ y: 0, animated: true });
  };

  const periods: { v: Period; l: string }[] = [
    { v: 7, l: "7j" },
    { v: 30, l: "30j" },
    { v: 90, l: "90j" },
  ];
  const modes: { v: ModeFilter; l: string }[] = [
    { v: "all", l: "Tous" },
    { v: "demo", l: "Démo" },
    { v: "real", l: "Réel" },
  ];

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={10} testID="journal-back">
          <Ionicons name="chevron-back" size={26} color={colors.textPrimary} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Overline>Intelligence</Overline>
          <Text style={styles.title}>Journal AI</Text>
        </View>
        <View style={styles.aiPill}>
          <Ionicons name="sparkles" size={12} color={colors.primary} />
          <Text style={styles.aiPillText}>Claude 4.5</Text>
        </View>
      </View>

      <ScrollView ref={scrollRef} contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        {/* Filters */}
        <Card>
          <Text style={styles.cardTitle}>{"Période d'analyse"}</Text>
          <View style={styles.toggleRow}>
            {periods.map((p) => (
              <TouchableOpacity
                key={p.v}
                onPress={() => setPeriod(p.v)}
                style={[styles.toggleBtn, period === p.v && styles.toggleBtnActive]}
                testID={`period-${p.v}`}
              >
                <Text style={[styles.toggleText, period === p.v && styles.toggleTextActive]}>{p.l}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={[styles.cardTitle, { marginTop: spacing.md }]}>Mode</Text>
          <View style={styles.toggleRow}>
            {modes.map((m) => (
              <TouchableOpacity
                key={m.v}
                onPress={() => setModeFilter(m.v)}
                style={[styles.toggleBtn, modeFilter === m.v && styles.toggleBtnActive]}
                testID={`mode-${m.v}`}
              >
                <Text style={[styles.toggleText, modeFilter === m.v && styles.toggleTextActive]}>{m.l}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </Card>

        {/* Stats preview */}
        <Card style={{ marginTop: spacing.md }}>
          <Text style={styles.cardTitle}>Aperçu de la période</Text>
          {loadingPreview ? (
            <View style={{ paddingVertical: spacing.lg, alignItems: "center" }}>
              <ActivityIndicator color={colors.primary} />
            </View>
          ) : preview ? (
            <View style={styles.statsGrid}>
              <StatTile label="Trades" value={String(preview.total_trades)} />
              <StatTile
                label="Winrate"
                value={`${preview.winrate.toFixed(1)}%`}
                color={preview.winrate >= 50 ? colors.success : colors.danger}
              />
              <StatTile
                label="PnL Total"
                value={fmt.money(preview.total_pnl)}
                color={preview.total_pnl >= 0 ? colors.success : colors.danger}
              />
              <StatTile
                label="Profit Factor"
                value={preview.profit_factor.toFixed(2)}
                color={preview.profit_factor >= 1 ? colors.success : colors.danger}
              />
              <StatTile label="Best" value={fmt.money(preview.best_trade)} color={colors.success} />
              <StatTile label="Worst" value={fmt.money(preview.worst_trade)} color={colors.danger} />
            </View>
          ) : (
            <EmptyState title="Aucune donnée" subtitle="Lance le bot pour générer de l'historique" />
          )}
        </Card>

        {/* Generate button */}
        <View style={{ marginTop: spacing.md }}>
          {streaming ? (
            <Button title="Arrêter" onPress={handleStop} variant="danger" icon="stop-circle-outline" testID="journal-stop" />
          ) : (
            <Button
              title={report ? "Re-générer l'analyse IA" : "Générer l'analyse IA"}
              onPress={handleAnalyze}
              variant="primary"
              icon="sparkles"
              testID="journal-generate"
              disabled={!preview || preview.total_trades === 0}
            />
          )}
        </View>

        {error ? (
          <Card style={{ marginTop: spacing.md, backgroundColor: colors.dangerBg, borderColor: colors.danger, borderWidth: 1 }}>
            <Text style={{ color: colors.danger, fontWeight: "700" }}>{error}</Text>
          </Card>
        ) : null}

        {/* Report */}
        {report || streaming ? (
          <Card style={{ marginTop: spacing.md }}>
            <View style={styles.reportHeader}>
              <View style={styles.reportHeaderLeft}>
                <Ionicons name="document-text-outline" size={18} color={colors.primary} />
                <Text style={styles.cardTitle}>{"Rapport d'analyse"}</Text>
                {streaming ? <ActivityIndicator size="small" color={colors.primary} /> : null}
              </View>
              <Badge variant="neutral">Markdown</Badge>
            </View>
            <View style={styles.reportBody}>
              <MarkdownLite text={report || "…"} />
            </View>
          </Card>
        ) : null}

        {/* History */}
        <Card style={{ marginTop: spacing.md }}>
          <View style={styles.historyHeader}>
            <Text style={styles.cardTitle}>Rapports précédents</Text>
            <TouchableOpacity onPress={loadHistory} hitSlop={10}>
              <Ionicons name="refresh" size={18} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>
          {history.length === 0 ? (
            <Text style={styles.muted}>Aucun rapport sauvegardé.</Text>
          ) : (
            history.map((r) => (
              <TouchableOpacity
                key={r.id}
                onPress={() => loadReport(r)}
                style={styles.historyRow}
                testID={`history-${r.id}`}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.historyDate}>
                    {new Date(r.created_at).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" })}
                  </Text>
                  <Text style={styles.historyMeta}>
                    {r.period_days}j · {r.mode || "tous"} · {r.stats.total_trades} trades · {fmt.money(r.stats.total_pnl)}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
              </TouchableOpacity>
            ))
          )}
        </Card>

        <View style={{ height: spacing.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function StatTile({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.statTile}>
      <Text style={styles.statTileLabel}>{label}</Text>
      <Text style={[styles.statTileValue, color ? { color } : null]}>{value}</Text>
    </View>
  );
}

// Minimal Markdown renderer (headings, bold, lists, code)
function MarkdownLite({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <View>
      {lines.map((line, idx) => {
        if (line.startsWith("# ")) return <Text key={idx} style={styles.mdH1}>{line.slice(2)}</Text>;
        if (line.startsWith("## ")) return <Text key={idx} style={styles.mdH2}>{line.slice(3)}</Text>;
        if (line.startsWith("### ")) return <Text key={idx} style={styles.mdH3}>{line.slice(4)}</Text>;
        if (line.startsWith("- ") || line.startsWith("* ")) {
          return (
            <View key={idx} style={styles.mdListItem}>
              <Text style={styles.mdBullet}>•</Text>
              <Text style={styles.mdText}>{renderInline(line.slice(2))}</Text>
            </View>
          );
        }
        if (/^\d+\.\s/.test(line)) {
          const m = line.match(/^(\d+)\.\s(.*)$/);
          return (
            <View key={idx} style={styles.mdListItem}>
              <Text style={styles.mdNumber}>{m?.[1]}.</Text>
              <Text style={styles.mdText}>{renderInline(m?.[2] || "")}</Text>
            </View>
          );
        }
        if (line.startsWith("> ")) {
          return <Text key={idx} style={styles.mdQuote}>{line.slice(2)}</Text>;
        }
        if (line.trim() === "") return <View key={idx} style={{ height: 8 }} />;
        return <Text key={idx} style={styles.mdText}>{renderInline(line)}</Text>;
      })}
    </View>
  );
}

function renderInline(text: string): React.ReactNode {
  // Split by **bold** and `code`
  const parts: React.ReactNode[] = [];
  const regex = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > lastIdx) parts.push(text.slice(lastIdx, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) {
      parts.push(<Text key={`b${key++}`} style={{ fontWeight: "700" }}>{tok.slice(2, -2)}</Text>);
    } else if (tok.startsWith("`")) {
      parts.push(<Text key={`c${key++}`} style={{ fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace", backgroundColor: colors.surfaceAlt, color: colors.textPrimary }}>{tok.slice(1, -1)}</Text>);
    }
    lastIdx = m.index + tok.length;
  }
  if (lastIdx < text.length) parts.push(text.slice(lastIdx));
  return parts;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.white,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
  },
  title: { fontSize: 22, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.5 },
  aiPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
    backgroundColor: "#EEF2FF",
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: "#C7D2FE",
  },
  aiPillText: { fontSize: 11, fontWeight: "700", color: colors.primary },
  scroll: { padding: spacing.md },
  cardTitle: { fontSize: 14, fontWeight: "700", color: colors.textPrimary, marginBottom: spacing.sm },
  toggleRow: { flexDirection: "row", gap: 6 },
  toggleBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceAlt,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.border,
  },
  toggleBtnActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  toggleText: { fontSize: 13, fontWeight: "600", color: colors.textSecondary },
  toggleTextActive: { color: colors.white },
  statsGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  statTile: {
    flexBasis: "31%",
    flexGrow: 1,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    padding: spacing.sm,
  },
  statTileLabel: { fontSize: 11, color: colors.textSecondary, marginBottom: 2 },
  statTileValue: { fontSize: 15, fontWeight: "800", color: colors.textPrimary },
  reportHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  reportHeaderLeft: { flexDirection: "row", alignItems: "center", gap: 8 },
  reportBody: { paddingVertical: 4 },
  mdH1: { fontSize: 22, fontWeight: "800", color: colors.textPrimary, marginTop: 12, marginBottom: 6, letterSpacing: -0.5 },
  mdH2: { fontSize: 17, fontWeight: "800", color: colors.textPrimary, marginTop: 14, marginBottom: 4 },
  mdH3: { fontSize: 14, fontWeight: "700", color: colors.textPrimary, marginTop: 10, marginBottom: 4 },
  mdText: { fontSize: 14, color: colors.textPrimary, lineHeight: 21, flex: 1 },
  mdListItem: { flexDirection: "row", gap: 8, marginVertical: 2, paddingLeft: 4 },
  mdBullet: { fontSize: 14, color: colors.primary, lineHeight: 21 },
  mdNumber: { fontSize: 14, fontWeight: "700", color: colors.primary, lineHeight: 21, minWidth: 22 },
  mdQuote: { fontSize: 13, color: colors.textSecondary, fontStyle: "italic", borderLeftWidth: 3, borderLeftColor: colors.border, paddingLeft: 10, marginVertical: 4 },
  historyHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm },
  historyRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: spacing.sm,
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
  },
  historyDate: { fontSize: 13, fontWeight: "700", color: colors.textPrimary },
  historyMeta: { fontSize: 11, color: colors.textSecondary, marginTop: 2 },
  muted: { color: colors.textMuted, fontSize: 13 },
});
