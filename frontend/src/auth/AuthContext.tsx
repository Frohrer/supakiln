import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  api,
  getToken,
  setToken,
  clearToken,
  AUTH_UNAUTHORIZED_EVENT,
} from '../config/api';

export interface AuthUser {
  id: number;
  email: string;
  is_admin: boolean;
  disabled: boolean;
  created_at: string;
}

interface AuthState {
  user: AuthUser | null;
  // `authRequired` is true once we've seen a 401 from /auth/me — i.e.
  // the backend is enforcing auth and we're not logged in. The root
  // guard reads this to decide between "show login" and "show app as
  // anonymous system user".
  authRequired: boolean;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authRequired, setAuthRequired] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const r = await api.get<AuthUser>('/auth/me');
      setUser(r.data);
      setAuthRequired(false);
    } catch (e: any) {
      // 401 means either: no token and backend requires auth, or our
      // token is invalid/expired. Either way, we must show login.
      if (e?.status === 401 || e?.response?.status === 401) {
        setUser(null);
        setAuthRequired(true);
        // Drop a stale token so the next request doesn't keep failing.
        if (getToken()) clearToken();
      } else {
        // Network or other error — leave user/null and don't force
        // login, the app will just retry as anonymous.
        setUser(null);
        setAuthRequired(false);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // If any later request returns 401, the axios interceptor fires this
  // event. Drop the user and flip to "auth required" so the guard
  // routes to /login on the next render.
  useEffect(() => {
    const handler = () => {
      setUser(null);
      setAuthRequired(true);
    };
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, handler);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api.post('/auth/login', { email, password });
    setToken(r.data.session_token);
    setUser(r.data.user);
    setAuthRequired(false);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout');
    } catch {
      // best-effort server-side; we still wipe client state
    }
    clearToken();
    setUser(null);
    // After logout, probe /auth/me again — if backend is in anonymous
    // mode we'll land back on the system user; if it's enforcing, the
    // guard will route to /login.
    await refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({ user, authRequired, loading, login, logout, refresh }),
    [user, authRequired, loading, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthState => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside <AuthProvider>');
  }
  return ctx;
};
