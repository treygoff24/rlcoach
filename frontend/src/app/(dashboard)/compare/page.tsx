// frontend/src/app/(dashboard)/compare/page.tsx
'use client';

import { useState } from 'react';

type CompareMode = 'rank' | 'self';

const mockRankData = {
  rank: 'Diamond II',
  sampleSize: 1247,
  metrics: [
    { name: 'Goals/Game', yours: 1.2, rankAvg: 0.9, percentile: 72 },
    { name: 'Saves/Game', yours: 1.4, rankAvg: 1.3, percentile: 58 },
    { name: 'Shots/Game', yours: 2.1, rankAvg: 1.8, percentile: 65 },
    { name: 'Win Rate', yours: 54, rankAvg: 50, percentile: 62 },
    { name: 'Boost/100', yours: 42, rankAvg: 38, percentile: 68 },
    { name: 'Avg Speed', yours: 1450, rankAvg: 1380, percentile: 71 },
  ],
};

const mockSelfData = {
  periods: ['This Week', 'Last Week'],
  metrics: [
    { name: 'Goals/Game', current: 1.2, previous: 1.0, change: 20 },
    { name: 'Saves/Game', current: 1.4, previous: 1.5, change: -7 },
    { name: 'Shots/Game', current: 2.1, previous: 1.9, change: 11 },
    { name: 'Win Rate', current: 54, previous: 48, change: 13 },
    { name: 'Boost/100', current: 42, previous: 40, change: 5 },
    { name: 'Avg Speed', current: 1450, previous: 1420, change: 2 },
  ],
};

function getPercentileColor(p: number) {
  if (p >= 80) return 'text-orange-400';
  if (p >= 60) return 'text-green-400';
  if (p >= 40) return 'text-yellow-400';
  return 'text-red-400';
}

export default function ComparePage() {
  const [mode, setMode] = useState<CompareMode>('rank');

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

      {mode === 'rank' && (
        <div className="space-y-6">
          {/* Rank Info */}
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-400">Comparing against</p>
                <p className="text-2xl font-bold text-white">{mockRankData.rank}</p>
              </div>
              <p className="text-sm text-gray-400">
                Based on {mockRankData.sampleSize.toLocaleString()} rlcoach users
              </p>
            </div>
          </div>

          {/* Metrics Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {mockRankData.metrics.map((m) => (
              <div key={m.name} className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
                <p className="text-sm text-gray-400 mb-3">{m.name}</p>
                <div className="flex items-end justify-between">
                  <div>
                    <p className="text-2xl font-bold text-white">
                      {typeof m.yours === 'number' && m.yours > 100 ? m.yours : m.yours}
                      {m.name === 'Win Rate' && '%'}
                    </p>
                    <p className="text-xs text-gray-500">
                      Rank avg: {m.rankAvg}{m.name === 'Win Rate' && '%'}
                    </p>
                  </div>
                  <div className="text-right">
                    <span className={`text-lg font-bold ${getPercentileColor(m.percentile)}`}>
                      Top {100 - m.percentile}%
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {mode === 'self' && (
        <div className="space-y-6">
          {/* Period Info */}
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
            <div className="flex items-center gap-4">
              <span className="text-xl font-bold text-white">{mockSelfData.periods[0]}</span>
              <span className="text-gray-500">vs</span>
              <span className="text-xl font-bold text-gray-400">{mockSelfData.periods[1]}</span>
            </div>
          </div>

          {/* Metrics Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {mockSelfData.metrics.map((m) => {
              const isPositive = m.change > 0;
              const isNeutral = m.change === 0;
              return (
                <div key={m.name} className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
                  <p className="text-sm text-gray-400 mb-3">{m.name}</p>
                  <div className="flex items-end justify-between">
                    <div>
                      <p className="text-2xl font-bold text-white">
                        {m.current}{m.name === 'Win Rate' && '%'}
                      </p>
                      <p className="text-xs text-gray-500">
                        Was: {m.previous}{m.name === 'Win Rate' && '%'}
                      </p>
                    </div>
                    <div className={`flex items-center gap-1 ${
                      isPositive ? 'text-green-400' : isNeutral ? 'text-gray-400' : 'text-red-400'
                    }`}>
                      {!isNeutral && (
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
                        {isPositive && '+'}{m.change}%
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
