import React, { useEffect, useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { Card, Button, Input, SectionTitle, Overline, Badge, EmptyState, Stat } from "@/src/components/ui";
import { colors, spacing, fmt } from "@/src/theme";
import { apiGet, apiPost, apiDelete } from "@/src/api/client";

type Cost = { id: string; category: string; label: string; amount: number; currency: string; recurring: string; date: string; notes?: string };

const CATEGORIES = ["vps", "api", "data", "maintenance", "other"] as const;

export default function Costs() {
  const router = useRouter();
  const [items, setItems] = useState<Cost[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("EUR");
  const [category, setCategory] = useState<typeof CATEGORIES[number]>("vps");
  const [recurring, setRecurring] = useState<"once" | "monthly" | "yearly">("monthly");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [list, s] = await Promise.all([apiGet<Cost[]>("/costs"), apiGet("/costs/summary")]);
      setItems(list);
      setSummary(s);
    } catch (e: any) { setError(e.message); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const add = async () => {
    setError(null);
    const amt = parseFloat(amount);
    if (!label.trim() || isNaN(amt)) { setError("Renseignez un libellé et un montant valide"); return; }
    setBusy(true);
    try {
      await apiPost("/costs", { label: label.trim(), amount: amt, currency, category, recurring });
      setLabel(""); setAmount("");
      await refresh();
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  };

  const del = async (id: string) => {
    try { await apiDelete(`/costs/${id}`); await refresh(); } catch (e: any) { setError(e.message); }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backRow} testID="costs-back">
          <Ionicons name="chevron-back" size={20} color={colors.textPrimary} />
          <Text style={{ color: colors.textPrimary, fontSize: 15 }}>Retour</Text>
        </TouchableOpacity>
        <Overline>Infrastructure</Overline>
        <Text style={styles.title}>Coûts</Text>
        <Text style={styles.subtitle}>Suivi des dépenses VPS / API / données / maintenance</Text>

        {summary ? (
          <Card style={{ marginTop: spacing.md }}>
            <View style={{ flexDirection: "row" }}>
              <Stat label="Total mensuel" value={fmt.money(summary.monthly_total, "EUR")} testID="cost-monthly" />
              <Stat label="Total annuel" value={fmt.money(summary.yearly_total, "EUR")} testID="cost-yearly" />
            </View>
            <View style={{ flexDirection: "row", marginTop: spacing.md }}>
              <Stat label="One-off" value={fmt.money(summary.one_off_total, "EUR")} testID="cost-oneoff" />
              <Stat label="P&L réalisé" value={fmt.money(summary.current_realized_pnl, "USD")} valueColor={summary.current_realized_pnl >= 0 ? colors.success : colors.danger} testID="cost-pnl" />
            </View>
            {summary.by_category && Object.keys(summary.by_category).length > 0 ? (
              <View style={{ marginTop: spacing.md }}>
                <Text style={styles.label}>Par catégorie (mensuel)</Text>
                {Object.entries(summary.by_category).map(([k, v]: any) => (
                  <View key={k} style={styles.catRow}>
                    <Text style={styles.catName}>{k.toUpperCase()}</Text>
                    <Text style={styles.catVal}>{fmt.money(v, "EUR")}</Text>
                  </View>
                ))}
              </View>
            ) : null}
          </Card>
        ) : null}

        <SectionTitle>Ajouter une dépense</SectionTitle>
        <Card>
          <Input label="Libellé" value={label} onChangeText={setLabel} placeholder="VPS Hetzner CPX21" testID="cost-label-input" />
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <View style={{ flex: 2 }}><Input label="Montant" value={amount} onChangeText={setAmount} keyboardType="numeric" placeholder="8.50" testID="cost-amount-input" /></View>
            <View style={{ flex: 1 }}><Input label="Devise" value={currency} onChangeText={setCurrency} testID="cost-currency-input" /></View>
          </View>

          <Text style={styles.label}>Catégorie</Text>
          <View style={styles.chipRow}>
            {CATEGORIES.map((c) => (
              <TouchableOpacity key={c} onPress={() => setCategory(c)} style={[styles.chip, category === c && styles.chipOn]} testID={`cost-cat-${c}`}>
                <Text style={[styles.chipText, category === c && styles.chipTextOn]}>{c.toUpperCase()}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={[styles.label, { marginTop: spacing.md }]}>Fréquence</Text>
          <View style={styles.chipRow}>
            {(["once", "monthly", "yearly"] as const).map((r) => (
              <TouchableOpacity key={r} onPress={() => setRecurring(r)} style={[styles.chip, recurring === r && styles.chipOn]} testID={`cost-rec-${r}`}>
                <Text style={[styles.chipText, recurring === r && styles.chipTextOn]}>{r === "once" ? "Unique" : r === "monthly" ? "Mensuel" : "Annuel"}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {error ? <Text style={{ color: colors.danger, fontSize: 13, marginTop: 8 }}>{error}</Text> : null}
          <Button title="Ajouter" onPress={add} loading={busy} icon="add-circle" testID="cost-add-button" style={{ marginTop: spacing.md }} />
        </Card>

        <SectionTitle>Dépenses enregistrées ({items.length})</SectionTitle>
        {items.length === 0 ? (
          <Card><EmptyState icon="cash-outline" title="Aucune dépense" subtitle="Ajoutez votre première dépense d'infrastructure" testID="empty-costs" /></Card>
        ) : (
          items.map((it) => (
            <Card key={it.id} style={{ marginBottom: spacing.sm }} testID={`cost-item-${it.id}`}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <Text style={styles.itemLabel}>{it.label}</Text>
                    <Badge variant="neutral">{it.category.toUpperCase()}</Badge>
                  </View>
                  <Text style={styles.itemSub}>{it.recurring === "once" ? "Unique" : it.recurring === "monthly" ? "Mensuel" : "Annuel"} · {new Date(it.date).toLocaleDateString("fr-FR")}</Text>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={styles.itemAmount}>{fmt.money(it.amount, it.currency)}</Text>
                  <TouchableOpacity onPress={() => del(it.id)} style={styles.delBtn} testID={`cost-del-${it.id}`}>
                    <Ionicons name="trash-outline" size={14} color={colors.danger} />
                  </TouchableOpacity>
                </View>
              </View>
            </Card>
          ))
        )}
        <View style={{ height: spacing.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  scroll: { padding: spacing.md },
  backRow: { flexDirection: "row", alignItems: "center", gap: 4, marginBottom: spacing.md },
  title: { fontSize: 28, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.8, marginTop: 4 },
  subtitle: { fontSize: 13, color: colors.textSecondary, marginTop: 4 },
  label: { fontSize: 11, color: colors.textSecondary, textTransform: "uppercase", letterSpacing: 1, fontWeight: "700", marginBottom: 6 },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 18, borderColor: colors.borderStrong, borderWidth: 1, backgroundColor: colors.white },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: 12, color: colors.textPrimary, fontWeight: "600" },
  chipTextOn: { color: colors.white },
  catRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 6 },
  catName: { fontSize: 12, color: colors.textSecondary, fontWeight: "700" },
  catVal: { fontSize: 13, color: colors.textPrimary, fontWeight: "700" },
  itemLabel: { fontSize: 14, fontWeight: "700", color: colors.textPrimary },
  itemSub: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  itemAmount: { fontSize: 15, fontWeight: "800", color: colors.textPrimary },
  delBtn: { marginTop: 6, padding: 6, borderRadius: 6, backgroundColor: colors.dangerBg },
});
