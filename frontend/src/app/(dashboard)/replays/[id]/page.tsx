// frontend/src/app/(dashboard)/replays/[id]/page.tsx
'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';

type TabId = 'overview' | 'mechanics' | 'boost' | 'positioning' | 'timeline' | 'defense' | 'offense';

const tabs: Array<{ id: TabId; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'mechanics', label: 'Mechanics' },
  { id: 'boost', label: 'Boost' },
  { id: 'positioning', label: 'Positioning' },
  { id: 'timeline', label: 'Timeline' },
  { id: 'defense', label: 'Defense' },
  { id: 'offense', label: 'Offense' },
];

// Mock replay data
const mockReplay = {
  id: '1',
  filename: 'ranked_1v1_neo.replay',
  map_name: 'Neo Tokyo',
  playlist: 'Ranked Duels',
  team_size: 1,
  duration_seconds: 312,
  played_at: '2026-01-03T14:30:00Z',
  result: 'win' as const,
  score: { blue: 5, orange: 3 },
  overtime: false,
  players: [
    {
      id: 'p1',
      name: 'fastbutstupid',
      team: 'blue' as const,
      is_me: true,
      stats: { goals: 3, assists: 0, saves: 2, shots: 5, score: 485 },
    },
    {
      id: 'p2',
      name: 'OpponentPlayer',
      team: 'orange' as const,
      is_me: false,
      stats: { goals: 3, assists: 0, saves: 1, shots: 4, score: 320 },
    },
  ],
  mechanics: {
    flip_resets: 2,
    ceiling_shots: 1,
    wave_dashes: 8,
    fast_aerials: 12,
    air_dribbles: 0,
    double_touches: 1,
    speed_flips: 3,
    half_flips: 5,
  },
  boost: {
    avg_amount: 45,
    time_empty_pct: 12,
    time_full_pct: 8,
    big_pads: 14,
    small_pads: 32,
    stolen: 4,
  },
  positioning: {
    third_splits: { defensive: 35, mid: 40, offensive: 25 },
    avg_distance_to_ball: 2100,
    time_behind_ball_pct: 62,
  },
};

