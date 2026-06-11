import React, { useEffect, useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl, ActivityIndicator } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { Card } from "@/src/components/ui";
import { colors, spacing } from "@/src/theme";
import { apiGet } from "@/src/api/client";

function scoreColor(score: number, threshold: number) {
  if (score >= threshold) return colors.success;
  if (score >= threshold - 15) return "#F59E0B";
  return colors.danger;
}

function DecisionBadge({ decision }: { decision: string }) {
  const map: Record<string, { label: string; bg: string; fg: string }> = {
    EXECUTE: { label: "EXÉCUTÉ", bg: "rgba(16,185,129,0.15)", fg: colors.success },
    REJECT: { label: "REJETÉ", bg: "rgba(239,68,68,0.12)", fg: colors.danger },
    NO_SIGNAL: { label: "PAS DE SIGNAL", bg: colors.surfaceAlt, fg: colors.textSecondary },
  };
  const s = map[decision] || map.NO_SIGNAL;
  return (
    <View style={[styles.decisionBadge, { backgroundColor: s.bg }]}>
      <Text style={[styles.decisionText, { color: s.fg }]}>{s.label}</Text>
    </View>
  );
}

function EvalCard({ ev }: { ev: any }) {
  const [expanded, setExpanded] = useState(false);
  const color = scoreColor(ev.score, ev.threshold);
  return (
    <TouchableOpacity onPress={() => setExpanded(!expanded)} activeOpacity={0.8} testID={`signal-card-${ev.symbol}`}>
      <Card style={{ marginBottom: spacing.md }}>
        <View style={styles.evalHeader}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Text style={styles.evalSymbol}>{ev.symbol}</Text>
            {ev.side ? (
              <Text style={[styles.evalSide, { color: ev.side === "BUY" ? colors.success : colors.danger }]}>
                {ev.side === "BUY" ? "↑ ACHAT" : "↓ VENTE"}
              </Text>
            ) : null}
          </View>
          <DecisionBadge decision={ev.decision} />
        </View>

        <View style={styles.scoreRow}>
          <View style={styles.scoreBarBg}>
            <View style={[styles.scoreBarFill, { width: `${Math.min(ev.score, 100)}%`, backgroundColor: color }]} />
            <View style={[styles.thresholdMark, { left: `${ev.threshold}%` }]} />
          </View>
          <Text style={[styles.scoreText, { color }]} testID={`signal-score-${ev.symbol}`}>{ev.score}</Text>
        </View>
        <Text style={styles.summary}>{ev.summary || "—"}</Text>

        {expanded ? (
          <View style={{ marginTop: spacing.sm }}>
            {(ev.factors || []).map((f: any, i: number) => (
              <View key={i} style={styles.factorRow}>
                <Ionicons
                  name={f.ok ? "checkmark-circle" : "remove-circle-outline"}
                  size={15}
                  color={f.ok ? colors.success : colors.textMuted}
                  style={{ marginTop: 1 }}
                />
                <View style={{ flex: 1 }}>
                  <Text style={styles.factorName}>{f.name} · {f.points}/{f.max} pts</Text>
                  <Text style={styles.factorDetail}>{f.detail}</Text>
                </View>
              </View>
            ))}
          </View>
        ) : (
          <Text style={styles.expandHint}>Toucher pour voir le détail des {(ev.factors || []).length} facteurs</Text>
        )}
      </Card>
    </TouchableOpacity>
  );
}

export default function SignalsScreen() {
  const router = useRouter();
  const [current, setCurrent] = useState<any>(null);
  const [recent, setRecent] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [cur, rec] = await Promise.all([
        apiGet("/signals/current"),
        apiGet("/signals/recent?limit=20"),
      ]);
      setCurrent(cur);
      setRecent(rec as any[]);
      setError(null);
    } catch (e: any) { setError(e.message); }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} testID="signals-back-button">
          <Ionicons name="chevron-back" size={24} color={colors.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Signaux & Scores</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 100 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        <Text style={styles.intro}>
          {"Chaque marché est noté sur 100 via 6 familles de facteurs (tendance, momentum, structure, volatilité, spread, régime). Le bot n'ouvre une position que si le score atteint le seuil"}
          {current ? ` (${current.min_confidence_score})` : ""}.
        </Text>

        <Text style={styles.sectionTitle}>ANALYSE EN DIRECT</Text>
        {!current ? (
          <ActivityIndicator color={colors.primary} style={{ marginVertical: 30 }} />
        ) : current.evaluations.length === 0 ? (
          <Card><Text style={styles.empty}>{"Aucune évaluation pour le moment. Activez le bot pour lancer l'analyse (1 évaluation/minute par marché)."}</Text></Card>
        ) : (
          current.evaluations.map((ev: any) => <EvalCard key={ev.symbol} ev={ev} />)
        )}

        <Text style={styles.sectionTitle}>HISTORIQUE DES SIGNAUX</Text>
        {recent.length === 0 ? (
          <Card><Text style={styles.empty}>Aucun signal enregistré (les exécutions et presque-signaux apparaîtront ici).</Text></Card>
        ) : (
          recent.map((ev: any) => <EvalCard key={ev.id} ev={ev} />)
        )}
        {error ? <Text style={{ color: colors.danger, fontSize: 12 }}>{error}</Text> : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  headerTitle: { fontSize: 17, fontWeight: "800", color: colors.textPrimary },
  intro: { fontSize: 12, color: colors.textSecondary, lineHeight: 18, marginBottom: spacing.lg },
  sectionTitle: { fontSize: 11, fontWeight: "800", color: colors.textMuted, letterSpacing: 1.2, marginBottom: spacing.sm, marginTop: spacing.md },
  evalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  evalSymbol: { fontSize: 16, fontWeight: "800", color: colors.textPrimary },
  evalSide: { fontSize: 12, fontWeight: "800" },
  decisionBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 100 },
  decisionText: { fontSize: 10, fontWeight: "800", letterSpacing: 0.5 },
  scoreRow: { flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 6 },
  scoreBarBg: { flex: 1, height: 8, backgroundColor: colors.surfaceAlt, borderRadius: 100, overflow: "hidden", position: "relative" },
  scoreBarFill: { height: 8, borderRadius: 100 },
  thresholdMark: { position: "absolute", top: -2, width: 2, height: 12, backgroundColor: colors.textPrimary, opacity: 0.5 },
  scoreText: { fontSize: 16, fontWeight: "900", width: 34, textAlign: "right" },
  summary: { fontSize: 12, color: colors.textSecondary, lineHeight: 17 },
  expandHint: { fontSize: 10, color: colors.textMuted, marginTop: 8, fontStyle: "italic" },
  factorRow: { flexDirection: "row", gap: 8, marginTop: 8 },
  factorName: { fontSize: 12, fontWeight: "700", color: colors.textPrimary },
  factorDetail: { fontSize: 11, color: colors.textSecondary, lineHeight: 16, marginTop: 1 },
  empty: { fontSize: 12, color: colors.textMuted, lineHeight: 18 },
});
