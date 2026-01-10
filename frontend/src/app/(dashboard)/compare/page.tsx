// frontend/src/app/(dashboard)/compare/page.tsx
'use client';

import { useState, useEffect } from 'react';
import { useSession } from 'next-auth/react';

type CompareMode = 'rank' | 'self';

interface StatComparison {
  value: number;
  benchmark: number;
  rank_name: string;
  difference: number;
  percentage: number;
  comparison: string;
}

interface BenchmarkResponse {
  rank_tier: number;
  rank_name: string;
  comparisons: Record<string, StatComparison>;
  has_data: boolean;
}

interface SelfComparisonMetric {
  name: string;
  current: number | null;
  previous: number | null;
  change_pct: number | null;
}

interface SelfComparisonResponse {
  current_period: string;
  previous_period: string;
  current_games: number;
  previous_games: number;
  metrics: SelfComparisonMetric[];
  has_data: boolean;
}

function getPercentileColor(comparison: string) {
  if (comparison === 'above') return 'text-green-400';
  if (comparison === 'on_par') return 'text-yellow-400';
  return 'text-red-400';
}

function getChangeColor(change: number | null) {
  if (change === null) return 'text-gray-400';
  if (change > 0) return 'text-green-400';
  if (change < 0) return 'text-red-400';
  return 'text-gray-400';
}

const METRIC_LABELS: Record<string, string> = {
  avg_goals: 'Goals/Game',
  avg_saves: 'Saves/Game',
  avg_assists: 'Assists/Game',
  avg_shots: 'Shots/Game',
  avg_bcpm: 'Boost/min',
  win_rate: 'Win Rate',
};

