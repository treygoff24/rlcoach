import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { getTrends, getBenchmarks } from '../api/client';
import { Card, CardHeader, CardContent, SkeletonChart, ErrorState, NoDataEmpty } from '../components';

const METRIC_OPTIONS = [
  { value: 'bcpm', label: 'Boost/Min', category: 'Boost' },
  { value: 'avg_boost', label: 'Avg Boost', category: 'Boost' },
  { value: 'goals', label: 'Goals', category: 'Fundamentals' },
  { value: 'assists', label: 'Assists', category: 'Fundamentals' },
  { value: 'saves', label: 'Saves', category: 'Fundamentals' },
  { value: 'shots', label: 'Shots', category: 'Fundamentals' },
];

const PERIOD_OPTIONS = [
  { value: '7d', label: 'Last 7 Days' },
  { value: '30d', label: 'Last 30 Days' },
  { value: '90d', label: 'Last 90 Days' },
  { value: 'all', label: 'All Time' },
];

export function Trends() {
  const [metric, setMetric] = useState('bcpm');
  const [period, setPeriod] = useState('30d');
  const [showBenchmark, setShowBenchmark] = useState(true);

  const { data, isLoading, error } = useQuery({
    queryKey: ['trends', metric, period],
    queryFn: () => getTrends({ metric, period }),
  });

  const { data: benchmarksData } = useQuery({
    queryKey: ['benchmarks', metric],
    queryFn: () => getBenchmarks({ metric, rank: 'GC1' }),
    enabled: showBenchmark,
  });

  if (error) {
    return <ErrorState message="Failed to load trends" />;
  }

  const benchmarkValue = benchmarksData?.items?.[0]?.median_value;

  const chartData = data?.values.map((v) => ({
    date: new Date(v.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    value: v.value,
    benchmark: benchmarkValue,
  })) ?? [];

  const selectedMetric = METRIC_OPTIONS.find((m) => m.value === metric);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--color-text)]">Trends</h1>
        <p className="text-sm text-[var(--color-text-muted)]">Track your performance over time</p>
      </div>

      {/* Controls */}
      <Card>
        <CardContent className="flex flex-wrap gap-4 items-center">
          <div>
            <label className="block text-xs text-[var(--color-text-muted)] mb-1">Metric</label>
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
              className="bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]"
            >
              {METRIC_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
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
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="showBenchmark"
              checked={showBenchmark}
              onChange={(e) => setShowBenchmark(e.target.checked)}
              className="rounded border-[var(--color-border)]"
            />
            <label htmlFor="showBenchmark" className="text-sm text-[var(--color-text-muted)]">
              Show GC1 Benchmark
            </label>
          </div>
        </CardContent>
      </Card>

      {/* Chart */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">{selectedMetric?.label} Over Time</h2>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <SkeletonChart />
          ) : chartData.length === 0 ? (
            <NoDataEmpty message="No data for selected period" />
          ) : (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis
                    dataKey="date"
                    stroke="var(--color-text-muted)"
                    tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
                  />
                  <YAxis
                    stroke="var(--color-text-muted)"
                    tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--color-bg-secondary)',
                      border: '1px solid var(--color-border)',
                      borderRadius: '8px',
                    }}
                    labelStyle={{ color: 'var(--color-text)' }}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="var(--color-primary)"
                    strokeWidth={2}
                    dot={false}
                    name={selectedMetric?.label}
                  />
                  {showBenchmark && benchmarkValue && (
                    <Line
                      type="monotone"
                      dataKey="benchmark"
                      stroke="var(--color-success)"
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      dot={false}
                      name="GC1 Benchmark"
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
