// WebSocket-based live data hook with polling fallback
import { useEffect, useState, useRef, useCallback } from "react";
import { Platform } from "react-native";
import { getToken } from "@/src/api/client";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";

export type LivePosition = {
  id: string;
  symbol: string;
  side: "BUY" | "SELL";
  entry_price: number;
  current_price?: number | null;
  unrealized_pnl?: number;
  quantity: number;
  stop_loss: number;
  take_profit: number;
  strategy: string;
  mode: string;
  opened_at: string;
};

export type MT5Status = {
  connected: boolean;
  mode: "native" | "bridge" | "unavailable";
  has_native_lib: boolean;
  has_bridge_url: boolean;
  login?: string | null;
  server?: string | null;
  broker?: string | null;
  last_error?: string | null;
  last_heartbeat?: string | null;
};

export type LiveSnapshot = {
  state: {
    balance: number;
    equity: number;
    daily_pnl: number;
    realized_pnl: number;
    unrealized_pnl: number;
    open_positions: number;
    trades_today: number;
    daily_start_balance: number;
    paused_reason?: string | null;
    kill_switch_engaged: boolean;
    real_unlocked: boolean;
  };
  config_mode: "demo" | "real";
  config_enabled: boolean;
  prices: Record<string, number | null>;
  positions: LivePosition[];
  mt5_status: MT5Status;
  mt5_account: any | null;
};

export type ConnectionStatus = "connecting" | "live" | "polling" | "offline";

export function useLiveData() {
  const [snapshot, setSnapshot] = useState<LiveSnapshot | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pollIntervalRef = useRef<any>(null);
  const reconnectTimeoutRef = useRef<any>(null);
  const mounted = useRef(true);

  const connectWS = useCallback(async () => {
    const token = await getToken();
    if (!token) {
      setStatus("offline");
      return;
    }
    const wsUrl = BASE.replace(/^http/, "ws") + `/api/ws?token=${encodeURIComponent(token)}`;
    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      setStatus("connecting");

      ws.onopen = () => {
        if (!mounted.current) return;
        setStatus("live");
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      };

      ws.onmessage = (ev) => {
        if (!mounted.current) return;
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "snapshot") {
            setSnapshot(msg.data);
            setLastUpdate(new Date());
          }
        } catch {}
      };

      ws.onerror = () => {
        if (!mounted.current) return;
        setStatus("offline");
      };

      ws.onclose = () => {
        if (!mounted.current) return;
        wsRef.current = null;
        setStatus("offline");
        // Reconnect with backoff (3s)
        reconnectTimeoutRef.current = setTimeout(() => {
          if (mounted.current) connectWS();
        }, 3000);
        // Activate polling fallback
        startPolling();
      };
    } catch {
      setStatus("offline");
      startPolling();
    }
  }, []);

  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) return;
    setStatus("polling");
    const poll = async () => {
      try {
        const token = await getToken();
        const res = await fetch(`${BASE}/api/bot/state`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error("polling failed");
        const data = await res.json();
        const positions = await fetch(`${BASE}/api/positions/open`, {
          headers: { Authorization: `Bearer ${token}` },
        }).then((r) => r.json()).catch(() => []);
        if (mounted.current) {
          setSnapshot({
            state: data.state,
            config_mode: data.config_mode,
            config_enabled: data.config_enabled,
            prices: data.prices,
            positions,
            mt5_status: data.mt5_status || { connected: false, mode: "unavailable", has_native_lib: false, has_bridge_url: false },
            mt5_account: data.mt5_account || null,
          });
          setLastUpdate(new Date());
        }
      } catch {}
    };
    poll();
    pollIntervalRef.current = setInterval(poll, 3000);
  }, []);

  useEffect(() => {
    mounted.current = true;
    connectWS();
    return () => {
      mounted.current = false;
      if (wsRef.current) wsRef.current.close();
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    };
  }, [connectWS]);

  return { snapshot, status, lastUpdate };
}
