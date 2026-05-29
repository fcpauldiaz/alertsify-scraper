export type Period = "all" | "7d" | "30d";

export interface Summary {
  period: Period;
  total_equity: number | null;
  buying_power: number | null;
  total_unrealized_pnl: number;
  total_realized_pnl: number;
  open_count: number;
  closed_count: number;
  win_rate: number | null;
  avg_winner: number | null;
  avg_loser: number | null;
  pnl_by_underlying: Record<string, number>;
}

export interface Trade {
  alertsify_user_id: string;
  alertsify_position_id: string;
  alertsify_symbol: string;
  underlying: string;
  tradier_option_symbol: string;
  quantity: number;
  status: string;
  entry_premium_per_share: number | null;
  current_or_exit_premium_per_share: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number | null;
  pnl_percent: number | null;
  notional_at_entry: number | null;
  hold_duration_seconds: number | null;
  created_at: string;
  closed_at: string | null;
}

export interface EquityPoint {
  date: string;
  cumulative_realized_pnl: number;
}
