import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getMe, login as loginRequest } from "../api/endpoints";
import type { CurrentUser } from "../api/types";

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<CurrentUser>;
  logout: () => void;
  setToken: (token: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setLoading(false);
      return;
    }
    getMe()
      .then((res) => setUser(res.data))
      .catch(() => localStorage.removeItem("access_token"))
      .finally(() => setLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    const res = await loginRequest(email, password);
    localStorage.setItem("access_token", res.data.access_token);
    const me = await getMe();
    setUser(me.data);
    return me.data;
  };

  const logout = () => {
    localStorage.removeItem("access_token");
    setUser(null);
  };

  const setToken = async (token: string) => {
    localStorage.setItem("access_token", token);
    const me = await getMe();
    setUser(me.data);
  };

  return <AuthContext.Provider value={{ user, loading, login, logout, setToken }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
