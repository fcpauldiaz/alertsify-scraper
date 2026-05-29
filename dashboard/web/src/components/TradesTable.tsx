import { useMemo, useState } from "react";
import {
  formatDuration,
  formatPercent,
  formatPremium,
  formatUsd,
  pnlClass,
} from "../format";
import type { Trade } from "../types";

type SortKey =
  | "underlying"
  | "status"
  | "realized_pnl"
  | "unrealized_pnl"
  | "created_at";

interface TradesTableProps {
  trades: Trade[];
  loading: boolean;
}

function activePnl(trade: Trade): number | null {
  return trade.status === "open" ? trade.unrealized_pnl : trade.realized_pnl;
}

export function TradesTable({ trades, loading }: TradesTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("created_at");
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = useMemo(() => {
    const copy = [...trades];
    copy.sort((a, b) => {
      let av: string | number | null = null;
      let bv: string | number | null = null;
      switch (sortKey) {
        case "underlying":
          av = a.underlying;
          bv = b.underlying;
          break;
        case "status":
          av = a.status;
          bv = b.status;
          break;
        case "realized_pnl":
          av = a.realized_pnl;
          bv = b.realized_pnl;
          break;
        case "unrealized_pnl":
          av = a.unrealized_pnl;
          bv = b.unrealized_pnl;
          break;
        case "created_at":
          av = a.created_at;
          bv = b.created_at;
          break;
      }
      if (av === bv) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      const cmp = av < bv ? -1 : 1;
      return sortAsc ? cmp : -cmp;
    });
    return copy;
  }, [trades, sortKey, sortAsc]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(key === "underlying");
    }
  }

  function sortIndicator(key: SortKey): string {
    if (sortKey !== key) return "";
    return sortAsc ? " ↑" : " ↓";
  }

  if (loading) {
    return (
      <section className="table-section" aria-busy="true">
        <h2>Trades</h2>
        <div className="table-wrap skeleton skeleton-chart" />
      </section>
    );
  }

  if (trades.length === 0) {
    return (
      <section className="table-section">
        <h2>Trades</h2>
        <div className="empty-state">
          No live trades recorded yet. Trades appear here after the scraper places
          orders for live Alertsify users.
        </div>
      </section>
    );
  }

  return (
    <section className="table-section">
      <h2>Trades</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>
                <button type="button" onClick={() => toggleSort("underlying")}>
                  Underlying{sortIndicator("underlying")}
                </button>
              </th>
              <th>Symbol</th>
              <th>Qty</th>
              <th>Entry</th>
              <th>Current / exit</th>
              <th>
                <button type="button" onClick={() => toggleSort("realized_pnl")}>
                  P&L{sortIndicator("realized_pnl")}
                </button>
              </th>
              <th>P&L %</th>
              <th>
                <button type="button" onClick={() => toggleSort("status")}>
                  Status{sortIndicator("status")}
                </button>
              </th>
              <th>
                <button type="button" onClick={() => toggleSort("created_at")}>
                  Opened{sortIndicator("created_at")}
                </button>
              </th>
              <th>Hold</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((trade) => {
              const pnl = activePnl(trade);
              return (
                <tr key={`${trade.alertsify_user_id}-${trade.alertsify_position_id}`}>
                  <td>{trade.underlying}</td>
                  <td className="mono">{trade.alertsify_symbol}</td>
                  <td>{trade.quantity}</td>
                  <td>{formatPremium(trade.entry_premium_per_share)}</td>
                  <td>{formatPremium(trade.current_or_exit_premium_per_share)}</td>
                  <td className={pnlClass(pnl)}>{formatUsd(pnl)}</td>
                  <td className={pnlClass(pnl)}>{formatPercent(trade.pnl_percent)}</td>
                  <td>
                    <span
                      className={
                        trade.status === "open" ? "status-open" : "status-closed"
                      }
                    >
                      {trade.status}
                    </span>
                  </td>
                  <td className="mono">
                    {trade.created_at.slice(0, 16).replace("T", " ")}
                  </td>
                  <td>{formatDuration(trade.hold_duration_seconds)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
