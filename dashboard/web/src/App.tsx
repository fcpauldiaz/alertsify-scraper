import { useCallback, useEffect, useState } from "react";
import {
  fetchEquityCurve,
  fetchHealth,
  fetchSummary,
  fetchTrades,
} from "./api";
import { Charts } from "./components/Charts";
import { KpiGrid } from "./components/KpiGrid";
import { TradesTable } from "./components/TradesTable";
import type { EquityPoint, Period, Summary, Trade } from "./types";

const PERIODS: { value: Period; label: string }[] = [
  { value: "all", label: "All" },
  { value: "30d", label: "30d" },
  { value: "7d", label: "7d" },
];

export default function App() {
  const [period, setPeriod] = useState<Period>("all");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [equity, setEquity] = useState<EquityPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [liveConfigured, setLiveConfigured] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const health = await fetchHealth();
      setLiveConfigured(health.live_tradier_configured);
      if (!health.live_tradier_configured) {
        setSummary(null);
        setTrades([]);
        setEquity([]);
        return;
      }
      const [summaryData, tradesData, equityData] = await Promise.all([
        fetchSummary(period),
        fetchTrades(period),
        fetchEquityCurve(period),
      ]);
      setSummary(summaryData);
      setTrades(tradesData);
      setEquity(equityData);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load dashboard";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-title">
          <h1>
            Trade performance
            <span className="live-badge">Live</span>
          </h1>
          <p>Realized and open P&L for live Tradier accounts only.</p>
        </div>
        <div className="toolbar">
          <div className="period-tabs" role="tablist" aria-label="Period">
            {PERIODS.map((item) => (
              <button
                key={item.value}
                type="button"
                role="tab"
                aria-selected={period === item.value}
                onClick={() => setPeriod(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {error ? (
        <div className="banner banner-error" role="alert">
          {error}
        </div>
      ) : null}

      {!liveConfigured && !loading ? (
        <div className="banner" role="status">
          Tradier live credentials are not configured. Set TRADIER_LIVE_API_KEY and
          TRADIER_LIVE_ACCOUNT_ID in your environment.
        </div>
      ) : null}

      <KpiGrid summary={summary} loading={loading} />
      <Charts equity={equity} summary={summary} loading={loading} />
      <TradesTable trades={trades} loading={loading} />
    </div>
  );
}
