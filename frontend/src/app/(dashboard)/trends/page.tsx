// frontend/src/app/(dashboard)/trends/page.tsx
'use client';

import { useState, useEffect } from 'react';
import { useSession } from 'next-auth/react';

type MetricId = 'goals' | 'saves' | 'assists' | 'shots' | 'bcpm';
type TimeRange = '7d' | '30d' | '90d' | 'all';

interface TrendDataPoint {
  date: string | null;
  value: number;
}

interface TrendResponse {
  metric: string;
  period: string;
  values: TrendDataPoint[];
}

const metrics: Array<{ id: MetricId; label: string }> = [
  { id: 'goals', label: 'Goals' },
  { id: 'saves', label: 'Saves' },
  { id: 'assists', label: 'Assists' },
  { id: 'shots', label: 'Shots' },
  { id: 'bcpm', label: 'Boost/min' },
];

const timeRanges: Array<{ id: TimeRange; label: string }> = [
  { id: '7d', label: '7 Days' },
  { id: '30d', label: '30 Days' },
  { id: '90d', label: '90 Days' },
  { id: 'all', label: 'All Time' },
];

// Aggregate data points into buckets for display
function aggregateData(
  dataPoints: TrendDataPoint[],
  maxBuckets: number
): Array<{ label: string; value: number }> {
  if (dataPoints.length === 0) return [];
  if (dataPoints.length <= maxBuckets) {
    return dataPoints.map((d) => ({
      label: d.date ? new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '',
      value: d.value,
    }));
  }

  // Group into buckets
  const bucketSize = Math.ceil(dataPoints.length / maxBuckets);
  const buckets: Array<{ label: string; value: number }> = [];

  for (let i = 0; i < dataPoints.length; i += bucketSize) {
    const chunk = dataPoints.slice(i, i + bucketSize);
    const avgValue = chunk.reduce((sum, d) => sum + d.value, 0) / chunk.length;
    const firstDate = chunk[0]?.date;
    buckets.push({
      label: firstDate ? new Date(firstDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '',
      value: avgValue,
    });
  }

  return buckets;
}

export default function TrendsPage() {
  const { data: session } = useSession();
  const [selectedMetric, setSelectedMetric] = useState<MetricId>('goals');
  const [timeRange, setTimeRange] = useState<TimeRange>('30d');
  const [trendData, setTrendData] = useState<TrendDataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchTrends() {
      if (!session?.accessToken) {
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const res = await fetch(
          `/api/v1/analysis/trends?metric=${selectedMetric}&period=${timeRange}`,
          {
            headers: {
              Authorization: `Bearer ${session.accessToken}`,
            },
          }
        );

        if (!res.ok) {
          if (res.status === 401) {
            setError('Session expired. Please sign in again.');
          } else {
            setError('Failed to load trend data.');
          }
          return;
        }

        const data: TrendResponse = await res.json();
        setTrendData(data.values);
      } catch (err) {
        setError('Unable to connect to server.');
      } finally {
        setLoading(false);
      }
    }

    fetchTrends();
  }, [session?.accessToken, selectedMetric, timeRange]);

  // Aggregate data into buckets for display (max 10 bars)
  const aggregatedData = aggregateData(trendData, 10);
  const data = aggregatedData.map((d) => d.value);
  const max = data.length > 0 ? Math.max(...data) : 0;
  const min = data.length > 0 ? Math.min(...data) : 0;
  const range = max - min || 1;
  const trend = data.length >= 2
    ? data[data.length - 1] > data[0] ? 'up' : data[data.length - 1] < data[0] ? 'down' : 'stable'
    : 'stable';

  if (loading) {
    return (
      <div className="p-6 lg:p-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white">Trends</h1>
          <p className="text-gray-400 mt-1">Track your performance over time</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6 animate-pulse">
          <div className="h-6 w-32 bg-gray-700 rounded mb-4" />
          <div className="h-48 bg-gray-800 rounded" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 lg:p-8">
        <div className="text-center py-16">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-red-500/20 flex items-center justify-center">
            <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Something went wrong</h2>
          <p className="text-gray-400">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Trends</h1>
        <p className="text-gray-400 mt-1">Track your performance over time</p>
      </div>

      {/* Controls */}
      <div className="flex flex-col sm:flex-row gap-4 mb-8">
        {/* Metric selector */}
        <div className="flex flex-wrap gap-2">
          {metrics.map((m) => (
            <button
              key={m.id}
              onClick={() => setSelectedMetric(m.id)}
              className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                selectedMetric === m.id
                  ? 'bg-orange-500 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-white'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        {/* Time range selector */}
        <div className="flex gap-2 sm:ml-auto">
          {timeRanges.map((t) => (
            <button
              key={t.id}
              onClick={() => setTimeRange(t.id)}
              className={`px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
                timeRange === t.id
                  ? 'bg-gray-700 text-white'
                  : 'bg-gray-800/50 text-gray-400 hover:text-white'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-semibold text-white">
              {metrics.find((m) => m.id === selectedMetric)?.label}
            </h3>
            <p className="text-sm text-gray-400">
              {selectedMetric === 'bcpm' ? 'Boost collected per minute' : 'Per game average'}
            </p>
          </div>
          {data.length >= 2 && (
            <div className={`flex items-center gap-1 ${
              trend === 'up' ? 'text-green-400' : trend === 'down' ? 'text-red-400' : 'text-gray-400'
            }`}>
              {trend === 'up' && (
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
                </svg>
              )}
              {trend === 'down' && (
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                </svg>
              )}
              <span className="text-sm font-medium">
                {trend === 'up' ? 'Improving' : trend === 'down' ? 'Declining' : 'Stable'}
              </span>
            </div>
          )}
        </div>

        {/* Bar chart or empty state */}
        {data.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-gray-500">
            No data available for this time period
          </div>
        ) : (
          <div className="flex items-end gap-2 h-48">
            {data.map((value, i) => {
              const height = ((value - min) / range) * 100;
              const isLast = i === data.length - 1;
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-2">
                  <div
                    className={`w-full rounded-t transition-all ${
                      isLast ? 'bg-orange-500' : 'bg-gray-700'
                    }`}
                    style={{ height: `${Math.max(height, 10)}%` }}
                  />
                  <span className="text-xs text-gray-500">
                    {value.toFixed(1)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Stats Summary */}
      {data.length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
            <p className="text-sm text-gray-400">Current</p>
            <p className="text-2xl font-bold text-white">
              {data[data.length - 1]?.toFixed(1) ?? '--'}
            </p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
            <p className="text-sm text-gray-400">Average</p>
            <p className="text-2xl font-bold text-white">
              {(data.reduce((a, b) => a + b, 0) / data.length).toFixed(1)}
            </p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
            <p className="text-sm text-gray-400">Best</p>
            <p className="text-2xl font-bold text-green-400">
              {max.toFixed(1)}
            </p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
            <p className="text-sm text-gray-400">Worst</p>
            <p className="text-2xl font-bold text-red-400">
              {min.toFixed(1)}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