function formatDuration(seconds: number) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function OverviewTab({ replay }: { replay: typeof mockReplay }) {
  const myPlayer = replay.players.find((p) => p.is_me);

  return (
    <div className="space-y-6">
      {/* Game Result */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
        <div className="flex items-center justify-between">
          <div className="text-center flex-1">
            <p className="text-sm text-blue-400 font-medium mb-2">Blue Team</p>
            <p className="text-4xl font-bold text-white">{replay.score.blue}</p>
          </div>
          <div className="px-6">
            <p className="text-gray-500 text-lg">vs</p>
          </div>
          <div className="text-center flex-1">
            <p className="text-sm text-orange-400 font-medium mb-2">Orange Team</p>
            <p className="text-4xl font-bold text-white">{replay.score.orange}</p>
          </div>
        </div>
        {replay.overtime && (
          <p className="text-center text-gray-400 mt-4">Overtime</p>
        )}
      </div>

      {/* Player Stats */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800">
          <h3 className="font-medium text-white">Scoreboard</h3>
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="px-4 py-2 text-left text-xs font-medium text-gray-400">Player</th>
              <th className="px-4 py-2 text-center text-xs font-medium text-gray-400">Score</th>
              <th className="px-4 py-2 text-center text-xs font-medium text-gray-400">Goals</th>
              <th className="px-4 py-2 text-center text-xs font-medium text-gray-400">Assists</th>
              <th className="px-4 py-2 text-center text-xs font-medium text-gray-400">Saves</th>
              <th className="px-4 py-2 text-center text-xs font-medium text-gray-400">Shots</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {replay.players.map((player) => (
              <tr key={player.id} className={player.is_me ? 'bg-orange-500/5' : ''}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${player.team === 'blue' ? 'bg-blue-500' : 'bg-orange-500'}`} />
                    <span className={`font-medium ${player.is_me ? 'text-orange-400' : 'text-white'}`}>
                      {player.name}
                      {player.is_me && <span className="text-xs text-gray-500 ml-2">(you)</span>}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 text-center text-gray-300">{player.stats.score}</td>
                <td className="px-4 py-3 text-center text-gray-300">{player.stats.goals}</td>
                <td className="px-4 py-3 text-center text-gray-300">{player.stats.assists}</td>
                <td className="px-4 py-3 text-center text-gray-300">{player.stats.saves}</td>
                <td className="px-4 py-3 text-center text-gray-300">{player.stats.shots}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* My Highlights */}
      {myPlayer && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
            <p className="text-sm text-gray-400">Goals</p>
            <p className="text-3xl font-bold text-white">{myPlayer.stats.goals}</p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
            <p className="text-sm text-gray-400">Saves</p>
            <p className="text-3xl font-bold text-white">{myPlayer.stats.saves}</p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
            <p className="text-sm text-gray-400">Shot %</p>
            <p className="text-3xl font-bold text-white">
              {myPlayer.stats.shots > 0
                ? Math.round((myPlayer.stats.goals / myPlayer.stats.shots) * 100)
                : 0}%
            </p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
            <p className="text-sm text-gray-400">Score</p>
            <p className="text-3xl font-bold text-white">{myPlayer.stats.score}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function MechanicsTab({ replay }: { replay: typeof mockReplay }) {
  const mechanics = [
    { name: 'Flip Resets', count: replay.mechanics.flip_resets },
    { name: 'Ceiling Shots', count: replay.mechanics.ceiling_shots },
    { name: 'Wave Dashes', count: replay.mechanics.wave_dashes },
    { name: 'Fast Aerials', count: replay.mechanics.fast_aerials },
    { name: 'Air Dribbles', count: replay.mechanics.air_dribbles },
    { name: 'Double Touches', count: replay.mechanics.double_touches },
    { name: 'Speed Flips', count: replay.mechanics.speed_flips },
    { name: 'Half Flips', count: replay.mechanics.half_flips },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {mechanics.map((m) => (
        <div key={m.name} className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">{m.name}</p>
          <p className="text-3xl font-bold text-white">{m.count}</p>
        </div>
      ))}
    </div>
  );
}

function BoostTab({ replay }: { replay: typeof mockReplay }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Avg Boost</p>
          <p className="text-3xl font-bold text-white">{replay.boost.avg_amount}</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Time Empty</p>
          <p className="text-3xl font-bold text-white">{replay.boost.time_empty_pct}%</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Time Full</p>
          <p className="text-3xl font-bold text-white">{replay.boost.time_full_pct}%</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Big Pads</p>
          <p className="text-3xl font-bold text-white">{replay.boost.big_pads}</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Small Pads</p>
          <p className="text-3xl font-bold text-white">{replay.boost.small_pads}</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Stolen</p>
          <p className="text-3xl font-bold text-orange-400">{replay.boost.stolen}</p>
        </div>
      </div>
    </div>
  );
}

function PositioningTab({ replay }: { replay: typeof mockReplay }) {
  const { third_splits } = replay.positioning;

  return (
    <div className="space-y-6">
      {/* Third Splits */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
        <h3 className="font-medium text-white mb-4">Field Position</h3>
        <div className="flex h-8 rounded-lg overflow-hidden">
          <div
            className="bg-blue-500 flex items-center justify-center"
            style={{ width: `${third_splits.defensive}%` }}
          >
            <span className="text-xs font-medium text-white">{third_splits.defensive}%</span>
          </div>
          <div
            className="bg-gray-600 flex items-center justify-center"
            style={{ width: `${third_splits.mid}%` }}
          >
            <span className="text-xs font-medium text-white">{third_splits.mid}%</span>
          </div>
          <div
            className="bg-orange-500 flex items-center justify-center"
            style={{ width: `${third_splits.offensive}%` }}
          >
            <span className="text-xs font-medium text-white">{third_splits.offensive}%</span>
          </div>
        </div>
        <div className="flex justify-between mt-2 text-xs text-gray-400">
          <span>Defensive</span>
          <span>Midfield</span>
          <span>Offensive</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Avg Distance to Ball</p>
          <p className="text-3xl font-bold text-white">{(replay.positioning.avg_distance_to_ball / 100).toFixed(0)}m</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Time Behind Ball</p>
          <p className="text-3xl font-bold text-white">{replay.positioning.time_behind_ball_pct}%</p>
        </div>
      </div>
    </div>
  );
}

function PlaceholderTab({ name }: { name: string }) {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="text-center">
        <p className="text-gray-400">{name} visualization coming soon</p>
      </div>
    </div>
  );
}

export default function ReplayDetailPage() {
  const params = useParams();
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [loading, setLoading] = useState(true);
  const [replay, setReplay] = useState<typeof mockReplay | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setReplay(mockReplay);
      setLoading(false);
    }, 300);
    return () => clearTimeout(timer);
  }, [params.id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!replay) {
    return (
      <div className="p-6 lg:p-8">
        <p className="text-gray-400">Replay not found</p>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8">
      {/* Header */}
      <div className="mb-6">
        <Link
          href="/dashboard/replays"
          className="inline-flex items-center gap-1 text-gray-400 hover:text-white mb-4 text-sm"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Replays
        </Link>

        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white">{replay.filename}</h1>
            <div className="flex items-center gap-3 mt-2 text-sm text-gray-400">
              <span>{replay.map_name}</span>
              <span>•</span>
              <span>{replay.playlist}</span>
              <span>•</span>
              <span>{formatDuration(replay.duration_seconds)}</span>
            </div>
          </div>
          <div className={`px-4 py-2 rounded-lg font-semibold ${
            replay.result === 'win'
              ? 'bg-green-500/20 text-green-400'
              : 'bg-red-500/20 text-red-400'
          }`}>
            {replay.result === 'win' ? 'Victory' : 'Defeat'}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-800 mb-6">
        <div className="flex gap-1 overflow-x-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors ${
                activeTab === tab.id
                  ? 'text-orange-400 border-b-2 border-orange-400'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && <OverviewTab replay={replay} />}
      {activeTab === 'mechanics' && <MechanicsTab replay={replay} />}
      {activeTab === 'boost' && <BoostTab replay={replay} />}
      {activeTab === 'positioning' && <PositioningTab replay={replay} />}
      {activeTab === 'timeline' && <PlaceholderTab name="Timeline" />}
      {activeTab === 'defense' && <PlaceholderTab name="Defense" />}
      {activeTab === 'offense' && <PlaceholderTab name="Offense" />}
    </div>
  );
}
