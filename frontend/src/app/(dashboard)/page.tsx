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
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-victory">
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
        </svg>
        Above rank
      </span>
    );
  }
  if (comparison === 'below') {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-defeat">
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
        </svg>
        Below rank
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-white/50">
      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 12h14" />
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
  accent = 'default',
  delay = 0,
}: {
  label: string;
  value: string | number;
  subtext?: string;
  large?: boolean;
  comparison?: StatComparison;
  accent?: 'default' | 'fire' | 'boost' | 'victory';
  delay?: number;
}) {
  const accentStyles = {
    default: 'from-white/5 to-transparent',
    fire: 'from-fire/10 to-transparent',
    boost: 'from-boost/10 to-transparent',
    victory: 'from-victory/10 to-transparent',
  };

  return (
    <div
      className={`
        group relative card card-hover speed-lines overflow-hidden
        animate-slide-up opacity-0 [animation-fill-mode:forwards]
      `}
      style={{ animationDelay: `${delay}ms` }}
    >
      {/* Accent gradient */}
      <div className={`absolute inset-0 bg-gradient-to-br ${accentStyles[accent]} opacity-0 group-hover:opacity-100 transition-opacity duration-300`} />

      {/* Content */}
      <div className="relative">
        <p className="stat-label mb-2">{label}</p>
        <p className={`font-display ${large ? 'text-stat-xl' : 'text-stat-lg'} text-white tracking-wide`}>
          {value}
        </p>
        <div className="flex items-center justify-between mt-3">
          {subtext && <p className="text-xs text-white/40">{subtext}</p>}
          {comparison && <ComparisonBadge comparison={comparison.comparison} />}
        </div>
      </div>

      {/* Hover glow line */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-boost/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
    </div>
  );
}

function MechanicCard({
  name,
  count,
  delay = 0,
}: {
  name: string;
  count: number;
  delay?: number;
}) {
  return (
    <div
      className="group relative card card-hover overflow-hidden animate-slide-up opacity-0 [animation-fill-mode:forwards]"
      style={{ animationDelay: `${delay}ms` }}
    >
      {/* Background pattern */}
      <div className="absolute inset-0 bg-grid-pattern bg-grid opacity-30" />

      {/* Mechanic icon glow */}
      <div className="absolute -top-10 -right-10 w-32 h-32 bg-gradient-radial from-plasma/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />

      {/* Content */}
      <div className="relative">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-plasma animate-pulse" />
            <h3 className="font-semibold text-white">{name}</h3>
          </div>
          <span className="badge badge-boost text-[10px]">TRACKED</span>
        </div>
        <div className="flex items-end justify-between">
          <div>
            <p className="font-display text-stat-lg text-white">{count}</p>
            <p className="text-xs text-white/40 mt-1">total executions</p>
          </div>
          {/* Mini trend sparkline placeholder */}
          <div className="flex items-end gap-0.5 h-8">
            {[40, 60, 45, 80, 65, 90, 75].map((h, i) => (
              <div
                key={i}
                className="w-1 bg-gradient-to-t from-plasma/40 to-plasma rounded-full transition-all duration-300 group-hover:from-plasma/60 group-hover:to-plasma"
                style={{ height: `${h}%` }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function QuickActionCard({
  href,
  icon,
  title,
  description,
  variant = 'default',
  delay = 0,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  description: string;
  variant?: 'default' | 'primary';
  delay?: number;
}) {
  const isPrimary = variant === 'primary';

  return (
    <Link
      href={href}
      className={`
        group relative block overflow-hidden rounded-2xl p-6 transition-all duration-300
        animate-slide-up opacity-0 [animation-fill-mode:forwards]
        ${isPrimary
          ? 'bg-gradient-to-br from-fire/20 via-fire/10 to-transparent border border-fire/30 hover:border-fire/50'
          : 'card card-hover'
        }
      `}
      style={{ animationDelay: `${delay}ms` }}
    >
      {/* Animated background glow for primary */}
      {isPrimary && (
        <div className="absolute -top-20 -right-20 w-40 h-40 bg-gradient-radial from-fire/30 to-transparent opacity-50 group-hover:opacity-80 transition-opacity duration-300 animate-pulse-slow" />
      )}

      {/* Content */}
      <div className="relative flex items-center gap-4">
        <div className={`
          w-14 h-14 rounded-2xl flex items-center justify-center transition-all duration-300
          ${isPrimary
            ? 'bg-fire/20 group-hover:bg-fire/30 group-hover:shadow-glow-fire'
            : 'bg-white/5 group-hover:bg-white/10'
          }
        `}>
          <span className={`transition-colors duration-200 ${isPrimary ? 'text-fire' : 'text-white/60 group-hover:text-white'}`}>
            {icon}
          </span>
        </div>
        <div className="flex-1">
          <h3 className={`font-semibold transition-colors duration-200 ${isPrimary ? 'text-white group-hover:text-fire' : 'text-white group-hover:text-white'}`}>
            {title}
          </h3>
          <p className="text-sm text-white/50">{description}</p>
        </div>
        <svg className="w-5 h-5 text-white/50 group-hover:text-white/60 transition-all duration-200 group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </div>
    </Link>
  );
}

function StatSkeleton({ large = false }: { large?: boolean }) {
  return (
    <div className="card animate-pulse">
      <div className="h-3 w-16 bg-white/10 rounded mb-3" />
      <div className={`${large ? 'h-14 w-28' : 'h-12 w-20'} bg-white/10 rounded`} />
      <div className="h-3 w-20 bg-white/5 rounded mt-4" />
    </div>
  );
}

function MechanicSkeleton() {
  return (
    <div className="card animate-pulse">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-2 h-2 rounded-full bg-white/10" />
        <div className="h-4 w-24 bg-white/10 rounded" />
      </div>
      <div className="h-12 w-16 bg-white/10 rounded" />
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
          <div className="h-10 w-64 bg-white/10 rounded-lg mb-3" />
          <div className="h-4 w-40 bg-white/5 rounded" />
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
          <div className="h-6 w-48 bg-white/10 rounded mb-4" />
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
        <div className="text-center py-20">
          <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-defeat/20 flex items-center justify-center animate-pulse-slow">
            <svg className="w-10 h-10 text-defeat" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-2xl font-display text-white mb-3">SOMETHING WENT WRONG</h2>
          <p className="text-white/50 mb-8 max-w-md mx-auto">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="btn-primary"
          >
            <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
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
        <div className="text-center py-20">
          {/* Animated upload icon */}
          <div className="relative w-24 h-24 mx-auto mb-8">
            <div className="absolute inset-0 rounded-3xl bg-gradient-to-br from-fire/30 to-boost/30 animate-pulse-slow" />
            <div className="absolute inset-1 rounded-3xl bg-void flex items-center justify-center">
              <svg className="w-12 h-12 text-fire animate-float" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>
            {/* Orbiting dots */}
            <div className="absolute inset-0 animate-spin-slow">
              <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1 w-2 h-2 rounded-full bg-boost" />
            </div>
          </div>

          <h2 className="text-3xl font-display text-white mb-3 tracking-wide">WELCOME TO RLCOACH</h2>
          <p className="text-white/50 mb-10 max-w-lg mx-auto leading-relaxed">
            Upload your first replay to unlock detailed performance analytics,
            mechanic tracking, and personalized AI coaching.
          </p>
          <Link
            href="/replays"
            className="btn-primary inline-flex items-center gap-3 text-lg px-8 py-4"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            Upload Your First Replay
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8 space-y-10">
      {/* Hero Section */}
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4 animate-fade-in">
        <div>
          <h1 className="text-4xl lg:text-5xl font-display text-white tracking-wide mb-2">
            YOUR PERFORMANCE
          </h1>
          <div className="flex items-center gap-3 text-white/50">
            <span>Based on {stats.total_replays} {stats.total_replays === 1 ? 'replay' : 'replays'} analyzed</span>
            {benchmarks?.has_data && (
              <>
                <span className="w-1 h-1 rounded-full bg-white/30" />
                <span className="text-fire">Comparing to {benchmarks.rank_name}</span>
              </>
            )}
          </div>
        </div>

        {/* Trend indicator */}
        <div className="flex items-center gap-3">
          {stats.recent_trend === 'up' && (
            <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-victory/10 border border-victory/20">
              <svg className="w-5 h-5 text-victory" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
              <span className="font-semibold text-victory">Improving</span>
            </div>
          )}
          {stats.recent_trend === 'down' && (
            <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-defeat/10 border border-defeat/20">
              <svg className="w-5 h-5 text-defeat" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 17h8m0 0v-8m0 8l-8-8-4 4-6-6" />
              </svg>
              <span className="font-semibold text-defeat">Needs Work</span>
            </div>
          )}
          {stats.recent_trend === 'stable' && (
            <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 border border-white/10">
              <svg className="w-5 h-5 text-white/60" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14" />
              </svg>
              <span className="font-semibold text-white/60">Stable</span>
            </div>
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
          accent="fire"
          delay={100}
        />
        <StatCard
          label="Avg Goals"
          value={stats.avg_goals !== null ? stats.avg_goals.toFixed(1) : '--'}
          subtext="per game"
          comparison={benchmarks?.comparisons?.goals_per_game}
          delay={150}
        />
        <StatCard
          label="Avg Assists"
          value={stats.avg_assists !== null ? stats.avg_assists.toFixed(1) : '--'}
          subtext="per game"
          comparison={benchmarks?.comparisons?.assists_per_game}
          delay={200}
        />
        <StatCard
          label="Avg Saves"
          value={stats.avg_saves !== null ? stats.avg_saves.toFixed(1) : '--'}
          subtext="per game"
          comparison={benchmarks?.comparisons?.saves_per_game}
          delay={250}
        />
        <StatCard
          label="Avg Shots"
          value={stats.avg_shots !== null ? stats.avg_shots.toFixed(1) : '--'}
          subtext="per game"
          comparison={benchmarks?.comparisons?.shots_per_game}
          delay={300}
        />
      </div>

      {/* Mechanics Breakdown */}
      {stats.top_mechanics.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div className="w-1 h-8 rounded-full bg-gradient-to-b from-plasma to-plasma/30" />
              <h2 className="text-2xl font-display text-white tracking-wide">MECHANICS BREAKDOWN</h2>
            </div>
            <Link
              href="/replays"
              className="flex items-center gap-2 text-sm font-medium text-white/50 hover:text-white transition-colors group"
            >
              View all replays
              <svg className="w-4 h-4 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {stats.top_mechanics.map((mechanic, index) => (
              <MechanicCard
                key={mechanic.name}
                name={mechanic.name}
                count={mechanic.count}
                delay={400 + index * 100}
              />
            ))}
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div>
        <div className="flex items-center gap-3 mb-6">
          <div className="w-1 h-8 rounded-full bg-gradient-to-b from-boost to-boost/30" />
          <h2 className="text-2xl font-display text-white tracking-wide">QUICK ACTIONS</h2>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <QuickActionCard
            href="/coach"
            icon={
              <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            }
            title="AI Coach"
            description="Get personalized advice and training drills"
            variant="primary"
            delay={600}
          />
          <QuickActionCard
            href="/trends"
            icon={
              <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
              </svg>
            }
            title="View Trends"
            description="Track your progress over time"
            delay={700}
          />
          <QuickActionCard
            href="/compare"
            icon={
              <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            }
            title="Compare"
            description="See how you stack up vs your rank"
            delay={800}
          />
        </div>
      </div>
    </div>
  );
}
