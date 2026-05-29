import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { EquityPoint, Summary } from "../types";

interface ChartsProps {
  equity: EquityPoint[];
  summary: Summary | null;
  loading: boolean;
}

const CHART_PROFIT = "oklch(45% 0.12 155)";
const CHART_LOSS = "oklch(48% 0.14 25)";
const CHART_LINE = "oklch(52% 0.14 250)";
const CHART_GRID = "oklch(88% 0.02 250)";

export function Charts({ equity, summary, loading }: ChartsProps) {
  if (loading) {
    return (
      <div className="charts-row" aria-busy="true">
        <div className="chart-panel skeleton skeleton-chart" />
        <div className="chart-panel skeleton skeleton-chart" />
      </div>
    );
  }

  const underlyingData = summary
    ? Object.entries(summary.pnl_by_underlying)
        .map(([underlying, pnl]) => ({ underlying, pnl }))
        .sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl))
        .slice(0, 12)
    : [];

  return (
    <div className="charts-row">
      <div className="chart-panel">
        <h2>Equity curve (realized)</h2>
        {equity.length === 0 ? (
          <p className="empty-state">No closed trades in this period.</p>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={equity}>
              <CartesianGrid stroke={CHART_GRID} strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(value: number) => [
                  `$${value.toFixed(2)}`,
                  "Cumulative",
                ]}
              />
              <Line
                type="monotone"
                dataKey="cumulative_realized_pnl"
                stroke={CHART_LINE}
                strokeWidth={2}
                dot={false}
                isAnimationActive={!window.matchMedia(
                  "(prefers-reduced-motion: reduce)",
                ).matches}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
      <div className="chart-panel">
        <h2>P&L by underlying</h2>
        {underlyingData.length === 0 ? (
          <p className="empty-state">No P&L breakdown yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={underlyingData} layout="vertical" margin={{ left: 48 }}>
              <CartesianGrid stroke={CHART_GRID} strokeDasharray="3 3" />
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis
                type="category"
                dataKey="underlying"
                tick={{ fontSize: 11 }}
                width={44}
              />
              <Tooltip formatter={(value: number) => [`$${value.toFixed(2)}`, "P&L"]} />
              <Bar
                dataKey="pnl"
                fill={CHART_LINE}
                isAnimationActive={!window.matchMedia(
                  "(prefers-reduced-motion: reduce)",
                ).matches}
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
