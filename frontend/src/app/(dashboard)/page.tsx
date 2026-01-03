// frontend/src/app/(dashboard)/page.tsx
'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';

interface DashboardStats {
  totalReplays: number;
  recentWinRate: number;
  avgGoals: number;
  avgAssists: number;
  avgSaves: number;
  avgShots: number;
  topMechanics: Array<{
    name: string;
    count: number;
    percentile: number;
  }>;
  recentTrend: 'up' | 'down' | 'stable';
}

// Mock data for now - will be replaced with API call
const mockStats: DashboardStats = {
  totalReplays: 247,
  recentWinRate: 54.3,
  avgGoals: 1.2,
  avgAssists: 0.8,
  avgSaves: 1.4,
  avgShots: 2.1,
  topMechanics: [
    { name: 'Flip Resets', count: 47, percentile: 97 },
    { name: 'Ceiling Shots', count: 23, percentile: 89 },
    { name: 'Wave Dashes', count: 156, percentile: 82 },
    { name: 'Fast Aerials', count: 312, percentile: 75 },
    { name: 'Air Dribbles', count: 18, percentile: 71 },
    { name: 'Double Touches', count: 34, percentile: 68 },
  ],
  recentTrend: 'up',
};

function StatCard({
  label,
  value,
  subtext,
  large = false,
}: {
  label: string;
  value: string | number;
  subtext?: string;
  large?: boolean;
}) {
  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
      <p className="text-sm text-gray-400 mb-1">{label}</p>
      <p className={`font-bold ${large ? 'text-3xl' : 'text-2xl'} text-white`}>
        {value}
      </p>
      {subtext && <p className="text-xs text-gray-500 mt-1">{subtext}</p>}
    </div>
  );
}

function MechanicCard({
  name,
  count,
  percentile,
}: {
  name: string;
  count: number;
  percentile: number;
}) {
  const getPercentileColor = (p: number) => {
    if (p >= 90) return 'text-orange-400 bg-orange-500/20';
    if (p >= 75) return 'text-green-400 bg-green-500/20';
    if (p >= 50) return 'text-blue-400 bg-blue-500/20';
    return 'text-gray-400 bg-gray-500/20';
  };

  const getRankLabel = (p: number) => {
    if (p >= 99) return 'SSL';
    if (p >= 95) return 'GC';
    if (p >= 85) return 'Champ';
    if (p >= 70) return 'Diamond';
    if (p >= 50) return 'Plat';
    return 'Gold';
  };

  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <h3 className="font-medium text-white">{name}</h3>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${getPercentileColor(percentile)}`}>
          Top {100 - percentile}%
        </span>
      </div>
      <div className="flex items-end justify-between">
        <div>
          <p className="text-3xl font-bold text-white">{count}</p>
          <p className="text-sm text-gray-400">total</p>
        </div>
        <div className="text-right">
          <p className="text-sm text-gray-400">Avg rank:</p>
          <p className="text-lg font-semibold text-orange-400">{getRankLabel(percentile)}</p>
        </div>
      </div>
    </div>
  );
}

export default function DashboardHome() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Simulate API call
    const timer = setTimeout(() => {
      setStats(mockStats);
      setLoading(false);
    }, 500);
    return () => clearTimeout(timer);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="p-6 lg:p-8">
        <div className="text-center py-16">
          <h2 className="text-2xl font-bold text-white mb-4">Welcome to rlcoach!</h2>
          <p className="text-gray-400 mb-6">Upload your first replay to get started</p>
          <button className="px-6 py-3 bg-orange-500 hover:bg-orange-600 text-white font-medium rounded-lg transition-colors">
            Upload Replays
          </button>
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
            Based on {stats.totalReplays} replays analyzed
          </p>
        </div>
        <div className="flex items-center gap-2">
          {stats.recentTrend === 'up' && (
            <span className="flex items-center gap-1 text-green-400 text-sm">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
              </svg>
              Improving
            </span>
          )}
          {stats.recentTrend === 'down' && (
            <span className="flex items-center gap-1 text-red-400 text-sm">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
              </svg>
              Needs work
            </span>
          )}
        </div>
      </div>

      {/* Topline Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          label="Win Rate"
          value={`${stats.recentWinRate}%`}
          subtext="Last 20 games"
          large
        />
        <StatCard label="Avg Goals" value={stats.avgGoals.toFixed(1)} subtext="per game" />
        <StatCard label="Avg Assists" value={stats.avgAssists.toFixed(1)} subtext="per game" />
        <StatCard label="Avg Saves" value={stats.avgSaves.toFixed(1)} subtext="per game" />
        <StatCard label="Avg Shots" value={stats.avgShots.toFixed(1)} subtext="per game" />
      </div>

      {/* Mechanics Breakdown */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-white">Mechanics Breakdown</h2>
          <Link
            href="/dashboard/replays"
            className="text-sm text-orange-400 hover:text-orange-300 flex items-center gap-1"
          >
            View all replays
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </Link>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {stats.topMechanics.map((mechanic) => (
            <MechanicCard
              key={mechanic.name}
              name={mechanic.name}
              count={mechanic.count}
              percentile={mechanic.percentile}
            />
          ))}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Link
          href="/dashboard/coach"
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
          href="/dashboard/trends"
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
          href="/dashboard/compare"
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
