import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { getComparison } from '../api/client';
import { Card, CardHeader, CardContent, SkeletonChart, ErrorState, NoDataEmpty } from '../components';

const RANK_OPTIONS = [
  'GC3', 'GC2', 'GC1',
  'C3', 'C2', 'C1',
  'D3', 'D2', 'D1',
  'P3', 'P2', 'P1',
];

const PERIOD_OPTIONS = [
  { value: '7d', label: 'Last 7 Days' },
  { value: '30d', label: 'Last 30 Days' },
  { value: '90d', label: 'Last 90 Days' },
  { value: 'all', label: 'All Time' },
];

export function Compare() {
  const [rank, setRank] = useState('GC1');
  const [period, setPeriod] = useState('30d');

  const { data, isLoading, error } = useQuery({
    queryKey: ['compare', rank, period],
    queryFn: () => getComparison({ rank, period }),
  });

  if (error) {
    return <ErrorState message="Failed to load comparison" />;
  }

  const chartData = data?.comparisons
    .filter((c) => c.target_median !== null)
    .map((c) => ({
      metric: c.metric.toUpperCase(),
      difference: c.difference_pct ?? 0,
      myValue: c.my_value,
      targetMedian: c.target_median,
    })) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--color-text)]">Compare</h1>
        <p className="text-sm text-[var(--color-text-muted)]">Compare your stats to rank benchmarks</p>
      </div>

      {/* Controls */}
      <Card>
        <CardContent className="flex flex-wrap gap-4 items-center">
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">Target Rank</label>
            <select
              value={rank}
              onChange={(e) => setRank(e.target.value)}
              className="bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]"
            >
              {RANK_OPTIONS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">Period</label>
            <select
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              className="bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]"
            >
              {PERIOD_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          {data && (
            <div className="ml-auto text-sm text-[var(--color-text-muted)]">
              Based on {data.game_count} games
            </div>
          )}
        </CardContent>
      </Card>

      {/* Gap Chart */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Gap to {rank}</h2>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <SkeletonChart />
          ) : chartData.length === 0 ? (
            <NoDataEmpty message="No benchmark data available" />
          ) : (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis
                    type="number"
                    stroke="var(--color-text-muted)"
                    tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
                    tickFormatter={(v) => `${v > 0 ? '+' : ''}${v}%`}
                  />
                  <YAxis
                    type="category"
                    dataKey="metric"
                    stroke="var(--color-text-muted)"
                    tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
                    width={80}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--color-bg-secondary)',
                      border: '1px solid var(--color-border)',
                      borderRadius: '8px',
                    }}
                    labelStyle={{ color: 'var(--color-text)' }}
                    formatter={(value) => {
                      const numValue = Number(value) || 0;
                      return [`${numValue > 0 ? '+' : ''}${numValue.toFixed(1)}%`, 'Difference'];
                    }}
                  />
                  <Bar dataKey="difference" radius={[0, 4, 4, 0]}>
                    {chartData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={entry.difference >= 0 ? 'var(--color-success)' : 'var(--color-error)'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Comparison Table */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Detailed Comparison</h2>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4">Loading...</div>
          ) : data?.comparisons.length === 0 ? (
            <NoDataEmpty />
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--color-border)]">
                  <th className="text-left p-4 text-sm font-medium text-[var(--color-text-muted)]">Metric</th>
                  <th className="text-center p-4 text-sm font-medium text-[var(--color-text-muted)]">Your Avg</th>
                  <th className="text-center p-4 text-sm font-medium text-[var(--color-text-muted)]">{rank} Median</th>
                  <th className="text-center p-4 text-sm font-medium text-[var(--color-text-muted)]">Difference</th>
                </tr>
              </thead>
              <tbody>
                {data?.comparisons.map((c) => (
                  <tr key={c.metric} className="border-b border-[var(--color-border)]">
                    <td className="p-4 font-medium">{c.metric.toUpperCase()}</td>
                    <td className="p-4 text-center">{c.my_value.toFixed(2)}</td>
                    <td className="p-4 text-center text-[var(--color-text-muted)]">
                      {c.target_median?.toFixed(2) ?? '-'}
                    </td>
                    <td className="p-4 text-center">
                      {c.difference_pct !== null ? (
                        <span
                          className={
                            c.difference_pct >= 0
                              ? 'text-[var(--color-success)]'
                              : 'text-[var(--color-error)]'
                          }
                        >
                          {c.difference_pct > 0 ? '+' : ''}{c.difference_pct.toFixed(1)}%
                        </span>
                      ) : (
                        '-'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
