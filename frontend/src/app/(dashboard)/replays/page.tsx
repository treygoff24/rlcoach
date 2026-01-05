// frontend/src/app/(dashboard)/replays/page.tsx
'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';

interface Replay {
  id: string;
  filename: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  played_at: string | null;
  map_name: string | null;
  playlist: string | null;
  team_size: number | null;
  result: 'win' | 'loss' | 'unknown';
  score: string;
  created_at: string;
}

// Mock data
const mockReplays: Replay[] = [
  { id: '1', filename: 'ranked_1v1_neo.replay', status: 'completed', played_at: '2026-01-03T14:30:00Z', map_name: 'Neo Tokyo', playlist: 'Ranked Duels', team_size: 1, result: 'win', score: '5 - 3', created_at: '2026-01-03T14:35:00Z' },
  { id: '2', filename: 'ranked_2v2_mannfield.replay', status: 'completed', played_at: '2026-01-03T14:15:00Z', map_name: 'Mannfield', playlist: 'Ranked Doubles', team_size: 2, result: 'loss', score: '2 - 4', created_at: '2026-01-03T14:20:00Z' },
  { id: '3', filename: 'ranked_3v3_beckwith.replay', status: 'completed', played_at: '2026-01-03T14:00:00Z', map_name: 'Beckwith Park', playlist: 'Ranked Standard', team_size: 3, result: 'win', score: '3 - 1', created_at: '2026-01-03T14:05:00Z' },
  { id: '4', filename: 'ranked_2v2_dfh.replay', status: 'processing', played_at: null, map_name: null, playlist: null, team_size: null, result: 'unknown', score: '-', created_at: '2026-01-03T15:00:00Z' },
  { id: '5', filename: 'ranked_3v3_aquadome.replay', status: 'completed', played_at: '2026-01-03T13:45:00Z', map_name: 'AquaDome', playlist: 'Ranked Standard', team_size: 3, result: 'win', score: '6 - 2', created_at: '2026-01-03T13:50:00Z' },
];

function formatDate(dateStr: string) {
  const date = new Date(dateStr);
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}

function StatusBadge({ status }: { status: Replay['status'] }) {
  const styles = {
    completed: 'bg-green-500/20 text-green-400',
    processing: 'bg-yellow-500/20 text-yellow-400',
    pending: 'bg-gray-500/20 text-gray-400',
    failed: 'bg-red-500/20 text-red-400',
  };

  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${styles[status]}`}>
      {status}
    </span>
  );
}

function ResultBadge({ result }: { result: Replay['result'] }) {
  if (result === 'unknown') return null;
  const isWin = result === 'win';
  return (
    <span className={`text-xs font-bold px-2 py-0.5 rounded ${isWin ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
      {isWin ? 'W' : 'L'}
    </span>
  );
}

export default function ReplaysPage() {
  const [replays, setReplays] = useState<Replay[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'completed' | 'processing'>('all');

  useEffect(() => {
    const timer = setTimeout(() => {
      setReplays(mockReplays);
      setLoading(false);
    }, 300);
    return () => clearTimeout(timer);
  }, []);

  const filteredReplays = replays.filter((replay) => {
    if (filter === 'all') return true;
    if (filter === 'completed') return replay.status === 'completed';
    if (filter === 'processing') return replay.status === 'processing' || replay.status === 'pending';
    return true;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]" role="status" aria-label="Loading replays">
        <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full" aria-hidden="true" />
        <span className="sr-only">Loading replays...</span>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Replays</h1>
          <p className="text-gray-400 mt-1">{replays.length} replays uploaded</p>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2" role="group" aria-label="Filter replays">
          {(['all', 'completed', 'processing'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              aria-pressed={filter === f}
              className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 focus:ring-offset-gray-900 ${
                filter === f
                  ? 'bg-orange-500 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-white'
              }`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Replay List */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <caption className="sr-only">Your uploaded replays</caption>
            <thead>
              <tr className="border-b border-gray-800">
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Replay
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider hidden sm:table-cell">
                  Map
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider hidden md:table-cell">
                  Playlist
                </th>
                <th scope="col" className="px-4 py-3 text-center text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Result
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider hidden lg:table-cell">
                  Date
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {filteredReplays.map((replay) => (
                <tr
                  key={replay.id}
                  className="hover:bg-gray-800/50 transition-colors"
                >
                  <td className="px-4 py-4">
                    <Link
                      href={`/replays/${replay.id}`}
                      className="text-white hover:text-orange-400 font-medium transition-colors focus:outline-none focus:text-orange-400 focus:underline"
                    >
                      {replay.filename}
                    </Link>
                  </td>
                  <td className="px-4 py-4 hidden sm:table-cell">
                    <span className="text-gray-300">{replay.map_name || '-'}</span>
                  </td>
                  <td className="px-4 py-4 hidden md:table-cell">
                    <span className="text-gray-300">{replay.playlist || '-'}</span>
                  </td>
                  <td className="px-4 py-4 text-center">
                    <div className="flex items-center justify-center gap-2">
                      <ResultBadge result={replay.result} />
                      <span className="text-gray-300">{replay.score}</span>
                    </div>
                  </td>
                  <td className="px-4 py-4 hidden lg:table-cell">
                    <span className="text-gray-400">
                      {replay.played_at ? formatDate(replay.played_at) : '-'}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    <StatusBadge status={replay.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {filteredReplays.length === 0 && (
          <div className="text-center py-12">
            <svg className="w-12 h-12 mx-auto text-gray-600 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <p className="text-gray-400 mb-4">No replays found</p>
            <p className="text-sm text-gray-500">Upload some replays to get started</p>
          </div>
        )}
      </div>
    </div>
  );
}
