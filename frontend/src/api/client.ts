// API client wrapping fetch with JWT injection
import { storage } from "@/src/utils/storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";

export const TOKEN_KEY = "tb_jwt_token";

async function authHeader(): Promise<Record<string, string>> {
  const token = await storage.secureGet<string>(TOKEN_KEY, "");
  if (token) return { Authorization: `Bearer ${token}` };
  return {};
}

export async function apiGet<T = any>(path: string): Promise<T> {
  const headers = { "Content-Type": "application/json", ...(await authHeader()) };
  const res = await fetch(`${BASE}/api${path}`, { method: "GET", headers });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status}: ${txt || res.statusText}`);
  }
  return res.json();
}

export async function apiPost<T = any>(path: string, body?: any): Promise<T> {
  const headers = { "Content-Type": "application/json", ...(await authHeader()) };
  const res = await fetch(`${BASE}/api${path}`, {
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
  const headers = { "Content-Type": "application/json", ...(await authHeader()) };
  const res = await fetch(`${BASE}/api${path}`, {
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
  const headers = { "Content-Type": "application/json", ...(await authHeader()) };
  const res = await fetch(`${BASE}/api${path}`, { method: "DELETE", headers });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || `${res.status}: ${res.statusText}`);
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
