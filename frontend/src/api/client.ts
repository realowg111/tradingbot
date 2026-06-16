// API client wrapping fetch with JWT injection.
// BASE_URL is resolved at runtime:
//   1) storage("tb_backend_url") if user has overridden it from Settings
//   2) process.env.EXPO_PUBLIC_BACKEND_URL fallback
import { storage } from "@/src/utils/storage";

const ENV_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";
export const BACKEND_URL_KEY = "tb_backend_url";

let _cachedBase: string | null = null;

export async function getBaseUrl(): Promise<string> {
  if (_cachedBase !== null) return _cachedBase;
  const override = (await storage.getItem<string>(BACKEND_URL_KEY, "")) || "";
  _cachedBase = (override || ENV_BASE || "").replace(/\/+$/, "");
  return _cachedBase;
}

export async function setBaseUrl(url: string): Promise<void> {
  const clean = (url || "").trim().replace(/\/+$/, "");
  if (clean) {
    await storage.setItem(BACKEND_URL_KEY, clean);
  } else {
    await storage.removeItem(BACKEND_URL_KEY);
  }
  _cachedBase = clean || ENV_BASE.replace(/\/+$/, "");
}

export function getEnvBaseUrl(): string {
  return ENV_BASE.replace(/\/+$/, "");
}

export const TOKEN_KEY = "tb_jwt_token";

async function authHeader(): Promise<Record<string, string>> {
  const token = await storage.secureGet<string>(TOKEN_KEY, "");
  if (token) return { Authorization: `Bearer ${token}` };
  return {};
}

export async function apiGet<T = any>(path: string): Promise<T> {
  const base = await getBaseUrl();
  const headers = { "Content-Type": "application/json", ...(await authHeader()) };
  const res = await fetch(`${base}/api${path}`, { method: "GET", headers });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status}: ${txt || res.statusText}`);
  }
  return res.json();
}

export async function apiPost<T = any>(path: string, body?: any): Promise<T> {
  const base = await getBaseUrl();
  const headers = { "Content-Type": "application/json", ...(await authHeader()) };
  const res = await fetch(`${base}/api${path}`, {
    method: "POST",
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const txt = await res.text();
    try {
      const parsed = JSON.parse(txt);
      throw new Error(parsed.detail || txt);
    } catch {
      throw new Error(txt || `${res.status}: ${res.statusText}`);
    }
  }
  return res.json();
}

export async function apiPut<T = any>(path: string, body?: any): Promise<T> {
  const base = await getBaseUrl();
  const headers = { "Content-Type": "application/json", ...(await authHeader()) };
  const res = await fetch(`${base}/api${path}`, {
    method: "PUT",
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const txt = await res.text();
    try {
      const parsed = JSON.parse(txt);
      throw new Error(parsed.detail || txt);
    } catch {
      throw new Error(txt || `${res.status}: ${res.statusText}`);
    }
  }
  return res.json();
}

export async function apiDelete<T = any>(path: string): Promise<T> {
  const base = await getBaseUrl();
  const headers = { "Content-Type": "application/json", ...(await authHeader()) };
  const res = await fetch(`${base}/api${path}`, { method: "DELETE", headers });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || `${res.status}: ${res.statusText}`);
  }
  return res.json();
}

export async function apiPatch<T = any>(path: string, body?: any): Promise<T> {
  const base = await getBaseUrl();
  const headers = { "Content-Type": "application/json", ...(await authHeader()) };
  const res = await fetch(`${base}/api${path}`, {
    method: "PATCH",
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const txt = await res.text();
    try {
      const parsed = JSON.parse(txt);
      throw new Error(parsed.detail || txt);
    } catch {
      throw new Error(txt || `${res.status}: ${res.statusText}`);
    }
  }
  return res.json();
}

export async function setToken(token: string) {
  await storage.secureSet(TOKEN_KEY, token);
}

export async function clearToken() {
  await storage.secureRemove(TOKEN_KEY);
}

export async function getToken(): Promise<string | null> {
  return await storage.secureGet<string>(TOKEN_KEY, "");
}