export default function ComparePage() {
  const { data: session } = useSession();
  const [mode, setMode] = useState<CompareMode>('rank');
  const [rankData, setRankData] = useState<BenchmarkResponse | null>(null);
  const [selfData, setSelfData] = useState<SelfComparisonResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      if (!session?.accessToken) {
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        if (mode === 'rank') {
          const res = await fetch('/api/v1/users/me/benchmarks', {
            headers: {
              Authorization: `Bearer ${session.accessToken}`,
            },
          });

          if (!res.ok) {
            if (res.status === 401) {
              setError('Session expired. Please sign in again.');
            } else {
              setError('Failed to load benchmark data.');
            }
            return;
          }

          const data: BenchmarkResponse = await res.json();
          setRankData(data);
        } else {
          const res = await fetch('/api/v1/users/me/compare/self?period=7d', {
            headers: {
              Authorization: `Bearer ${session.accessToken}`,
            },
          });

          if (!res.ok) {
            if (res.status === 401) {
              setError('Session expired. Please sign in again.');
            } else {
              setError('Failed to load comparison data.');
            }
            return;
          }

          const data: SelfComparisonResponse = await res.json();
          setSelfData(data);
        }
      } catch (err) {
        setError('Unable to connect to server.');
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, [session?.accessToken, mode]);

  if (loading) {
    return (
      <div className="p-6 lg:p-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white">Compare</h1>
          <p className="text-gray-400 mt-1">See how you stack up</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6 animate-pulse">
          <div className="h-6 w-32 bg-gray-700 rounded mb-4" />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="h-24 bg-gray-800 rounded" />
            ))}
          </div>
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
        <h1 className="text-2xl font-bold text-white">Compare</h1>
        <p className="text-gray-400 mt-1">See how you stack up</p>
      </div>

      {/* Mode Toggle */}
      <div className="flex gap-2 mb-8">
        <button
          onClick={() => setMode('rank')}
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
            mode === 'rank'
              ? 'bg-orange-500 text-white'
              : 'bg-gray-800 text-gray-400 hover:text-white'
          }`}
        >
          vs Your Rank
        </button>
        <button
          onClick={() => setMode('self')}
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
            mode === 'self'
              ? 'bg-orange-500 text-white'
              : 'bg-gray-800 text-gray-400 hover:text-white'
          }`}
        >
          vs Yourself
        </button>
      </div>

      {mode === 'rank' && rankData && (
        <div className="space-y-6">
          {/* Rank Info */}
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-400">Comparing against</p>
                <p className="text-2xl font-bold text-white">{rankData.rank_name}</p>
              </div>
              {!rankData.has_data && (
                <p className="text-sm text-yellow-400">
                  No replay data yet. Upload some replays to see comparisons.
                </p>
              )}
            </div>
          </div>

          {/* Metrics Grid */}
          {rankData.has_data && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {Object.entries(rankData.comparisons).map(([key, stat]) => (
                <div key={key} className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
                  <p className="text-sm text-gray-400 mb-3">{METRIC_LABELS[key] || key}</p>
                  <div className="flex items-end justify-between">
                    <div>
                      <p className="text-2xl font-bold text-white">
                        {stat.value.toFixed(1)}
                        {key === 'win_rate' && '%'}
                      </p>
                      <p className="text-xs text-gray-500">
                        Rank avg: {stat.benchmark.toFixed(1)}{key === 'win_rate' && '%'}
                      </p>
                    </div>
                    <div className="text-right">
                      <span className={`text-lg font-bold ${getPercentileColor(stat.comparison)}`}>
                        {stat.comparison === 'above' ? '+' : stat.comparison === 'below' ? '' : '±'}
                        {stat.difference.toFixed(1)}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {mode === 'rank' && !rankData?.has_data && rankData && (
        <div className="text-center py-12">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-800 flex items-center justify-center">
            <svg className="w-8 h-8 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-white mb-2">No Data Yet</h3>
          <p className="text-gray-400">Upload some replays to see how you compare to your rank.</p>
        </div>
      )}

      {mode === 'self' && selfData && (
        <div className="space-y-6">
          {/* Period Info */}
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
            <div className="flex items-center gap-4">
              <div>
                <span className="text-xl font-bold text-white">{selfData.current_period}</span>
                <span className="text-sm text-gray-500 ml-2">({selfData.current_games} games)</span>
              </div>
              <span className="text-gray-500">vs</span>
              <div>
                <span className="text-xl font-bold text-gray-400">{selfData.previous_period}</span>
                <span className="text-sm text-gray-500 ml-2">({selfData.previous_games} games)</span>
              </div>
            </div>
          </div>

          {/* Metrics Grid */}
          {selfData.has_data && selfData.metrics.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {selfData.metrics.map((m) => {
                const isPositive = m.change_pct !== null && m.change_pct > 0;
                const isNeutral = m.change_pct === null || m.change_pct === 0;
                return (
                  <div key={m.name} className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
                    <p className="text-sm text-gray-400 mb-3">{m.name}</p>
                    <div className="flex items-end justify-between">
                      <div>
                        <p className="text-2xl font-bold text-white">
                          {m.current !== null ? m.current.toFixed(1) : '--'}
                          {m.name === 'Win Rate' && m.current !== null && '%'}
                        </p>
                        <p className="text-xs text-gray-500">
                          Was: {m.previous !== null ? m.previous.toFixed(1) : '--'}
                          {m.name === 'Win Rate' && m.previous !== null && '%'}
                        </p>
                      </div>
                      <div className={`flex items-center gap-1 ${getChangeColor(m.change_pct)}`}>
                        {!isNeutral && m.change_pct !== null && (
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d={isPositive ? 'M5 10l7-7m0 0l7 7m-7-7v18' : 'M19 14l-7 7m0 0l-7-7m7 7V3'}
                            />
                          </svg>
                        )}
                        <span className="font-bold">
                          {m.change_pct !== null ? `${isPositive ? '+' : ''}${m.change_pct.toFixed(0)}%` : '--'}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-12">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-800 flex items-center justify-center">
                <svg className="w-8 h-8 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">Not Enough Data</h3>
              <p className="text-gray-400">Play more games to see how you&apos;re improving over time.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
