import React, { useEffect, useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";

import { Card, Button, SectionTitle, Overline, Badge } from "@/src/components/ui";
import { colors, spacing, radius } from "@/src/theme";
import { apiGet, apiPost } from "@/src/api/client";
import { useToast } from "@/src/components/Toast";

type HealthData = {
  platform: { system: string; release: string; python: string; hostname: string };
  cpu: { percent: number; count: number; load_avg: number[] };
  memory: { total_mb: number; used_mb: number; available_mb: number; percent: number };
  disk: { total_gb: number; used_gb: number; free_gb: number; percent: number };
  network: { bytes_sent: number; bytes_recv: number };
  uptime: { system_seconds: number; backend_seconds: number };
  services: { mongodb: boolean; bot_loop: boolean; mt5_connected: boolean; mt5_mode: string; ws_clients: number };
};

export default function SystemHealth() {
  const router = useRouter();
  const toast = useToast();
  const [data, setData] = useState<HealthData | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const d = await apiGet<HealthData>("/system/health");
      setData(d);
      setError(null);
    } catch (e: any) { setError(e.message); }
  }, []);

  useFocusEffect(useCallback(() => {
    let interval: any;
    refresh();
    interval = setInterval(refresh, 4000);
    return () => clearInterval(interval);
  }, [refresh]));

  const onRefresh = async () => { setRefreshing(true); await refresh(); setRefreshing(false); };

  const triggerUpdate = async () => {
    setUpdating(true);
    try {
      const r = await apiPost<any>("/system/update");
      if (r.updated) {
        toast.show({ type: "success", title: "Mise à jour appliquée", message: `${r.before?.slice(0, 7)} → ${r.after?.slice(0, 7)}` });
      } else {
        toast.show({ type: "info", title: "Aucune mise à jour", message: r.message || "Déjà à jour" });
      }
    } catch (e: any) {
      toast.show({ type: "danger", title: "Erreur update", message: e.message });
    } finally { setUpdating(false); }
  };

  const fmtUptime = (sec: number) => {
    const d = Math.floor(sec / 86400);
    const h = Math.floor((sec % 86400) / 3600);
    const m = Math.floor((sec % 3600) / 60);
    if (d > 0) return `${d}j ${h}h ${m}m`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  };

  const fmtBytes = (b: number) => {
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)} MB`;
    return `${(b / 1024 / 1024 / 1024).toFixed(2)} GB`;
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      >
        <TouchableOpacity onPress={() => router.back()} style={styles.backRow} testID="system-back">
          <Ionicons name="chevron-back" size={20} color={colors.textPrimary} />
          <Text style={{ color: colors.textPrimary, fontSize: 15 }}>Retour</Text>
        </TouchableOpacity>
        <Overline>Infrastructure</Overline>
        <Text style={styles.title}>Santé du serveur</Text>
        <Text style={styles.subtitle}>Métriques temps réel du VPS</Text>

        {error ? <View style={styles.errBox}><Text style={{ color: colors.danger, fontSize: 13 }}>{error}</Text></View> : null}

        {/* Services status */}
        {data ? (
          <>
            <SectionTitle>Services</SectionTitle>
            <Card>
              <ServiceRow label="Backend FastAPI" ok={true} subtitle={`Uptime ${fmtUptime(data.uptime.backend_seconds)}`} testID="svc-backend" />
              <ServiceRow label="MongoDB" ok={data.services.mongodb} testID="svc-mongo" />
              <ServiceRow label="Boucle de trading" ok={data.services.bot_loop} testID="svc-bot" />
              <ServiceRow label="MetaTrader 5" ok={data.services.mt5_connected} subtitle={data.services.mt5_connected ? `Mode ${data.services.mt5_mode}` : "Simulateur actif"} testID="svc-mt5" />
              <ServiceRow label="WebSocket" ok={data.services.ws_clients > 0} subtitle={`${data.services.ws_clients} client(s) connecté(s)`} testID="svc-ws" last />
            </Card>

            <SectionTitle>Ressources</SectionTitle>
            <Card>
              <Gauge label="CPU" percent={data.cpu.percent} subtitle={`${data.cpu.count} vCPU · Load ${data.cpu.load_avg.map(x => x.toFixed(2)).join(" / ")}`} testID="gauge-cpu" />
              <View style={styles.divider} />
              <Gauge label="Mémoire" percent={data.memory.percent} subtitle={`${(data.memory.used_mb / 1024).toFixed(2)} GB / ${(data.memory.total_mb / 1024).toFixed(1)} GB`} testID="gauge-mem" />
              <View style={styles.divider} />
              <Gauge label="Disque" percent={data.disk.percent} subtitle={`${data.disk.used_gb} GB / ${data.disk.total_gb} GB · Libre ${data.disk.free_gb} GB`} testID="gauge-disk" />
            </Card>

            <SectionTitle>Système</SectionTitle>
            <Card>
              <InfoRow label="OS" value={`${data.platform.system} ${data.platform.release}`} />
              <InfoRow label="Hostname" value={data.platform.hostname} />
              <InfoRow label="Python" value={data.platform.python} />
              <InfoRow label="Uptime VPS" value={fmtUptime(data.uptime.system_seconds)} />
              <InfoRow label="Network ↑" value={fmtBytes(data.network.bytes_sent)} />
              <InfoRow label="Network ↓" value={fmtBytes(data.network.bytes_recv)} last />
            </Card>

            <SectionTitle>Mise à jour automatique</SectionTitle>
            <Card>
              <Text style={styles.updateDesc}>
                Si le backend est déployé via Git (sur ton VPS), tu peux lancer une mise à jour ici. Le serveur tirera la dernière version du code et redémarrera automatiquement.
              </Text>
              <Button title="Vérifier & mettre à jour" onPress={triggerUpdate} loading={updating} icon="cloud-download-outline" testID="update-button" />
              <Text style={styles.updateHint}>
                💡 Pour activer l'update automatique quotidien sur Windows VPS, voir le fichier <Text style={{ fontFamily: "Courier" }}>scripts/vps_windows/auto_update.ps1</Text>
              </Text>
            </Card>
          </>
        ) : null}

        <View style={{ height: spacing.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function ServiceRow({ label, ok, subtitle, testID, last }: { label: string; ok: boolean; subtitle?: string; testID?: string; last?: boolean }) {
  return (
    <View style={[styles.svcRow, last && { borderBottomWidth: 0 }]} testID={testID}>
      <View style={[styles.svcDot, { backgroundColor: ok ? colors.success : colors.danger }]} />
      <View style={{ flex: 1 }}>
        <Text style={styles.svcLabel}>{label}</Text>
        {subtitle ? <Text style={styles.svcSubtitle}>{subtitle}</Text> : null}
      </View>
      <Badge variant={ok ? "success" : "danger"}>{ok ? "OK" : "DOWN"}</Badge>
    </View>
  );
}

function Gauge({ label, percent, subtitle, testID }: { label: string; percent: number; subtitle?: string; testID?: string }) {
  const color = percent < 60 ? colors.success : percent < 85 ? colors.warning : colors.danger;
  return (
    <View testID={testID}>
      <View style={styles.gaugeHeader}>
        <Text style={styles.gaugeLabel}>{label}</Text>
        <Text style={[styles.gaugePercent, { color }]}>{percent.toFixed(0)}%</Text>
      </View>
      <View style={styles.gaugeBar}>
        <View style={[styles.gaugeFill, { width: `${Math.min(100, percent)}%`, backgroundColor: color }]} />
      </View>
      {subtitle ? <Text style={styles.gaugeSubtitle}>{subtitle}</Text> : null}
    </View>
  );
}

function InfoRow({ label, value, last }: { label: string; value: string; last?: boolean }) {
  return (
    <View style={[styles.infoRow, last && { borderBottomWidth: 0 }]}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  scroll: { padding: spacing.md },
  backRow: { flexDirection: "row", alignItems: "center", gap: 4, marginBottom: spacing.md },
  title: { fontSize: 28, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.8, marginTop: 4 },
  subtitle: { fontSize: 13, color: colors.textSecondary, marginTop: 4 },
  errBox: { backgroundColor: colors.dangerBg, padding: 10, borderRadius: 8, marginTop: spacing.md },

  svcRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 12, borderBottomColor: colors.border, borderBottomWidth: 1 },
  svcDot: { width: 10, height: 10, borderRadius: 5 },
  svcLabel: { fontSize: 14, fontWeight: "700", color: colors.textPrimary },
  svcSubtitle: { fontSize: 11, color: colors.textMuted, marginTop: 2 },

  divider: { height: 1, backgroundColor: colors.border, marginVertical: spacing.md },
  gaugeHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" },
  gaugeLabel: { fontSize: 13, color: colors.textPrimary, fontWeight: "700" },
  gaugePercent: { fontSize: 18, fontWeight: "800", letterSpacing: -0.3 },
  gaugeBar: { height: 6, backgroundColor: colors.surfaceAlt, borderRadius: 3, marginTop: 6, overflow: "hidden" },
  gaugeFill: { height: "100%", borderRadius: 3 },
  gaugeSubtitle: { fontSize: 11, color: colors.textMuted, marginTop: 4 },

  infoRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 8, borderBottomColor: colors.border, borderBottomWidth: 1 },
  infoLabel: { fontSize: 12, color: colors.textSecondary, fontWeight: "600" },
  infoValue: { fontSize: 13, color: colors.textPrimary, fontFamily: "Courier" },

  updateDesc: { fontSize: 13, color: colors.textSecondary, marginBottom: spacing.md, lineHeight: 18 },
  updateHint: { fontSize: 11, color: colors.textMuted, marginTop: spacing.sm, lineHeight: 16 },
});
