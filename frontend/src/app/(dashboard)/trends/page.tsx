// frontend/src/app/(dashboard)/trends/page.tsx
'use client';

import { useState } from 'react';

type MetricId = 'goals' | 'saves' | 'assists' | 'shots' | 'win_rate';
type TimeRange = '7d' | '30d' | '90d' | 'all';

const metrics: Array<{ id: MetricId; label: string }> = [
  { id: 'goals', label: 'Goals' },
  { id: 'saves', label: 'Saves' },
  { id: 'assists', label: 'Assists' },
  { id: 'shots', label: 'Shots' },
  { id: 'win_rate', label: 'Win Rate' },
];

const timeRanges: Array<{ id: TimeRange; label: string }> = [
  { id: '7d', label: '7 Days' },
  { id: '30d', label: '30 Days' },
  { id: '90d', label: '90 Days' },
  { id: 'all', label: 'All Time' },
];

// Mock trend data
const mockData = {
  goals: [1.2, 1.1, 1.4, 1.3, 1.5, 1.2, 1.6],
  saves: [1.4, 1.3, 1.5, 1.4, 1.2, 1.6, 1.5],
  assists: [0.8, 0.7, 0.9, 0.8, 1.0, 0.9, 1.1],
  shots: [2.1, 2.0, 2.3, 2.2, 2.4, 2.1, 2.5],
  win_rate: [52, 48, 55, 50, 58, 54, 60],
};

export default function TrendsPage() {
  const [selectedMetric, setSelectedMetric] = useState<MetricId>('goals');
  const [timeRange, setTimeRange] = useState<TimeRange>('7d');

  const data = mockData[selectedMetric];
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const trend = data[data.length - 1] > data[0] ? 'up' : data[data.length - 1] < data[0] ? 'down' : 'stable';

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
              Average per game
            </p>
          </div>
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
        </div>

        {/* Simple bar chart */}
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
                  {selectedMetric === 'win_rate' ? `${value}%` : value.toFixed(1)}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Stats Summary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Current</p>
          <p className="text-2xl font-bold text-white">
            {selectedMetric === 'win_rate' ? `${data[data.length - 1]}%` : data[data.length - 1].toFixed(1)}
          </p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Average</p>
          <p className="text-2xl font-bold text-white">
            {selectedMetric === 'win_rate'
              ? `${Math.round(data.reduce((a, b) => a + b, 0) / data.length)}%`
              : (data.reduce((a, b) => a + b, 0) / data.length).toFixed(1)}
          </p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Best</p>
          <p className="text-2xl font-bold text-green-400">
            {selectedMetric === 'win_rate' ? `${max}%` : max.toFixed(1)}
          </p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Worst</p>
          <p className="text-2xl font-bold text-red-400">
            {selectedMetric === 'win_rate' ? `${min}%` : min.toFixed(1)}
          </p>
        </div>
      </div>
    </div>
  );
}
