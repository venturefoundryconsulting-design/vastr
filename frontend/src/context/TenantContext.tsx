import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getMyTenant } from "../api/endpoints";
import type { TenantSelf } from "../api/types";
import { useAuth } from "./AuthContext";

const DARK_MODE_KEY = "vastr_dark_mode";

interface TenantContextValue {
  tenant: TenantSelf | null;
  loading: boolean;
  refresh: () => Promise<void>;
  /** A local browser preference, not tenant data - deliberately not synced to
   * the backend (dark mode is a per-user/per-device choice, not something a
   * company-wide "brand" setting like primary_color should force). Bundled
   * into this context rather than a separate provider purely to avoid one
   * more layer in main.tsx; it has nothing to do with the Tenant model. */
  darkMode: boolean;
  setDarkMode: (v: boolean) => void;
}

const TenantContext = createContext<TenantContextValue | undefined>(undefined);

function loadDarkModePreference(): boolean {
  try {
    return localStorage.getItem(DARK_MODE_KEY) === "1";
  } catch {
    return false;
  }
}

export function TenantProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [tenant, setTenant] = useState<TenantSelf | null>(null);
  const [loading, setLoading] = useState(true);
  const [darkMode, setDarkModeState] = useState(loadDarkModePreference);

  const refresh = async () => {
    if (!user || user.tenant_id == null) {
      setTenant(null);
      setLoading(false);
      return;
    }
    try {
      const res = await getMyTenant();
      setTenant(res.data);
    } catch {
      setTenant(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  const setDarkMode = (v: boolean) => {
    setDarkModeState(v);
    try {
      localStorage.setItem(DARK_MODE_KEY, v ? "1" : "0");
    } catch {
      // localStorage unavailable (private browsing etc.) - preference just won't persist
    }
  };

  return (
    <TenantContext.Provider value={{ tenant, loading, refresh, darkMode, setDarkMode }}>
      {children}
    </TenantContext.Provider>
  );
}

export function useTenant() {
  const ctx = useContext(TenantContext);
  if (!ctx) throw new Error("useTenant must be used within TenantProvider");
  return ctx;
}
