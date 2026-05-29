import { formatPercent, formatUsd } from "../format";
import type { Summary } from "../types";

interface KpiGridProps {
  summary: Summary | null;
  loading: boolean;
}

function SkeletonKpis() {
  return (
    <div className="kpi-grid" aria-busy="true">
      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="kpi-card skeleton skeleton-kpi" />
      ))}
    </div>
  );
}

export function KpiGrid({ summary, loading }: KpiGridProps) {
  if (loading || !summary) {
    return <SkeletonKpis />;
  }

  const winRate =
    summary.win_rate !== null ? formatPercent(summary.win_rate * 100) : "—";

  const items = [
    { label: "Equity", value: formatUsd(summary.total_equity) },
    { label: "Buying power", value: formatUsd(summary.buying_power) },
    {
      label: "Unrealized P&L",
      value: formatUsd(summary.total_unrealized_pnl),
    },
    {
      label: "Realized P&L",
      value: formatUsd(summary.total_realized_pnl),
    },
    { label: "Open positions", value: String(summary.open_count) },
    { label: "Win rate", value: winRate },
  ];

  return (
    <div className="kpi-grid">
      {items.map((item) => (
        <div key={item.label} className="kpi-card">
          <div className="label">{item.label}</div>
          <div className="value">{item.value}</div>
        </div>
      ))}
    </div>
  );
}
