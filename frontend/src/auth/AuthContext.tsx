import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import api from "@/lib/apiClient";

type User = { id: string; email: string; username: string; role: string; is_active: boolean; created_at: string; ebay_connected: boolean };
type AuthContextShape = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, username: string, password: string, role?: string) => Promise<void>;
  logout: () => void;
  refreshMe: () => Promise<void>;
};

const AuthContext = createContext<AuthContextShape | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshMe = useCallback(async () => {
    try {
      console.log("[Auth] Fetching /auth/me...");
      const { data } = await api.get("/auth/me");
      console.log("[Auth] User data received:", data?.email);
      setUser(data);
    } catch (error) {
      console.error("[Auth] Failed to fetch user data:", error);
      setUser(null);
      localStorage.removeItem("auth_token");
      throw error; // Re-throw so caller knows it failed
    }
  }, []);

  const initAuth = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("auth_token");
      if (!token) {
        setUser(null);
        return;
      }
      await refreshMe();
    } finally {
      setLoading(false);
    }
  }, [refreshMe]);

  const login = useCallback(async (email: string, password: string) => {
    setLoading(true);
    try {
      console.log("[Auth] Attempting login for:", email);
      const { data } = await api.post("/auth/login", { email, password });
      const token: string = data?.access_token;
      if (!token) {
        console.error("[Auth] No access_token in login response:", data);
        throw new Error("No access_token in response");
      }
      console.log("[Auth] Login successful, token received");
      localStorage.setItem("auth_token", token);

      // Await refreshMe to ensure user is set before login completes
      console.log("[Auth] Fetching user data...");
      await refreshMe();
      console.log("[Auth] User data fetched successfully");
    } catch (error) {
      console.error("[Auth] Login error:", error);
      // Clear token if login failed
      localStorage.removeItem("auth_token");
      throw error;
    } finally {
      setLoading(false);
    }
  }, [refreshMe]);

  const register = useCallback(async (email: string, username: string, password: string, role?: string) => {
    setLoading(true);
    try {
      const { data: newUser } = await api.post("/auth/register", { email, username, password, role });
      const { data: loginData } = await api.post("/auth/login", { email, password });
      const token: string = loginData?.access_token;
      if (!token) throw new Error("No access_token in response");
      localStorage.setItem("auth_token", token);
      setUser(newUser);
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("token");
    setUser(null);
  }, []);

  useEffect(() => {
    void initAuth();
    const onStorage = (e: StorageEvent) => {
      if (e.key === "auth_token") void initAuth();
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [initAuth]);

  const value = useMemo(() => ({ user, loading, login, register, logout, refreshMe }), [user, loading, login, register, logout, refreshMe]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};

