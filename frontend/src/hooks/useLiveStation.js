import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

/**
 * Single source of truth for live station UI.
 * Backend is authoritative; this hook never invents playback state.
 */
export function useLiveStation({ intervalMs = 1000, enabled = true } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const next = await api.getLiveStatus();
      if (!mounted.current) return;
      setData(next);
      setError(null);
    } catch (err) {
      if (!mounted.current) return;
      setError(err);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    if (!enabled) {
      setLoading(false);
      return undefined;
    }

    refresh();
    const timer = window.setInterval(refresh, intervalMs);

    return () => {
      mounted.current = false;
      window.clearInterval(timer);
    };
  }, [enabled, intervalMs, refresh]);

  return {
    data,
    loading,
    error,
    connected: Boolean(data) && !error,
    refresh,
  };
}
