// frontend/src/app/(dashboard)/replays/[id]/page.tsx
'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { formatMapName } from '@/lib/utils';

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

// API response types
interface PlayerStats {
  player_id: string;
  display_name: string;
  team: string;
  is_me: boolean;
  goals: number;
  assists: number;
  saves: number;
  shots: number;
  score: number;
  demos_inflicted: number;
  demos_taken: number;
  avg_boost: number | null;
  big_pads: number | null;
  small_pads: number | null;
  boost_stolen: number | null;
  time_zero_boost_pct: number | null;
  time_full_boost_pct: number | null;
  avg_speed_kph: number | null;
  time_supersonic_pct: number | null;
  time_offensive_third_pct: number | null;
  time_middle_third_pct: number | null;
  time_defensive_third_pct: number | null;
  behind_ball_pct: number | null;
  avg_distance_to_ball_m: number | null;
  wavedash_count: number | null;
  halfflip_count: number | null;
  speedflip_count: number | null;
  aerial_count: number | null;
}

interface ReplayData {
  id: string;
  filename: string;
  status: string;
  map_name: string | null;
  playlist: string | null;
  team_size: number | null;
  duration_seconds: number | null;
  played_at: string | null;
  result: string | null;
  my_score: number | null;
  opponent_score: number | null;
  overtime: boolean;
  players: PlayerStats[];
}

