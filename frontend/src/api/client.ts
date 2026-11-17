import type { LoginResponse, QueryValue } from '../types';

const BASE_URL = '/api/v1';
const ACCESS_KEY = 'bf_access_token';
const REFRESH_KEY = 'bf_refresh_token';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function getToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_KEY, accessToken);
  localStorage.setItem(REFRESH_KEY, refreshToken);
}

export function setTokenResponse(data: LoginResponse): void {
  setTokens(data.access_token, data.refresh_token);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export const tokenStore = {
  getToken,
  getRefreshToken,
  setTokens,
  setTokenResponse,
  clearTokens,
};

function isAuthPath(path: string): boolean {
  return (
    path.startsWith('/auth/login') ||
    path.startsWith('/auth/register') ||
    path.startsWith('/auth/refresh')
  );
}

function onSessionExpired(): void {
  clearTokens();
  // Never kick a customer off the public payment page.
  if (!window.location.pathname.startsWith('/pay/')) {
    window.location.href = '/login';
  }
}

let refreshInFlight: Promise<boolean> | null = null;

async function refreshTokens(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  refreshInFlight = (async () => {
    try {
      const response = await fetch(`${BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) return false;
      const data = (await response.json()) as LoginResponse;
      setTokenResponse(data);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

function authHeaders(init: RequestInit): Headers {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (
    init.body !== undefined &&
    !(init.body instanceof FormData) &&
    !headers.has('Content-Type')
  ) {
    headers.set('Content-Type', 'application/json');
  }
  return headers;
}

async function fetchWithAuth(
  path: string,
  init: RequestInit = {},
  allowRefresh = true,
): Promise<Response> {
  let response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: authHeaders(init),
  });

  if (response.status === 401 && allowRefresh && !isAuthPath(path)) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      response = await fetch(`${BASE_URL}${path}`, {
        ...init,
        headers: authHeaders(init),
      });
    } else {
      onSessionExpired();
    }
  }
  return response;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `Something went wrong (${response.status})`;
    try {
      const data = (await response.json()) as { detail?: unknown };
      if (typeof data.detail === 'string') {
        message = data.detail;
      } else if (Array.isArray(data.detail)) {
        message = data.detail
          .map((entry) => {
            if (entry && typeof entry === 'object' && 'msg' in entry) {
              const e = entry as { msg?: string; loc?: unknown[] };
              return `${Array.isArray(e.loc) ? e.loc.join(' · ') + ': ' : ''}${e.msg ?? 'Invalid value'}`;
            }
            return String(entry);
          })
          .join('; ');
      } else if (data.detail && typeof data.detail === 'object') {
        message = JSON.stringify(data.detail);
      }
    } catch {
      // keep generic message
    }
    throw new ApiError(message, response.status);
  }
  const text = await response.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

export function buildQuery(params?: Record<string, QueryValue>): string {
  if (!params) return '';
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    search.set(key, String(value));
  });
  const query = search.toString();
  return query ? `?${query}` : '';
}

export const api = {
  get: async <T>(path: string, params?: Record<string, QueryValue>): Promise<T> => {
    const response = await fetchWithAuth(`${path}${buildQuery(params)}`, { method: 'GET' });
    return parseResponse<T>(response);
  },
  post: async <T>(path: string, body?: unknown): Promise<T> => {
    const response = await fetchWithAuth(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return parseResponse<T>(response);
  },
  patch: async <T>(path: string, body?: unknown): Promise<T> => {
    const response = await fetchWithAuth(path, {
      method: 'PATCH',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return parseResponse<T>(response);
  },
  delete: async <T>(path: string): Promise<T> => {
    const response = await fetchWithAuth(path, { method: 'DELETE' });
    return parseResponse<T>(response);
  },
};

/** Fetch a binary/text resource with auth and trigger a browser download. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const response = await fetchWithAuth(path, { method: 'GET' });
  if (!response.ok) {
    await parseResponse(response);
    throw new ApiError('Download failed', response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Unauthenticated calls used by the public payment link page. */
export const publicApi = {
  get: async <T>(path: string): Promise<T> => {
    const response = await fetch(`${BASE_URL}${path}`, { method: 'GET' });
    return parseResponse<T>(response);
  },
  post: async <T>(path: string, body?: unknown): Promise<T> => {
    const response = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return parseResponse<T>(response);
  },
};
