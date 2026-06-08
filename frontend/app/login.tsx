import React, { useState } from "react";
import { View, Text, StyleSheet, KeyboardAvoidingView, Platform, ScrollView, TouchableOpacity } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { Button, Input, Card } from "@/src/components/ui";
import { colors, spacing } from "@/src/theme";
import { useAuth } from "@/src/context/AuthContext";

export default function LoginScreen() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async () => {
    setError(null);
    setLoading(true);
    try {
      await login(email.trim(), password);
      router.replace("/(tabs)/dashboard");
    } catch (e: any) {
      setError(e.message || "Erreur de connexion");
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <View style={styles.header}>
            <View style={styles.logoBox}>
              <Ionicons name="trending-up" size={28} color={colors.white} />
            </View>
            <Text style={styles.title}>Trading Bot</Text>
            <Text style={styles.subtitle}>Console professionnelle de trading automatisé</Text>
          </View>

          <Card style={{ marginTop: spacing.xl }}>
            <Text style={styles.cardTitle}>Connexion</Text>
            <Input
              testID="login-email-input"
              label="Email"
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              value={email}
              onChangeText={setEmail}
              placeholder="vous@example.com"
            />
            <Input
              testID="login-password-input"
              label="Mot de passe"
              secureTextEntry
              autoCapitalize="none"
              value={password}
              onChangeText={setPassword}
              placeholder="••••••••"
            />
            {error ? (
              <View style={styles.errorBox} testID="login-error">
                <Ionicons name="alert-circle" size={16} color={colors.danger} />
                <Text style={styles.errorText}>{error}</Text>
              </View>
            ) : null}
            <Button title="Se connecter" onPress={onSubmit} loading={loading} testID="login-submit-button" />
            <TouchableOpacity onPress={() => router.push("/register")} style={{ marginTop: spacing.md, alignItems: "center" }} testID="login-go-register">
              <Text style={styles.linkText}>Pas de compte ? Créer un compte</Text>
            </TouchableOpacity>
          </Card>

          <View style={styles.footer}>
            <Ionicons name="lock-closed" size={12} color={colors.textMuted} />
            <Text style={styles.footerText}>Identifiants chiffrés AES-256 · JWT signé</Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  scroll: { padding: spacing.lg, paddingTop: spacing.xxl, minHeight: "100%" },
  header: { alignItems: "center" },
  logoBox: {
    width: 56, height: 56, borderRadius: 14, backgroundColor: colors.primary,
    alignItems: "center", justifyContent: "center", marginBottom: spacing.md,
  },
  title: {
    fontSize: 32, fontWeight: "800", color: colors.textPrimary, letterSpacing: -1,
  },
  subtitle: {
    fontSize: 14, color: colors.textSecondary, marginTop: 6, textAlign: "center", maxWidth: 280,
  },
  cardTitle: {
    fontSize: 18, fontWeight: "700", color: colors.textPrimary, marginBottom: spacing.lg,
  },
  errorBox: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: colors.dangerBg, borderColor: "#FECACA", borderWidth: 1,
    padding: 10, borderRadius: 8, marginBottom: spacing.md,
  },
  errorText: { color: colors.danger, fontSize: 13, flex: 1 },
  linkText: { color: colors.primary, fontSize: 14, fontWeight: "600" },
  footer: {
    flexDirection: "row", alignItems: "center", gap: 6, justifyContent: "center",
    marginTop: spacing.xl,
  },
  footerText: { fontSize: 11, color: colors.textMuted, letterSpacing: 0.5 },
});
