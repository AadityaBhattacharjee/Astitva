/**
 * Auth context — handles login, register, logout, JWT state, 401 recovery.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { authApi, clearToken, getToken, setToken } from "@/api/client";

interface AuthUser {
  id: number;
  email: string;
  role: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  hydrated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function parseTokenPayload(token: string): AuthUser | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1]!)) as {
      sub?: string;
      role?: string;
      exp?: number;
    };
    if (!payload.sub) return null;
    // Check expiry
    if (payload.exp && Date.now() / 1000 > payload.exp) return null;
    return { id: parseInt(payload.sub, 10), email: "", role: payload.role ?? "USER" };
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [hydrated, setHydrated] = useState(false);

  // Hydrate from stored token on mount
  useEffect(() => {
    const token = getToken();
    if (token) {
      const parsed = parseTokenPayload(token);
      if (parsed) {
        setUser(parsed);
      } else {
        clearToken();
      }
    }
    setHydrated(true);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const resp = await authApi.login(email, password);
    setToken(resp.access_token);
    const parsed = parseTokenPayload(resp.access_token);
    setUser(parsed ? { ...parsed, email } : null);
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const resp = await authApi.register(email, password);
    setToken(resp.access_token);
    const parsed = parseTokenPayload(resp.access_token);
    setUser(parsed ? { ...parsed, email } : null);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated: Boolean(user), hydrated, login, register, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
