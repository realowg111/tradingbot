import React, { useState } from "react";
import { View, Text, StyleSheet, KeyboardAvoidingView, Platform, ScrollView, TouchableOpacity } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { Button, Input, Card } from "@/src/components/ui";
import { colors, spacing } from "@/src/theme";
import { useAuth } from "@/src/context/AuthContext";

export default function RegisterScreen() {
  const router = useRouter();
  const { register } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async () => {
    setError(null);
    if (password !== confirm) { setError("Les mots de passe ne correspondent pas"); return; }
    if (password.length < 6) { setError("Mot de passe trop court (6 caractères min)"); return; }
    setLoading(true);
    try {
      await register(email.trim(), password);
      router.replace("/(tabs)/dashboard");
    } catch (e: any) {
      setError(e.message || "Erreur lors de l'inscription");
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <TouchableOpacity onPress={() => router.back()} style={styles.backRow} testID="register-back">
            <Ionicons name="chevron-back" size={20} color={colors.textPrimary} />
            <Text style={{ color: colors.textPrimary, fontSize: 15 }}>Retour</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Créer un compte</Text>
          <Text style={styles.subtitle}>Accès chiffré à votre console de trading</Text>

          <Card style={{ marginTop: spacing.lg }}>
            <Input testID="register-email-input" label="Email" keyboardType="email-address" autoCapitalize="none" value={email} onChangeText={setEmail} placeholder="vous@example.com" />
            <Input testID="register-password-input" label="Mot de passe (6+ caractères)" secureTextEntry value={password} onChangeText={setPassword} placeholder="••••••••" />
            <Input testID="register-confirm-input" label="Confirmer le mot de passe" secureTextEntry value={confirm} onChangeText={setConfirm} placeholder="••••••••" />
            {error ? (
              <View style={styles.errorBox} testID="register-error">
                <Ionicons name="alert-circle" size={16} color={colors.danger} />
                <Text style={styles.errorText}>{error}</Text>
              </View>
            ) : null}
            <Button title="S'inscrire" onPress={onSubmit} loading={loading} testID="register-submit-button" />
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  scroll: { padding: spacing.lg, minHeight: "100%" },
  backRow: { flexDirection: "row", alignItems: "center", gap: 4, marginBottom: spacing.md },
  title: { fontSize: 28, fontWeight: "800", color: colors.textPrimary, letterSpacing: -0.8 },
  subtitle: { fontSize: 14, color: colors.textSecondary, marginTop: 4 },
  errorBox: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: colors.dangerBg, borderColor: "#FECACA", borderWidth: 1, padding: 10, borderRadius: 8, marginBottom: spacing.md },
  errorText: { color: colors.danger, fontSize: 13, flex: 1 },
});
