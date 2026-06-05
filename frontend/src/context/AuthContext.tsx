// Auth context
import React, { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { apiGet, apiPost, setToken, clearToken, getToken } from "@/src/api/client";

export type User = { id: string; email: string; is_admin: boolean };

type AuthCtx = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const Ctx = createContext<AuthCtx | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const t = await getToken();
        if (t) {
          const me = await apiGet<User>("/auth/me");
          setUser(me);
        }
      } catch {
        await clearToken();
        setUser(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const login = async (email: string, password: string) => {
    const res = await apiPost<{ access_token: string; user: User }>("/auth/login", { email, password });
    await setToken(res.access_token);
    setUser(res.user);
  };

  const register = async (email: string, password: string) => {
    const res = await apiPost<{ access_token: string; user: User }>("/auth/register", { email, password });
    await setToken(res.access_token);
    setUser(res.user);
  };

  const logout = async () => {
    await clearToken();
    setUser(null);
  };

  return <Ctx.Provider value={{ user, loading, login, register, logout }}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth must be inside AuthProvider");
  return c;
}
