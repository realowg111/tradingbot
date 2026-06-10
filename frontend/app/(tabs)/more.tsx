import React from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { Card, Overline } from "@/src/components/ui";
import { colors, spacing, radius } from "@/src/theme";
import { useAuth } from "@/src/context/AuthContext";

type Item = { id: string; icon: keyof typeof Ionicons.glyphMap; label: string; description: string; href: string; testId: string };

const items: Item[] = [
  { id: "journal", icon: "sparkles-outline", label: "Journal AI", description: "Analyse IA Claude 4.5 de l'historique de trades", href: "/journal", testId: "more-journal" },
  { id: "regime", icon: "pulse-outline", label: "Régime de marché", description: "Détection adaptative trend/range/volatile + ajustement auto", href: "/regime", testId: "more-regime" },
  { id: "risk", icon: "shield-checkmark-outline", label: "Gestion du risque", description: "SL, TP, drawdown, sizing, ratio R/R, validation, live MT5", href: "/risk", testId: "more-risk" },
  { id: "system", icon: "pulse-outline", label: "Santé du serveur", description: "CPU, RAM, disque, services, mise à jour auto", href: "/system", testId: "more-system" },
  { id: "costs", icon: "cash-outline", label: "Coûts infrastructure", description: "VPS, API, données, maintenance", href: "/costs", testId: "more-costs" },
  { id: "audit", icon: "document-text-outline", label: "Logs d'audit", description: "Toutes les décisions du bot", href: "/audit", testId: "more-audit" },
  { id: "mt5", icon: "lock-closed-outline", label: "Connexion MT5", description: "Identifiants chiffrés AES-256", href: "/mt5", testId: "more-mt5" },
  { id: "backtest", icon: "stats-chart-outline", label: "Backtesting", description: "Tester sur données historiques", href: "/backtest", testId: "more-backtest" },
];

export default function More() {
  const router = useRouter();
  const { user, logout } = useAuth();

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Overline>Console</Overline>
        <Text style={styles.title}>Paramètres & Modules</Text>

        <Card style={{ marginTop: spacing.md }}>
          <View style={styles.userRow}>
            <View style={styles.avatar}><Ionicons name="person" size={20} color={colors.white} /></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.userEmail}>{user?.email}</Text>
              <Text style={styles.userRole}>{user?.is_admin ? "Administrateur" : "Utilisateur"}</Text>
            </View>
            <TouchableOpacity onPress={logout} style={styles.logoutBtn} testID="logout-button">
              <Ionicons name="log-out-outline" size={18} color={colors.danger} />
              <Text style={{ color: colors.danger, fontSize: 12, fontWeight: "700" }}>Déconnexion</Text>
            </TouchableOpacity>
          </View>
        </Card>

        <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
          {items.map((it) => (
            <TouchableOpacity
              key={it.id}
              testID={it.testId}
              activeOpacity={0.85}
              onPress={() => router.push(it.href as any)}
            >
              <Card>
                <View style={styles.itemRow}>
                  <View style={styles.itemIcon}><Ionicons name={it.icon} size={20} color={colors.primary} /></View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.itemLabel}>{it.label}</Text>
                    <Text style={styles.itemDesc}>{it.description}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
                </View>
              </Card>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.footer}>Trading Bot v1.0.0 · Console Pro</Text>
        <View style={{ height: spacing.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  scroll: { padding: spacing.md },
  title: { fontSize: 28, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.8, marginTop: 4 },
  userRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.primary, alignItems: "center", justifyContent: "center" },
  userEmail: { fontSize: 14, fontWeight: "700", color: colors.textPrimary },
  userRole: { fontSize: 11, color: colors.textSecondary, marginTop: 2 },
  logoutBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 8, borderRadius: 6, backgroundColor: colors.dangerBg },
  itemRow: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  itemIcon: { width: 40, height: 40, borderRadius: radius.md, backgroundColor: colors.surfaceAlt, alignItems: "center", justifyContent: "center" },
  itemLabel: { fontSize: 14, fontWeight: "700", color: colors.textPrimary },
  itemDesc: { fontSize: 12, color: colors.textSecondary, marginTop: 2 },
  footer: { textAlign: "center", color: colors.textMuted, fontSize: 11, marginTop: spacing.xl, letterSpacing: 1 },
});
