// frontend/src/app/(dashboard)/page.tsx
'use client';

import { useState, useEffect } from 'react';
import { useSession } from 'next-auth/react';
import Link from 'next/link';

interface MechanicStat {
  name: string;
  count: number;
}

interface DashboardStats {
  total_replays: number;
  recent_win_rate: number | null;
  avg_goals: number | null;
  avg_assists: number | null;
  avg_saves: number | null;
  avg_shots: number | null;
  top_mechanics: MechanicStat[];
  recent_trend: 'up' | 'down' | 'stable';
  has_data: boolean;
}

interface StatComparison {
  value: number;
  benchmark: number;
  rank_name: string;
  difference: number;
  percentage: number;
  comparison: 'above' | 'below' | 'on_par';
}

interface BenchmarkData {
  rank_tier: number;
  rank_name: string;
  comparisons: Record<string, StatComparison>;
  has_data: boolean;
}

function ComparisonBadge({ comparison }: { comparison: 'above' | 'below' | 'on_par' }) {
  if (comparison === 'above') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-green-400">
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
        </svg>
        Above rank
      </span>
    );
  }
  if (comparison === 'below') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-red-400">
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
        </svg>
        Below rank
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-gray-400">
      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14" />
      </svg>
      On par
    </span>
  );
}

function StatCard({
  label,
  value,
  subtext,
  large = false,
  comparison,
}: {
  label: string;
  value: string | number;
  subtext?: string;
  large?: boolean;
  comparison?: StatComparison;
}) {
  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
      <p className="text-sm text-gray-400 mb-1">{label}</p>
      <p className={`font-bold ${large ? 'text-3xl' : 'text-2xl'} text-white`}>
        {value}
      </p>
      <div className="flex items-center justify-between mt-1">
        {subtext && <p className="text-xs text-gray-500">{subtext}</p>}
        {comparison && <ComparisonBadge comparison={comparison.comparison} />}
      </div>
    </div>
  );
}

function MechanicCard({
  name,
  count,
}: {
  name: string;
  count: number;
}) {
  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <h3 className="font-medium text-white">{name}</h3>
      </div>
      <div className="flex items-end justify-between">
        <div>
          <p className="text-3xl font-bold text-white">{count}</p>
          <p className="text-sm text-gray-400">total</p>
        </div>
      </div>
    </div>
  );
}

function StatSkeleton({ large = false }: { large?: boolean }) {
  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4 animate-pulse">
      <div className="h-4 w-20 bg-gray-700 rounded mb-2" />
      <div className={`${large ? 'h-9 w-24' : 'h-8 w-16'} bg-gray-700 rounded`} />
    </div>
  );
}

function MechanicSkeleton() {
  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4 animate-pulse">
      <div className="h-5 w-24 bg-gray-700 rounded mb-4" />
      <div className="h-9 w-16 bg-gray-700 rounded" />
    </div>
  );
}

