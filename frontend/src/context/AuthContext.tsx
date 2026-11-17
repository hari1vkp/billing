import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import {
  api,
  clearTokens,
  getRefreshToken,
  getToken,
  setTokenResponse,
} from '../api/client';
import type {
  AuthUser,
  Business,
  LoginResponse,
  MessageResponse,
  RegisterPayload,
} from '../types';

interface AuthContextValue {
  user: AuthUser | null;
  business: Business | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
  setBusiness: (business: Business | null) => void;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Every authenticated user starts in their own experience. */
export function homeForRole(role?: string | null): string {
  return role === 'owner' ? '/admin' : '/pos';
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [business, setBusiness] = useState<Business | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const refreshProfile = useCallback(async () => {
    if (!getToken()) return;
    const [me, biz] = await Promise.all([
      api.get<AuthUser>('/auth/me'),
      api.get<Business>('/business').catch(() => null),
    ]);
    setUser({ ...me, business_name: me.business_name || biz?.name });
    if (biz) setBusiness(biz);
  }, []);

  useEffect(() => {
    let active = true;
    (async () => {
      if (!getToken()) {
        if (active) setLoading(false);
        return;
      }
      try {
        const [me, biz] = await Promise.all([
          api.get<AuthUser>('/auth/me'),
          api.get<Business>('/business').catch(() => null),
        ]);
        if (!active) return;
        setUser({ ...me, business_name: me.business_name || biz?.name });
        if (biz) setBusiness(biz);
      } catch {
        if (active) {
          clearTokens();
          setUser(null);
        }
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const data = await api.post<LoginResponse>('/auth/login', { email, password });
      setTokenResponse(data);
      setUser({ ...data.user, business_name: data.user.business_name });
      try {
        const biz = await api.get<Business>('/business');
        setBusiness(biz);
        setUser((current) =>
          current ? { ...current, business_name: current.business_name || biz.name } : current,
        );
      } catch {
        // Business is best-effort; it is loaded again on the next page load.
      }
      navigate(homeForRole(data.user.role), { replace: true });
    },
    [navigate],
  );

  const register = useCallback(
    async (payload: RegisterPayload) => {
      const data = await api.post<LoginResponse>('/auth/register', payload);
      setTokenResponse(data);
      setUser(data.user);
      try {
        const biz = await api.get<Business>('/business');
        setBusiness(biz);
        setUser((current) =>
          current ? { ...current, business_name: current.business_name || biz.name } : current,
        );
      } catch {
        // ignore
      }
      navigate(homeForRole(data.user.role), { replace: true });
    },
    [navigate],
  );

  const logout = useCallback(async () => {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      try {
        await api.post<MessageResponse>('/auth/logout', { refresh_token: refreshToken });
      } catch {
        // Always clear local session even when the server call fails.
      }
    }
    clearTokens();
    setUser(null);
    setBusiness(null);
    navigate('/login', { replace: true });
  }, [navigate]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      business,
      loading,
      login,
      register,
      logout,
      setBusiness,
      refreshProfile,
    }),
    [user, business, loading, login, register, logout, refreshProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
