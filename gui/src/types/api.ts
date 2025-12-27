// API response types for RLCoach

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

// Dashboard types
export interface QuickStats {
  games_today: number;
  wins_today: number;
  losses_today: number;
  win_rate_today: number;
  avg_bcpm_today: number | null;
}

export interface RecentGame {
  replay_id: string;
  played_at_utc: string;
  playlist: string;
  result: 'WIN' | 'LOSS' | 'DRAW';
  my_score: number;
  opponent_score: number;
  duration_seconds: number;
}

export interface DashboardResponse {
  quick_stats: QuickStats;
  recent_games: RecentGame[];
  games_today: number;
}

// Game/Replay types
export interface Game {
  replay_id: string;
  played_at_utc: string;
  play_date: string;
  playlist: string;
  result: 'WIN' | 'LOSS' | 'DRAW';
  my_score: number;
  opponent_score: number;
  duration_seconds: number;
  map: string;
}

export interface PlayerStats {
  player_id: string;
  display_name: string;
  team: 'BLUE' | 'ORANGE';
  is_me: boolean;
  is_teammate: boolean;
  goals: number;
  assists: number;
  saves: number;
  shots: number;
  bcpm: number | null;
  avg_boost: number | null;
  first_man_pct: number | null;
  second_man_pct: number | null;
  third_man_pct: number | null;
}

export interface ReplayDetail {
  replay_id: string;
  played_at_utc: string;
  playlist: string;
  result: 'WIN' | 'LOSS' | 'DRAW';
  my_score: number;
  opponent_score: number;
  duration_seconds: number;
  map: string;
  players: PlayerStats[];
}

export interface ReplayFull extends ReplayDetail {
  events: GameEvent[];
  json_report: Record<string, unknown>;
}

export interface GameEvent {
  type: string;
  time_seconds: number;
  player_id?: string;
  player_name?: string;
  team?: 'BLUE' | 'ORANGE';
  details?: Record<string, unknown>;
}

// Analysis types
export interface TrendValue {
  date: string;
  value: number;
}

export interface TrendsResponse {
  metric: string;
  period: string;
  values: TrendValue[];
}

export interface Benchmark {
  metric: string;
  playlist: string;
  rank_tier: string;
  median_value: number;
  p25_value: number;
  p75_value: number;
  elite_threshold: number | null;
  source: string | null;
}

export interface Comparison {
  metric: string;
  my_value: number;
  target_median: number | null;
  difference: number | null;
  difference_pct: number | null;
}

export interface CompareResponse {
  target_rank: string;
  playlist: string;
  comparisons: Comparison[];
  game_count: number;
}

export interface Pattern {
  metric: string;
  win_avg: number;
  loss_avg: number;
  delta: number;
  effect_size: number;
  direction: 'higher_when_winning' | 'lower_when_winning';
}

export interface PatternsResponse {
  patterns: Pattern[];
  win_count: number;
  loss_count: number;
}

export interface Weakness {
  metric: string;
  my_value: number;
  target_median: number;
  z_score: number;
  severity: 'critical' | 'moderate' | 'minor' | 'strength' | 'neutral';
}

export interface WeaknessesResponse {
  weaknesses: Weakness[];
  strengths: Weakness[];
  game_count: number;
}

// Player types
export interface Player {
  player_id: string;
  display_name: string;
  platform: string | null;
  is_me: boolean;
  is_tagged_teammate: boolean;
  teammate_notes: string | null;
  games_with_me: number;
  first_seen_utc: string | null;
  last_seen_utc: string | null;
}

export interface TendencyProfile {
  aggression_score: number;
  challenge_rate: number;
  first_man_tendency: number;
  boost_priority: number;
  mechanical_index: number;
  defensive_index: number;
}

export interface PlayerDetail extends Player {
  tendency_profile?: TendencyProfile;
}

export interface TagRequest {
  tagged?: boolean;
  notes?: string | null;
}
