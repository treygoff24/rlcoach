import type { GamesParams } from '../api/client';
import type { Comparison, GameResult } from '../types/api';

export type { GameResult } from '../types/api';

export type GameFilters = Required<Pick<GamesParams, 'playlist' | 'limit' | 'offset'>> & {
  result: GameResult | '';
};

export function hasBenchmarkValue(value: number | null | undefined): value is number {
  return value != null;
}

export function buildCompareChartData(comparisons: Comparison[] = []) {
  return comparisons
    .filter(
      (c): c is Comparison & { target_median: number; difference_pct: number } =>
        c.target_median !== null && c.difference_pct !== null,
    )
    .map((c) => ({
      metric: c.metric.toUpperCase(),
      difference: c.difference_pct,
      myValue: c.my_value,
      targetMedian: c.target_median,
    }));
}

export function buildGamesParams(filters: GameFilters): GamesParams {
  return {
    playlist: filters.playlist || undefined,
    result: filters.result || undefined,
    limit: filters.limit,
    offset: filters.offset,
  };
}
