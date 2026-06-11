import React, { useEffect, useState, useCallback } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Switch, TextInput, ActivityIndicator } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { Card, Button, Input } from "@/src/components/ui";
import { colors, spacing, radius } from "@/src/theme";
import { apiGet, apiPost } from "@/src/api/client";

const CATEGORIES = [
  { id: "all", label: "Tous" },
  { id: "forex", label: "Forex" },
  { id: "crypto", label: "Crypto" },
  { id: "metaux", label: "Métaux" },
  { id: "indices", label: "Indices" },
  { id: "energie", label: "Énergie" },
  { id: "actions", label: "Actions" },
  { id: "autres", label: "Autres" },
];

export default function MarketsScreen() {
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [singleMode, setSingleMode] = useState(false);
  const [singleSymbol, setSingleSymbol] = useState("");
  const [threshold, setThreshold] = useState("70");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const load = useCallback(() => {
    apiGet("/market/symbols")
      .then((d: any) => {
        setData(d);
        setSelected(d.selected || []);
        setSingleMode(d.single_symbol_mode);
        setSingleSymbol(d.single_symbol || "");
        setThreshold(`${d.min_confidence_score ?? 70}`);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleSymbol = (name: string) => {
    setSuccess(false);
    setSelected((prev) =>
      prev.includes(name) ? prev.filter((s) => s !== name) : [...prev, name]
    );
  };

  const save = async () => {
    setBusy(true); setError(null); setSuccess(false);
    try {
      await apiPost("/market/symbols", { symbols: selected });
      await apiPost("/market/single-mode", { enabled: singleMode, symbol: singleSymbol || selected[0] });
      const t = parseInt(threshold, 10);
      if (!isNaN(t) && t >= 0 && t <= 100) {
        await apiPost("/bot/config-flags", { min_confidence_score: t });
      }
      setSuccess(true);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  };

  if (!data) {
    return (
      <SafeAreaView style={styles.safe}>
        <ActivityIndicator style={{ marginTop: 60 }} color={colors.primary} />
      </SafeAreaView>
    );
  }

  const filtered = (data.symbols || []).filter((s: any) => {
    if (category !== "all" && s.category !== category) return false;
    if (search && !s.name.toUpperCase().includes(search.toUpperCase()) && !(s.description || "").toUpperCase().includes(search.toUpperCase())) return false;
    return true;
  });
  // Selected first, then alphabetical
  filtered.sort((a: any, b: any) => {
    const sa = selected.includes(a.name) ? 0 : 1;
    const sb = selected.includes(b.name) ? 0 : 1;
    return sa - sb || a.name.localeCompare(b.name);
  });
  const shown = filtered.slice(0, 80);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} testID="markets-back-button">
          <Ionicons name="chevron-back" size={24} color={colors.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Marchés autorisés</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120 }} keyboardShouldPersistTaps="handled">
        <Card>
          <Text style={styles.helper}>
            {"Le bot n'analyse et ne trade QUE les marchés que vous activez ici. Source: "}
            <Text style={{ fontWeight: "800", color: data.source === "mt5" ? colors.success : colors.warning }}>
              {data.source === "mt5" ? `MT5 (${data.symbols.length} instruments)` : "Simulateur"}
            </Text>
          </Text>
          <View style={styles.switchRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.switchLabel}>Mode marché unique</Text>
              <Text style={styles.switchHint}>{"Ne trader qu'un seul actif (changement instantané)"}</Text>
            </View>
            <Switch
              testID="single-mode-switch"
              value={singleMode}
              onValueChange={(v) => { setSingleMode(v); setSuccess(false); }}
              trackColor={{ false: colors.borderStrong, true: colors.primary }}
            />
          </View>
          {singleMode ? (
            <Input
              label="Actif unique"
              value={singleSymbol}
              onChangeText={(v: string) => { setSingleSymbol(v.toUpperCase()); setSuccess(false); }}
              placeholder="EURUSD"
              autoCapitalize="characters"
              testID="single-symbol-input"
            />
          ) : null}
          <Input
            label="Score de confiance minimum (0-100)"
            value={threshold}
            onChangeText={(v: string) => { setThreshold(v); setSuccess(false); }}
            keyboardType="numeric"
            testID="threshold-input"
          />
          <Text style={styles.fieldHint}>{"Le bot n'exécute un trade que si le score multi-facteurs atteint ce seuil"}</Text>
        </Card>

        <View style={styles.searchBox}>
          <Ionicons name="search" size={16} color={colors.textMuted} />
          <TextInput
            testID="market-search-input"
            value={search}
            onChangeText={setSearch}
            placeholder="Rechercher un instrument…"
            placeholderTextColor={colors.textMuted}
            style={styles.searchInput}
          />
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: spacing.md }}>
          {CATEGORIES.map((c) => (
            <TouchableOpacity
              key={c.id}
              testID={`category-chip-${c.id}`}
              onPress={() => setCategory(c.id)}
              style={[styles.chip, category === c.id && styles.chipActive]}
            >
              <Text style={[styles.chipText, category === c.id && styles.chipTextActive]}>{c.label}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        <Text style={styles.countText}>
          {selected.length} sélectionné(s) · {filtered.length} instrument(s) {filtered.length > 80 ? "(80 affichés, affinez la recherche)" : ""}
        </Text>

        {shown.map((s: any) => {
          const isOn = selected.includes(s.name);
          return (
            <TouchableOpacity
              key={s.name}
              testID={`symbol-row-${s.name}`}
              onPress={() => toggleSymbol(s.name)}
              style={[styles.symRow, isOn && styles.symRowActive]}
            >
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  <Text style={styles.symName}>{s.name}</Text>
                  <View style={styles.catBadge}><Text style={styles.catBadgeText}>{s.category}</Text></View>
                </View>
                <Text style={styles.symDesc} numberOfLines={1}>{s.description || "—"}</Text>
              </View>
              <Ionicons
                name={isOn ? "checkmark-circle" : "ellipse-outline"}
                size={24}
                color={isOn ? colors.success : colors.borderStrong}
              />
            </TouchableOpacity>
          );
        })}

        {error ? <Text style={styles.errorText}>{error}</Text> : null}
        {success ? <Text style={styles.successText}>✓ Sélection enregistrée — appliquée immédiatement</Text> : null}
        <Button title="Enregistrer la sélection" onPress={save} loading={busy} style={{ marginTop: spacing.md }} testID="markets-save-button" />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  headerTitle: { fontSize: 17, fontWeight: "800", color: colors.textPrimary },
  helper: { fontSize: 12, color: colors.textSecondary, lineHeight: 18, marginBottom: spacing.md },
  switchRow: { flexDirection: "row", alignItems: "center", marginBottom: spacing.md },
  switchLabel: { fontSize: 14, fontWeight: "700", color: colors.textPrimary },
  switchHint: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  fieldHint: { fontSize: 11, color: colors.textMuted, marginTop: -6, lineHeight: 16 },
  searchBox: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: colors.white, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: 12, marginTop: spacing.lg, marginBottom: spacing.md },
  searchInput: { flex: 1, paddingVertical: 10, fontSize: 14, color: colors.textPrimary },
  chip: { paddingHorizontal: 14, paddingVertical: 7, borderRadius: 100, backgroundColor: colors.white, borderWidth: 1, borderColor: colors.border, marginRight: 8 },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: 12, fontWeight: "700", color: colors.textSecondary },
  chipTextActive: { color: colors.white },
  countText: { fontSize: 11, color: colors.textMuted, marginBottom: spacing.sm },
  symRow: { flexDirection: "row", alignItems: "center", backgroundColor: colors.white, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: 12, marginBottom: 8 },
  symRowActive: { borderColor: colors.success, backgroundColor: "rgba(16,185,129,0.05)" },
  symName: { fontSize: 14, fontWeight: "800", color: colors.textPrimary },
  symDesc: { fontSize: 11, color: colors.textMuted, marginTop: 2 },
  catBadge: { backgroundColor: colors.surfaceAlt, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  catBadgeText: { fontSize: 9, fontWeight: "700", color: colors.textSecondary, textTransform: "uppercase" },
  errorText: { color: colors.danger, fontSize: 12, marginTop: spacing.md },
  successText: { color: colors.success, fontSize: 12, marginTop: spacing.md, fontWeight: "700" },
});
