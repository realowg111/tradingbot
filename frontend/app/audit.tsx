import React, { useEffect, useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Linking, Platform } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";

import { Card, Badge, SectionTitle, EmptyState, Overline } from "@/src/components/ui";
import { colors, spacing } from "@/src/theme";
import { apiGet, getToken } from "@/src/api/client";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";

type Log = { id: string; ts: string; level: string; event: string; details: any };

const LEVEL_COLORS: Record<string, "neutral" | "success" | "danger" | "warning" | "demo"> = {
  INFO: "neutral",
  SIGNAL: "demo",
  TRADE: "success",
  RISK: "warning",
  ERROR: "danger",
  SYSTEM: "demo",
};

export default function Audit() {
  const router = useRouter();
  const [logs, setLogs] = useState<Log[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const q = filter !== "all" ? `?level=${filter}` : "";
      const data = await apiGet<Log[]>(`/audit/logs${q}`);
      setLogs(data);
    } catch (e: any) { setError(e.message); }
  }, [filter]);

  useFocusEffect(useCallback(() => {
    let interval: any;
    refresh();
    interval = setInterval(refresh, 4000);
    return () => clearInterval(interval);
  }, [refresh]));

  const exportFile = async (format: "csv" | "json") => {
    const token = await getToken();
    const url = `${BASE}/api/audit/export?format=${format}`;
    if (Platform.OS === "web") {
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      const blob = await res.blob();
      const dl = URL.createObjectURL(blob);
      // @ts-ignore
      const a = document.createElement("a");
      a.href = dl;
      a.download = `audit.${format}`;
      a.click();
      URL.revokeObjectURL(dl);
    } else {
      await Linking.openURL(url);
    }
  };

  const LEVELS = ["all", "INFO", "SIGNAL", "TRADE", "RISK", "ERROR", "SYSTEM"];

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <View style={{ padding: spacing.md, paddingBottom: 0 }}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backRow} testID="audit-back">
          <Ionicons name="chevron-back" size={20} color={colors.textPrimary} />
          <Text style={{ color: colors.textPrimary, fontSize: 15 }}>Retour</Text>
        </TouchableOpacity>
        <Overline>Journal</Overline>
        <Text style={styles.title}>Logs d'audit</Text>
      </View>
      <View style={styles.filterBg}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterRow}>
          {LEVELS.map((l) => (
            <TouchableOpacity
              key={l}
              testID={`audit-filter-${l}`}
              onPress={() => setFilter(l)}
              style={[styles.chip, filter === l && styles.chipActive]}
            >
              <Text style={[styles.chipText, filter === l && styles.chipTextActive]}>{l === "all" ? "Tous" : l}</Text>
            </TouchableOpacity>
          ))}
          <TouchableOpacity onPress={() => exportFile("csv")} style={styles.exportChip} testID="audit-export-csv">
            <Ionicons name="download-outline" size={14} color={colors.primary} />
            <Text style={styles.exportText}>CSV</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => exportFile("json")} style={styles.exportChip} testID="audit-export-json">
            <Ionicons name="download-outline" size={14} color={colors.primary} />
            <Text style={styles.exportText}>JSON</Text>
          </TouchableOpacity>
        </ScrollView>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.md, paddingTop: spacing.sm }}>
        {error ? <Text style={{ color: colors.danger }}>{error}</Text> : null}
        {logs.length === 0 ? (
          <Card><EmptyState icon="document-text-outline" title="Aucun log" testID="empty-audit" /></Card>
        ) : (
          logs.map((l) => (
            <Card key={l.id} style={{ marginBottom: spacing.sm }} testID={`audit-log-${l.id}`}>
              <View style={styles.logHeader}>
                <Badge variant={LEVEL_COLORS[l.level] || "neutral"}>{l.level}</Badge>
                <Text style={styles.logEvent}>{l.event}</Text>
              </View>
              {l.details && Object.keys(l.details).length > 0 ? (
                <Text style={styles.logDetails}>{JSON.stringify(l.details)}</Text>
              ) : null}
              <Text style={styles.logTs}>{new Date(l.ts).toLocaleString("fr-FR")}</Text>
            </Card>
          ))
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  backRow: { flexDirection: "row", alignItems: "center", gap: 4, marginBottom: spacing.md },
  title: { fontSize: 28, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.8, marginTop: 4 },
  filterBg: { backgroundColor: colors.surface, paddingVertical: spacing.sm, borderBottomColor: colors.border, borderBottomWidth: 1 },
  filterRow: { flexDirection: "row", gap: 8, paddingHorizontal: spacing.md },
  chip: { paddingHorizontal: 12, height: 36, borderRadius: 18, borderColor: colors.borderStrong, borderWidth: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.white, flexShrink: 0 },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: 12, color: colors.textPrimary, fontWeight: "600" },
  chipTextActive: { color: colors.white },
  exportChip: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, height: 36, borderRadius: 18, borderColor: colors.primary, borderWidth: 1, backgroundColor: colors.white, flexShrink: 0 },
  exportText: { color: colors.primary, fontWeight: "700", fontSize: 12 },
  logHeader: { flexDirection: "row", alignItems: "center", gap: 8 },
  logEvent: { fontSize: 14, fontWeight: "700", color: colors.textPrimary },
  logDetails: { fontSize: 11, color: colors.textSecondary, marginTop: 6, fontFamily: "Courier" },
  logTs: { fontSize: 10, color: colors.textMuted, marginTop: 6 },
});
