// API client for the AgentFactory platform.
// Uses relative /api/v1 paths (Vite proxies to the backend in dev; FastAPI
// serves the built assets same-origin in production). Tokens live in
// localStorage; a 401 triggers one refresh-and-retry cycle.

import type { TokenPair, RunEvent } from "./types";

const ACCESS_KEY = "af_access_token";
const REFRESH_KEY = "af_refresh_token";
const USER_KEY = "af_user";

export const API_BASE = import.meta.env.VITE_API_BASE || "";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function getStoredUser(): TokenPair["user"] | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as TokenPair["user"]) : null;
  } catch {
    return null;
  }
}

export function storeSession(tokens: TokenPair): void {
  localStorage.setItem(ACCESS_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  localStorage.setItem(USER_KEY, JSON.stringify(tokens.user));
}

export function clearSession(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USER_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function tryRefresh(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const resp = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!resp.ok) return false;
    const tokens = (await resp.json()) as TokenPair;
    storeSession(tokens);
    return true;
  } catch {
    return false;
  }
}

interface FetchOptions extends RequestInit {
  auth?: boolean;
}

export async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { auth = true, headers, ...rest } = options;

  const buildHeaders = (): Record<string, string> => {
    const h: Record<string, string> = { ...(headers as Record<string, string>) };
    if (rest.body && !h["Content-Type"]) h["Content-Type"] = "application/json";
    if (auth) {
      const token = getAccessToken();
      if (token) h["Authorization"] = `Bearer ${token}`;
    }
    return h;
  };

  let resp = await fetch(`${API_BASE}${path}`, { ...rest, headers: buildHeaders() });

  // One refresh-and-retry on 401 (expired access token).
  if (resp.status === 401 && auth && !path.includes("/auth/")) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      resp = await fetch(`${API_BASE}${path}`, { ...rest, headers: buildHeaders() });
    }
  }

  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, detail);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const api = {
  get: <T>(path: string, options?: FetchOptions) => apiFetch<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: FetchOptions) =>
    apiFetch<T>(path, {
      ...options,
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  patch: <T>(path: string, body?: unknown, options?: FetchOptions) =>
    apiFetch<T>(path, {
      ...options,
      method: "PATCH",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  delete: <T>(path: string, options?: FetchOptions) => apiFetch<T>(path, { ...options, method: "DELETE" }),
};

/**
 * Consume an SSE stream via fetch + ReadableStream (design.md §6).
 * Calls onEvent for every parsed event; resolves when the stream ends.
 */
export async function streamRunEvents(
  url: string,
  onEvent: (event: RunEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(`${API_BASE}${url}`, {
    headers: { Authorization: `Bearer ${getAccessToken() ?? ""}` },
    signal,
  });
  if (!resp.ok || !resp.body) {
    throw new ApiError(resp.status, `SSE stream failed: ${resp.statusText}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "";

  const flush = () => {
    // SSE frames are separated by a blank line
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      let name = eventName;
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (name && data) {
        try {
          onEvent(JSON.parse(data) as RunEvent);
        } catch {
          /* skip malformed frame */
        }
      }
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    flush();
  }
  flush(); // trailing frame
}