function formatDuration(seconds: number | null) {
  if (seconds == null) return '--:--';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function OverviewTab({ replay }: { replay: ReplayData }) {
  const myPlayer = replay.players.find((p) => p.is_me);
  const blueTeam = replay.players.filter((p) => p.team === 'blue');
  const orangeTeam = replay.players.filter((p) => p.team === 'orange');

  return (
    <div className="space-y-6">
      {/* Game Result */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
        <div className="flex items-center justify-between">
          <div className="text-center flex-1">
            <p className="text-sm text-blue-400 font-medium mb-2">Blue Team</p>
            <p className="text-4xl font-bold text-white">{replay.my_score ?? '-'}</p>
          </div>
          <div className="px-6">
            <p className="text-gray-500 text-lg">vs</p>
          </div>
          <div className="text-center flex-1">
            <p className="text-sm text-orange-400 font-medium mb-2">Orange Team</p>
            <p className="text-4xl font-bold text-white">{replay.opponent_score ?? '-'}</p>
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
          <caption className="sr-only">Game scoreboard showing player stats</caption>
          <thead>
            <tr className="border-b border-gray-800">
              <th scope="col" className="px-4 py-2 text-left text-xs font-medium text-gray-400">Player</th>
              <th scope="col" className="px-4 py-2 text-center text-xs font-medium text-gray-400">Score</th>
              <th scope="col" className="px-4 py-2 text-center text-xs font-medium text-gray-400">Goals</th>
              <th scope="col" className="px-4 py-2 text-center text-xs font-medium text-gray-400">Assists</th>
              <th scope="col" className="px-4 py-2 text-center text-xs font-medium text-gray-400">Saves</th>
              <th scope="col" className="px-4 py-2 text-center text-xs font-medium text-gray-400">Shots</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {replay.players.map((player) => (
              <tr key={player.player_id} className={player.is_me ? 'bg-orange-500/5' : ''}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2 h-2 rounded-full ${player.team === 'blue' ? 'bg-blue-500' : 'bg-orange-500'}`}
                      aria-hidden="true"
                    />
                    <span className={`font-medium ${player.is_me ? 'text-orange-400' : 'text-white'}`}>
                      {player.display_name}
                      {player.is_me && <span className="text-xs text-gray-500 ml-2">(you)</span>}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 text-center text-gray-300">{player.score}</td>
                <td className="px-4 py-3 text-center text-gray-300">{player.goals}</td>
                <td className="px-4 py-3 text-center text-gray-300">{player.assists}</td>
                <td className="px-4 py-3 text-center text-gray-300">{player.saves}</td>
                <td className="px-4 py-3 text-center text-gray-300">{player.shots}</td>
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
            <p className="text-3xl font-bold text-white">{myPlayer.goals}</p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
            <p className="text-sm text-gray-400">Saves</p>
            <p className="text-3xl font-bold text-white">{myPlayer.saves}</p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
            <p className="text-sm text-gray-400">Shot %</p>
            <p className="text-3xl font-bold text-white">
              {myPlayer.shots > 0
                ? Math.round((myPlayer.goals / myPlayer.shots) * 100)
                : 0}%
            </p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
            <p className="text-sm text-gray-400">Score</p>
            <p className="text-3xl font-bold text-white">{myPlayer.score}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function MechanicsTab({ replay }: { replay: ReplayData }) {
  const myPlayer = replay.players.find((p) => p.is_me);
  
  if (!myPlayer) {
    return <div className="text-gray-400 p-4">No player data available</div>;
  }

  const mechanics = [
    { name: 'Wave Dashes', count: myPlayer.wavedash_count ?? 0 },
    { name: 'Half Flips', count: myPlayer.halfflip_count ?? 0 },
    { name: 'Speed Flips', count: myPlayer.speedflip_count ?? 0 },
    { name: 'Aerials', count: myPlayer.aerial_count ?? 0 },
    { name: 'Demos Given', count: myPlayer.demos_inflicted },
    { name: 'Demos Taken', count: myPlayer.demos_taken },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
      {mechanics.map((m) => (
        <div key={m.name} className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">{m.name}</p>
          <p className="text-3xl font-bold text-white">{m.count}</p>
        </div>
      ))}
    </div>
  );
}

function BoostTab({ replay }: { replay: ReplayData }) {
  const myPlayer = replay.players.find((p) => p.is_me);
  
  if (!myPlayer) {
    return <div className="text-gray-400 p-4">No player data available</div>;
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Avg Boost</p>
          <p className="text-3xl font-bold text-white">{myPlayer.avg_boost?.toFixed(0) ?? '-'}</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Time Empty</p>
          <p className="text-3xl font-bold text-white">{myPlayer.time_zero_boost_pct?.toFixed(0) ?? '-'}%</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Time Full</p>
          <p className="text-3xl font-bold text-white">{myPlayer.time_full_boost_pct?.toFixed(0) ?? '-'}%</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Big Pads</p>
          <p className="text-3xl font-bold text-white">{myPlayer.big_pads ?? '-'}</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Small Pads</p>
          <p className="text-3xl font-bold text-white">{myPlayer.small_pads ?? '-'}</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Stolen</p>
          <p className="text-3xl font-bold text-orange-400">{myPlayer.boost_stolen?.toFixed(0) ?? '-'}</p>
        </div>
      </div>
    </div>
  );
}

function PositioningTab({ replay }: { replay: ReplayData }) {
  const myPlayer = replay.players.find((p) => p.is_me);
  
  if (!myPlayer) {
    return <div className="text-gray-400 p-4">No player data available</div>;
  }

  const defensive = myPlayer.time_defensive_third_pct ?? 0;
  const mid = myPlayer.time_middle_third_pct ?? 0;
  const offensive = myPlayer.time_offensive_third_pct ?? 0;

  return (
    <div className="space-y-6">
      {/* Third Splits */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
        <h3 className="font-medium text-white mb-4">Field Position</h3>
        <div className="flex h-8 rounded-lg overflow-hidden" role="img" aria-label={`Field position: ${defensive.toFixed(0)}% defensive, ${mid.toFixed(0)}% midfield, ${offensive.toFixed(0)}% offensive`}>
          <div
            className="bg-blue-500 flex items-center justify-center"
            style={{ width: `${defensive}%` }}
          >
            {defensive > 15 && <span className="text-xs font-medium text-white">{defensive.toFixed(0)}%</span>}
          </div>
          <div
            className="bg-gray-600 flex items-center justify-center"
            style={{ width: `${mid}%` }}
          >
            {mid > 15 && <span className="text-xs font-medium text-white">{mid.toFixed(0)}%</span>}
          </div>
          <div
            className="bg-orange-500 flex items-center justify-center"
            style={{ width: `${offensive}%` }}
          >
            {offensive > 15 && <span className="text-xs font-medium text-white">{offensive.toFixed(0)}%</span>}
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
          <p className="text-3xl font-bold text-white">
            {myPlayer.avg_distance_to_ball_m != null 
              ? `${(myPlayer.avg_distance_to_ball_m / 100).toFixed(0)}m`
              : '-'}
          </p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Time Behind Ball</p>
          <p className="text-3xl font-bold text-white">{myPlayer.behind_ball_pct?.toFixed(0) ?? '-'}%</p>
        </div>
      </div>
    </div>
  );
}

function TimelineTab({ replay }: { replay: ReplayData }) {
  return (
    <div className="space-y-4">
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
        <h3 className="font-medium text-white mb-4">Match Summary</h3>
        <div className="text-gray-400 text-sm space-y-1">
          <p>Final Score: {replay.my_score ?? 0} - {replay.opponent_score ?? 0}</p>
          <p>Duration: {formatDuration(replay.duration_seconds)}</p>
          {replay.overtime && <p className="text-orange-400">Went to Overtime</p>}
        </div>
      </div>
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
        <h3 className="font-medium text-white mb-4">Player Contributions</h3>
        <div className="space-y-3">
          {replay.players.map((p) => (
            <div key={p.player_id} className="flex items-center justify-between">
              <span className={p.is_me ? 'text-orange-400 font-medium' : 'text-gray-300'}>
                {p.display_name}
                {p.is_me && <span className="ml-2 text-xs text-orange-500">(you)</span>}
              </span>
              <span className="text-gray-400 text-sm">
                {p.goals}G / {p.assists}A / {p.saves}S / {p.shots} shots
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function DefenseTab({ replay }: { replay: ReplayData }) {
  const myPlayer = replay.players.find((p) => p.is_me);
  if (!myPlayer) {
    return <div className="text-gray-400 p-4">No player data available</div>;
  }
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Saves</p>
          <p className="text-3xl font-bold text-white">{myPlayer.saves}</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Defensive Third</p>
          <p className="text-3xl font-bold text-white">
            {myPlayer.time_defensive_third_pct != null ? `${myPlayer.time_defensive_third_pct.toFixed(0)}%` : '-'}
          </p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Behind Ball</p>
          <p className="text-3xl font-bold text-white">
            {myPlayer.behind_ball_pct != null ? `${myPlayer.behind_ball_pct.toFixed(0)}%` : '-'}
          </p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Demos Taken</p>
          <p className="text-3xl font-bold text-white">{myPlayer.demos_taken}</p>
        </div>
      </div>
    </div>
  );
}

function OffenseTab({ replay }: { replay: ReplayData }) {
  const myPlayer = replay.players.find((p) => p.is_me);
  if (!myPlayer) {
    return <div className="text-gray-400 p-4">No player data available</div>;
  }
  const shootingPct = myPlayer.shots > 0
    ? Math.round((myPlayer.goals / myPlayer.shots) * 100)
    : 0;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Goals</p>
          <p className="text-3xl font-bold text-white">{myPlayer.goals}</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Shots</p>
          <p className="text-3xl font-bold text-white">{myPlayer.shots}</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Shooting %</p>
          <p className="text-3xl font-bold text-white">{shootingPct}%</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Assists</p>
          <p className="text-3xl font-bold text-white">{myPlayer.assists}</p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Offensive Third</p>
          <p className="text-3xl font-bold text-white">
            {myPlayer.time_offensive_third_pct != null ? `${myPlayer.time_offensive_third_pct.toFixed(0)}%` : '-'}
          </p>
        </div>
        <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
          <p className="text-sm text-gray-400">Demos Given</p>
          <p className="text-3xl font-bold text-white">{myPlayer.demos_inflicted}</p>
        </div>
      </div>
    </div>
  );
}

export default function ReplayDetailPage() {
  const params = useParams();
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [replay, setReplay] = useState<ReplayData | null>(null);

  useEffect(() => {
    async function fetchReplay() {
      try {
        setLoading(true);
        setError(null);
        
        const response = await fetch(`/api/v1/replays/${params.id}/analysis`);
        
        if (!response.ok) {
          if (response.status === 401) {
            setError('Please sign in to view this replay');
            return;
          }
          if (response.status === 404) {
            setError('Replay not found');
            return;
          }
          throw new Error(`Failed to fetch replay: ${response.status}`);
        }
        
        const data: ReplayData = await response.json();
        setReplay(data);
      } catch (err) {
        console.error('Error fetching replay:', err);
        setError(err instanceof Error ? err.message : 'Failed to load replay');
      } finally {
        setLoading(false);
      }
    }
    
    if (params.id) {
      fetchReplay();
    }
  }, [params.id]);

  // Arrow key navigation for tabs
  const handleTabKeyDown = useCallback((e: React.KeyboardEvent, currentIndex: number) => {
    let newIndex = currentIndex;

    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      newIndex = currentIndex === 0 ? tabs.length - 1 : currentIndex - 1;
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      newIndex = currentIndex === tabs.length - 1 ? 0 : currentIndex + 1;
    } else if (e.key === 'Home') {
      e.preventDefault();
      newIndex = 0;
    } else if (e.key === 'End') {
      e.preventDefault();
      newIndex = tabs.length - 1;
    } else {
      return;
    }

    setActiveTab(tabs[newIndex].id);
    // Focus the new tab button
    const tabButton = document.getElementById(`tab-${tabs[newIndex].id}`);
    tabButton?.focus();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]" role="status" aria-label="Loading replay">
        <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full" aria-hidden="true" />
        <span className="sr-only">Loading replay data...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 lg:p-8">
        <Link
          href="/replays"
          className="inline-flex items-center gap-1 text-gray-400 hover:text-white mb-4 text-sm"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Replays
        </Link>
        <div className="card p-8 text-center">
          <p className="text-white/70">{error}</p>
        </div>
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

  const activeTabIndex = tabs.findIndex(t => t.id === activeTab);

  return (
    <div className="p-6 lg:p-8">
      {/* Header */}
      <div className="mb-6">
        <Link
          href="/replays"
          className="inline-flex items-center gap-1 text-gray-400 hover:text-white mb-4 text-sm focus:outline-none focus:text-orange-400 focus:underline"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Replays
        </Link>

        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white">
              {formatMapName(replay.map_name)} - {replay.played_at
                ? new Date(replay.played_at).toLocaleDateString('en-US', {
                    weekday: 'short',
                    month: 'short',
                    day: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit',
                  })
                : 'Unknown Date'}
            </h1>
            <div className="flex items-center gap-3 mt-2 text-sm text-gray-400">
              <span>{formatMapName(replay.map_name)}</span>
              <span aria-hidden="true">•</span>
              <span>{replay.playlist || 'Unknown Playlist'}</span>
              <span aria-hidden="true">•</span>
              <span>{formatDuration(replay.duration_seconds)}</span>
            </div>
          </div>
          <div className={`px-4 py-2 rounded-lg font-semibold ${
            replay.result === 'WIN'
              ? 'bg-green-500/20 text-green-400'
              : replay.result === 'LOSS'
              ? 'bg-red-500/20 text-red-400'
              : 'bg-gray-500/20 text-gray-400'
          }`}>
            {replay.result === 'WIN' ? 'Victory' : replay.result === 'LOSS' ? 'Defeat' : 'Unknown'}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-800 mb-6">
        <div className="relative">
          <div
            className="flex gap-1 overflow-x-auto scrollbar-hide"
            role="tablist"
            aria-label="Replay analysis tabs"
          >
            {tabs.map((tab, index) => (
              <button
                key={tab.id}
                id={`tab-${tab.id}`}
                role="tab"
                aria-selected={activeTab === tab.id}
                aria-controls={`panel-${tab.id}`}
                tabIndex={activeTab === tab.id ? 0 : -1}
                onClick={() => setActiveTab(tab.id)}
                onKeyDown={(e) => handleTabKeyDown(e, index)}
                className={`px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-inset ${
                  activeTab === tab.id
                    ? 'text-orange-400 border-b-2 border-orange-400'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          {/* Scroll indicator for mobile */}
          <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-gray-950 pointer-events-none sm:hidden" aria-hidden="true" />
        </div>
      </div>

      {/* Tab Panels */}
      <div
        id={`panel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`tab-${activeTab}`}
        tabIndex={0}
      >
        {activeTab === 'overview' && <OverviewTab replay={replay} />}
        {activeTab === 'mechanics' && <MechanicsTab replay={replay} />}
        {activeTab === 'boost' && <BoostTab replay={replay} />}
        {activeTab === 'positioning' && <PositioningTab replay={replay} />}
        {activeTab === 'timeline' && <TimelineTab replay={replay} />}
        {activeTab === 'defense' && <DefenseTab replay={replay} />}
        {activeTab === 'offense' && <OffenseTab replay={replay} />}
      </div>
    </div>
  );
}