export default function DashboardHome() {
  const { data: session } = useSession();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [benchmarks, setBenchmarks] = useState<BenchmarkData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      if (!session?.accessToken) {
        setLoading(false);
        return;
      }

      try {
        // Fetch stats and benchmarks in parallel
        const [statsRes, benchmarksRes] = await Promise.all([
          fetch('/api/v1/users/me/dashboard', {
            headers: {
              Authorization: `Bearer ${session.accessToken}`,
            },
          }),
          fetch('/api/v1/users/me/benchmarks', {
            headers: {
              Authorization: `Bearer ${session.accessToken}`,
            },
          }),
        ]);

        if (!statsRes.ok) {
          if (statsRes.status === 401) {
            setError('Session expired. Please sign in again.');
          } else {
            setError('Failed to load dashboard stats.');
          }
          return;
        }

        const statsData = await statsRes.json();
        setStats(statsData);

        // Benchmarks are optional - don't fail if unavailable
        if (benchmarksRes.ok) {
          const benchmarksData = await benchmarksRes.json();
          setBenchmarks(benchmarksData);
        }
      } catch (err) {
        setError('Unable to connect to server.');
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, [session?.accessToken]);

  if (loading) {
    return (
      <div className="p-6 lg:p-8 space-y-8">
        {/* Hero skeleton */}
        <div className="animate-pulse">
          <div className="h-8 w-48 bg-gray-700 rounded mb-2" />
          <div className="h-4 w-32 bg-gray-800 rounded" />
        </div>

        {/* Stats skeleton */}
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
          <StatSkeleton large />
          <StatSkeleton />
          <StatSkeleton />
          <StatSkeleton />
          <StatSkeleton />
        </div>

        {/* Mechanics skeleton */}
        <div>
          <div className="h-6 w-40 bg-gray-700 rounded mb-4" />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <MechanicSkeleton />
            <MechanicSkeleton />
            <MechanicSkeleton />
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
          <p className="text-gray-400 mb-6">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-6 py-3 bg-orange-500 hover:bg-orange-600 text-white font-medium rounded-lg transition-colors"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  // Empty state - no replays yet
  if (!stats || !stats.has_data) {
    return (
      <div className="p-6 lg:p-8">
        <div className="text-center py-16">
          <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-orange-500/20 flex items-center justify-center">
            <svg className="w-10 h-10 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">Welcome to rlcoach!</h2>
          <p className="text-gray-400 mb-8 max-w-md mx-auto">
            Upload your first replay to unlock detailed performance analytics,
            mechanic tracking, and personalized AI coaching.
          </p>
          <Link
            href="/replays"
            className="inline-flex items-center gap-2 px-6 py-3 bg-orange-500 hover:bg-orange-600 text-white font-medium rounded-lg transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            Upload Your First Replay
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8 space-y-8">
      {/* Hero Section */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <h1 className="text-2xl lg:text-3xl font-bold text-white">
            Your Performance
          </h1>
          <p className="text-gray-400 mt-1">
            Based on {stats.total_replays} {stats.total_replays === 1 ? 'replay' : 'replays'} analyzed
            {benchmarks?.has_data && (
              <span className="ml-2 text-orange-400">• Comparing to {benchmarks.rank_name}</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {stats.recent_trend === 'up' && (
            <span className="flex items-center gap-1 text-green-400 text-sm">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
              </svg>
              Improving
            </span>
          )}
          {stats.recent_trend === 'down' && (
            <span className="flex items-center gap-1 text-red-400 text-sm">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
              </svg>
              Needs work
            </span>
          )}
          {stats.recent_trend === 'stable' && (
            <span className="flex items-center gap-1 text-gray-400 text-sm">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14" />
              </svg>
              Stable
            </span>
          )}
        </div>
      </div>

      {/* Topline Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          label="Win Rate"
          value={stats.recent_win_rate !== null ? `${stats.recent_win_rate}%` : '--'}
          subtext="Last 20 games"
          large
        />
        <StatCard
          label="Avg Goals"
          value={stats.avg_goals !== null ? stats.avg_goals.toFixed(1) : '--'}
          subtext="per game"
          comparison={benchmarks?.comparisons?.goals_per_game}
        />
        <StatCard
          label="Avg Assists"
          value={stats.avg_assists !== null ? stats.avg_assists.toFixed(1) : '--'}
          subtext="per game"
          comparison={benchmarks?.comparisons?.assists_per_game}
        />
        <StatCard
          label="Avg Saves"
          value={stats.avg_saves !== null ? stats.avg_saves.toFixed(1) : '--'}
          subtext="per game"
          comparison={benchmarks?.comparisons?.saves_per_game}
        />
        <StatCard
          label="Avg Shots"
          value={stats.avg_shots !== null ? stats.avg_shots.toFixed(1) : '--'}
          subtext="per game"
          comparison={benchmarks?.comparisons?.shots_per_game}
        />
      </div>

      {/* Mechanics Breakdown */}
      {stats.top_mechanics.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-white">Mechanics Breakdown</h2>
            <Link
              href="/replays"
              className="text-sm text-orange-400 hover:text-orange-300 flex items-center gap-1"
            >
              View all replays
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {stats.top_mechanics.map((mechanic) => (
              <MechanicCard
                key={mechanic.name}
                name={mechanic.name}
                count={mechanic.count}
              />
            ))}
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Link
          href="/coach"
          className="bg-gradient-to-r from-orange-500/20 to-orange-600/20 border border-orange-500/30 rounded-xl p-6 hover:border-orange-500/50 transition-colors group"
        >
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-lg bg-orange-500/20 flex items-center justify-center">
              <svg className="w-6 h-6 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <div>
              <h3 className="font-semibold text-white group-hover:text-orange-400 transition-colors">
                AI Coach
              </h3>
              <p className="text-sm text-gray-400">Get personalized advice</p>
            </div>
          </div>
        </Link>

        <Link
          href="/trends"
          className="bg-gray-900/50 border border-gray-800 rounded-xl p-6 hover:border-gray-700 transition-colors group"
        >
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-lg bg-gray-800 flex items-center justify-center">
              <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
              </svg>
            </div>
            <div>
              <h3 className="font-semibold text-white group-hover:text-gray-200 transition-colors">
                View Trends
              </h3>
              <p className="text-sm text-gray-400">Track your progress</p>
            </div>
          </div>
        </Link>

        <Link
          href="/compare"
          className="bg-gray-900/50 border border-gray-800 rounded-xl p-6 hover:border-gray-700 transition-colors group"
        >
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-lg bg-gray-800 flex items-center justify-center">
              <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <div>
              <h3 className="font-semibold text-white group-hover:text-gray-200 transition-colors">
                Compare
              </h3>
              <p className="text-sm text-gray-400">vs your rank</p>
            </div>
          </div>
        </Link>
      </div>
    </div>
  );
}
