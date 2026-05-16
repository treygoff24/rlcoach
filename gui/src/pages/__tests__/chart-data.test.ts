import { describe, expect, it } from 'vitest';

import {
  buildCompareChartData,
  buildGamesParams,
  hasBenchmarkValue,
} from '../dataTransforms';
import type { Comparison } from '../../types/api';

describe('Trends benchmark handling', () => {
  it('treats zero-valued benchmarks as present', () => {
    expect(hasBenchmarkValue(0)).toBe(true);
    expect(hasBenchmarkValue(null)).toBe(false);
    expect(hasBenchmarkValue(undefined)).toBe(false);
  });
});

describe('Compare chart data', () => {
  it('does not coerce unavailable percentage differences into zero bars', () => {
    const comparisons: Comparison[] = [
      {
        metric: 'bcpm',
        my_value: 0,
        target_median: 50,
        difference: null,
        difference_pct: null,
      },
      {
        metric: 'goals',
        my_value: 2,
        target_median: 1,
        difference: 1,
        difference_pct: 100,
      },
    ];

    expect(buildCompareChartData(comparisons)).toEqual([
      {
        metric: 'GOALS',
        difference: 100,
        myValue: 2,
        targetMedian: 1,
      },
    ]);
  });
});

describe('Games query params', () => {
  it('omits the result param when All Results is selected', () => {
    expect(
      buildGamesParams({
        playlist: '',
        result: '',
        limit: 20,
        offset: 0,
      }),
    ).toEqual({
      playlist: undefined,
      result: undefined,
      limit: 20,
      offset: 0,
    });
  });
});
