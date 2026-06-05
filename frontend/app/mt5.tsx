import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { Card, Button, Input, SectionTitle, Overline, Badge } from "@/src/components/ui";
import { colors, spacing } from "@/src/theme";
import { apiGet, apiPost } from "@/src/api/client";

export default function MT5Screen() {
  const router = useRouter();
  const [existing, setExisting] = useState<any>(null);
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [server, setServer] = useState("");
  const [broker, setBroker] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    apiGet("/mt5/credentials").then((data) => {
      if (data) {
        setExisting(data);
        setLogin(data.login);
        setServer(data.server);
        setBroker(data.broker || "");
      }
    }).catch(() => {});
  }, []);

  const save = async () => {
    setError(null); setSuccess(false);
    if (!login || !password || !server) { setError("Login, mot de passe et serveur requis"); return; }
    setBusy(true);
    try {
      await apiPost("/mt5/credentials", { login, password, server, broker });
      setSuccess(true);
      setPassword("");
      const data = await apiGet("/mt5/credentials");
      setExisting(data);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backRow} testID="mt5-back">
          <Ionicons name="chevron-back" size={20} color={colors.textPrimary} />
          <Text style={{ color: colors.textPrimary, fontSize: 15 }}>Retour</Text>
        </TouchableOpacity>
        <Overline>Connexion broker</Overline>
        <Text style={styles.title}>Identifiants MT5</Text>
        <Text style={styles.subtitle}>Stockés chiffrés AES-256 sur le serveur, jamais en clair</Text>

        <Card style={{ marginTop: spacing.md, backgroundColor: colors.warningBg, borderColor: "#FCD34D" }}>
          <View style={{ flexDirection: "row", gap: 8, alignItems: "flex-start" }}>
            <Ionicons name="information-circle" size={18} color={colors.warning} />
            <Text style={{ flex: 1, fontSize: 12, color: "#92400E", lineHeight: 18 }}>
              Pour l'instant le bot utilise un simulateur MT5 interne (paper trading réaliste). Saisir vos identifiants ici n'enclenchera PAS le trading réel : un connecteur MT5 sera activé après votre passage en mode RÉEL et la validation de la phase paper.
            </Text>
          </View>
        </Card>

        {existing ? (
          <Card style={{ marginTop: spacing.md }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <View>
                <Text style={styles.existingLabel}>Identifiants enregistrés</Text>
                <Text style={styles.existingLogin} testID="mt5-existing-login">Compte: {existing.login}</Text>
                <Text style={styles.existingServer}>Serveur: {existing.server}{existing.broker ? ` · ${existing.broker}` : ""}</Text>
              </View>
              <Badge variant="success">CHIFFRÉS</Badge>
            </View>
          </Card>
        ) : null}

        <SectionTitle>Saisir les identifiants</SectionTitle>
        <Card>
          <Input label="Login MT5 (numéro de compte)" value={login} onChangeText={setLogin} placeholder="12345678" keyboardType="numeric" testID="mt5-login-input" />
          <Input label="Mot de passe" value={password} onChangeText={setPassword} placeholder="••••••••" secureTextEntry testID="mt5-password-input" />
          <Input label="Serveur" value={server} onChangeText={setServer} placeholder="ICMarketsSC-Demo" autoCapitalize="none" testID="mt5-server-input" />
          <Input label="Broker (optionnel)" value={broker} onChangeText={setBroker} placeholder="IC Markets" testID="mt5-broker-input" />

          {error ? <Text style={{ color: colors.danger, fontSize: 13, marginBottom: 8 }}>{error}</Text> : null}
          {success ? (
            <View style={styles.okBox} testID="mt5-save-success">
              <Ionicons name="lock-closed" size={14} color={colors.success} />
              <Text style={{ color: colors.success, fontSize: 13, fontWeight: "600" }}>Identifiants chiffrés et sauvegardés</Text>
            </View>
          ) : null}
          <Button title="Chiffrer & sauvegarder" onPress={save} loading={busy} icon="lock-closed" testID="mt5-save-button" />
        </Card>

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
  existingLabel: { fontSize: 11, color: colors.textSecondary, fontWeight: "700", textTransform: "uppercase", letterSpacing: 1 },
  existingLogin: { fontSize: 15, color: colors.textPrimary, fontWeight: "700", marginTop: 4 },
  existingServer: { fontSize: 12, color: colors.textSecondary, marginTop: 2 },
  okBox: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.successBg, padding: 10, borderRadius: 8, marginBottom: spacing.md },
});
