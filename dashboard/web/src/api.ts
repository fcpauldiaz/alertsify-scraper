import type { EquityPoint, Period, Summary, Trade } from "./types";

const API_KEY_STORAGE = "alertsify_dashboard_api_key";

interface DashboardBootstrap {
  apiKey?: string | null;
  authRequired?: boolean;
}

declare global {
  interface Window {
    __ALERTSIFY_DASHBOARD__?: DashboardBootstrap;
  }
}

export function getBootstrapConfig(): DashboardBootstrap {
  return window.__ALERTSIFY_DASHBOARD__ ?? {};
}

export function isApiKeyInjected(): boolean {
  return Boolean(getBootstrapConfig().apiKey?.trim());
}

export function resolveApiKey(): string {
  const injected = getBootstrapConfig().apiKey?.trim();
  if (injected) {
    return injected;
  }
  return getStoredApiKey();
}

export function getStoredApiKey(): string {
  return sessionStorage.getItem(API_KEY_STORAGE) ?? "";
}

export function setStoredApiKey(key: string): void {
  if (key) {
    sessionStorage.setItem(API_KEY_STORAGE, key);
  } else {
    sessionStorage.removeItem(API_KEY_STORAGE);
  }
}

async function fetchJson<T>(path: string, apiKey: string): Promise<T> {
  const headers: HeadersInit = {};
  if (apiKey) {
    headers.Authorization = `Bearer ${apiKey}`;
  }
  const response = await fetch(path, { headers });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || response.statusText);
  }
  return response.json() as Promise<T>;
}

export async function fetchHealth(): Promise<{
  live_tradier_configured: boolean;
  auth_required?: boolean;
}> {
  return fetchJson("/api/health", "");
}

export async function fetchSummary(period: Period, apiKey: string): Promise<Summary> {
  return fetchJson(`/api/live/summary?period=${period}`, apiKey);
}

export async function fetchTrades(period: Period, apiKey: string): Promise<Trade[]> {
  const data = await fetchJson<{ trades: Trade[] }>(
    `/api/live/trades?period=${period}&limit=500`,
    apiKey,
  );
  return data.trades;
}

export async function fetchEquityCurve(
  period: Period,
  apiKey: string,
): Promise<EquityPoint[]> {
  const data = await fetchJson<{ points: EquityPoint[] }>(
    `/api/live/equity-curve?period=${period}`,
    apiKey,
  );
  return data.points;
}
