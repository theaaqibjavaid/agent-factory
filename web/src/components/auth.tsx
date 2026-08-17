// Auth context + route guard for the Studio.
// Session state mirrors localStorage tokens (api.ts owns persistence).
import React, { createContext, useContext, useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import {
  clearSession,
  getStoredUser,
  getAccessToken,
  api,
} from "../lib/api";
import type { TokenPair, User } from "../lib/types";
import { Spinner } from "./ui";

interface AuthContextValue {
  user: User | null;
  initializing: boolean;
  signIn: (tokens: TokenPair) => void;
  signOut: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(() => getStoredUser());
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    // If we have a token but no cached user, fetch /me once.
    let cancelled = false;
    (async () => {
      if (getAccessToken() && !getStoredUser()) {
        try {
          const me = await api.get<User>("/api/v1/me");
          if (!cancelled) setUser(me);
        } catch {
          if (!cancelled) {
            clearSession();
            setUser(null);
          }
        }
      }
      if (!cancelled) setInitializing(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = (tokens: TokenPair) => setUser(tokens.user);
  const signOut = () => {
    const refresh = localStorage.getItem("af_refresh_token");
    if (refresh) {
      api
        .post("/api/v1/auth/logout", { refresh_token: refresh })
        .catch(() => undefined);
    }
    clearSession();
    setUser(null);
  };

  const refreshUser = async () => {
    const me = await api.get<User>("/api/v1/me");
    setUser(me);
  };

  return (
    <AuthContext.Provider value={{ user, initializing, signIn, signOut, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** Protects authenticated routes; preserves the intended path as returnTo. */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, initializing } = useAuth();
  const location = useLocation();

  if (initializing) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner className="h-6 w-6 text-primary" />
      </div>
    );
  }

  if (!user) {
    const returnTo = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/auth?returnTo=${returnTo}`} replace />;
  }

  return <>{children}</>;
}
