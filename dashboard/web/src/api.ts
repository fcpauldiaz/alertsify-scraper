import type { EquityPoint, Period, Summary, Trade } from "./types";

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || response.statusText);
  }
  return response.json() as Promise<T>;
}

export async function fetchHealth(): Promise<{ live_tradier_configured: boolean }> {
  return fetchJson("/api/health");
}

export async function fetchSummary(period: Period): Promise<Summary> {
  return fetchJson(`/api/live/summary?period=${period}`);
}

export async function fetchTrades(period: Period): Promise<Trade[]> {
  const data = await fetchJson<{ trades: Trade[] }>(
    `/api/live/trades?period=${period}&limit=500`,
  );
  return data.trades;
}

export async function fetchEquityCurve(period: Period): Promise<EquityPoint[]> {
  const data = await fetchJson<{ points: EquityPoint[] }>(
    `/api/live/equity-curve?period=${period}`,
  );
  return data.points;
}
