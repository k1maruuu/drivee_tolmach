"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { apiLogin, apiMe, apiRegister } from "@/lib/api/auth";
import type { TokenResponse, UserRead } from "@/lib/api/types";

type AuthContextValue = {
  user: UserRead | null;
  token: string | null;
  isLoading: boolean;
  login: (args: { email: string; password: string }) => Promise<void>;
  register: (args: {
    email: string;
    password: string;
    fullName?: string;
  }) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = "tolmach_access_token";

function readStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function storeToken(token: string | null) {
  if (typeof window === "undefined") return;
  try {
    if (!token) window.localStorage.removeItem(TOKEN_KEY);
    else window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // ignore
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserRead | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshMe = useCallback(async () => {
    if (!token) {
      setUser(null);
      return;
    }
    const me = await apiMe(token);
    setUser(me);
  }, [token]);

  useEffect(() => {
    const t = readStoredToken();
    setToken(t);
    setIsLoading(false);
  }, []);

  useEffect(() => {
    if (!token) {
      setUser(null);
      return;
    }
    void refreshMe().catch(() => {
      setUser(null);
      setToken(null);
      storeToken(null);
    });
  }, [token, refreshMe]);

  const login = useCallback(async ({ email, password }: { email: string; password: string }) => {
    const resp: TokenResponse = await apiLogin({ email, password });
    setToken(resp.access_token);
    storeToken(resp.access_token);
    setUser(resp.user);
  }, []);

  const register = useCallback(
    async ({ email, password, fullName }: { email: string; password: string; fullName?: string }) => {
      await apiRegister({ email, password, full_name: fullName });
      const resp: TokenResponse = await apiLogin({ email, password });
      setToken(resp.access_token);
      storeToken(resp.access_token);
      setUser(resp.user);
    },
    []
  );

  const logout = useCallback(() => {
    setUser(null);
    setToken(null);
    storeToken(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      isLoading,
      login,
      register,
      logout,
      refreshMe,
    }),
    [user, token, isLoading, login, register, logout, refreshMe]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

