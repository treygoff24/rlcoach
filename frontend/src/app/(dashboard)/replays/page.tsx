// frontend/src/app/(dashboard)/replays/page.tsx
'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';

interface Replay {
  id: string;
  replay_id?: string | null;
  filename: string;
  status: string;
  played_at: string | null;
  map_name: string | null;
  playlist: string | null;
  team_size: number | null;
  result: string | null;  // WIN, LOSS, DRAW
  my_score: number | null;
  opponent_score: number | null;
  created_at: string;
}

interface PaginatedResponse {
  items: Replay[];
  total: number;
  limit: number;
  offset: number;
}

function formatDate(dateStr: string) {
  const date = new Date(dateStr);
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}

function StatusBadge({ status }: { status: string }) {
  const normalizedStatus = status.toLowerCase();
  const config: Record<string, { bg: string; border: string; text: string; dot: string; label: string }> = {
    completed: {
      bg: 'bg-victory/15',
      border: 'border-victory/30',
      text: 'text-victory',
      dot: 'bg-victory',
      label: 'Analyzed',
    },
    processed: {
      bg: 'bg-victory/15',
      border: 'border-victory/30',
      text: 'text-victory',
      dot: 'bg-victory',
      label: 'Analyzed',
    },
    processing: {
      bg: 'bg-boost/15',
      border: 'border-boost/30',
      text: 'text-boost',
      dot: 'bg-boost animate-pulse',
      label: 'Processing',
    },
    pending: {
      bg: 'bg-white/5',
      border: 'border-white/10',
      text: 'text-white/60',
      dot: 'bg-white/40',
      label: 'Pending',
    },
    failed: {
      bg: 'bg-defeat/15',
      border: 'border-defeat/30',
      text: 'text-defeat',
      dot: 'bg-defeat',
      label: 'Failed',
    },
  };

  const style = config[normalizedStatus] || config.pending;

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${style.bg} ${style.border} ${style.text} border`}>
      <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
      {style.label}
    </span>
  );
}

function ResultBadge({ result, myScore, opponentScore }: { result: string | null; myScore: number | null; opponentScore: number | null }) {
  if (!result || result === 'UNKNOWN') {
    return <span className="text-white/50">—</span>;
  }

  const isWin = result === 'WIN';
  const score = myScore != null && opponentScore != null 
    ? `${myScore} - ${opponentScore}` 
    : '-';

  return (
    <div className="flex items-center gap-3">
      <span className={`
        inline-flex items-center justify-center w-7 h-7 rounded-lg text-xs font-bold
        ${isWin
          ? 'bg-victory/20 text-victory border border-victory/30'
          : 'bg-defeat/20 text-defeat border border-defeat/30'
        }
      `}>
        {isWin ? 'W' : 'L'}
      </span>
      <span className="font-display text-lg text-white tracking-wide">{score}</span>
    </div>
  );
}

function FilterButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`
        px-4 py-2 text-sm font-semibold rounded-xl transition-all duration-200
        focus:outline-none focus-visible:ring-2 focus-visible:ring-boost
        ${active
          ? 'bg-fire text-white shadow-glow-fire'
          : 'bg-white/5 text-white/60 hover:text-white hover:bg-white/10'
        }
      `}
    >
      {children}
    </button>
  );
}

function ReplayRow({ replay, index }: { replay: Replay; index: number }) {
  const replayId = replay.replay_id ?? replay.id;
  return (
    <tr
      className="group hover:bg-white/[0.02] transition-colors animate-slide-up opacity-0 [animation-fill-mode:forwards]"
      style={{ animationDelay: `${100 + index * 50}ms` }}
    >
      <td className="px-5 py-4">
        <Link
          href={`/replays/${replayId}`}
          className="group/link flex items-center gap-3"
        >
          {/* Replay icon */}
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-surface to-elevated flex items-center justify-center group-hover/link:from-fire/20 group-hover/link:to-fire/10 transition-all duration-200">
            <svg className="w-5 h-5 text-white/40 group-hover/link:text-fire transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <span className="font-medium text-white group-hover/link:text-fire transition-colors truncate max-w-[200px]">
            {replay.filename}
          </span>
        </Link>
      </td>
      <td className="px-5 py-4 hidden sm:table-cell">
        <span className="text-white/70">{replay.map_name || '—'}</span>
      </td>
      <td className="px-5 py-4 hidden md:table-cell">
        {replay.playlist ? (
          <span className="badge badge-boost text-[10px]">{replay.playlist}</span>
        ) : (
          <span className="text-white/50">—</span>
        )}
      </td>
      <td className="px-5 py-4">
        <ResultBadge result={replay.result} myScore={replay.my_score} opponentScore={replay.opponent_score} />
      </td>
      <td className="px-5 py-4 hidden lg:table-cell">
        <span className="text-white/50 text-sm">
          {replay.played_at ? formatDate(replay.played_at) : '—'}
        </span>
      </td>
      <td className="px-5 py-4">
        <StatusBadge status={replay.status} />
      </td>
    </tr>
  );
}

export default function ReplaysPage() {
  const [replays, setReplays] = useState<Replay[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'completed' | 'processing'>('all');

  useEffect(() => {
    async function fetchReplays() {
      try {
        setLoading(true);
        setError(null);
        
        const response = await fetch('/api/v1/replays/library');
        
        if (!response.ok) {
          if (response.status === 401) {
            setError('Please sign in to view your replays');
            return;
          }
          throw new Error(`Failed to fetch replays: ${response.status}`);
        }
        
        const data: PaginatedResponse = await response.json();
        setReplays(data.items);
      } catch (err) {
        console.error('Error fetching replays:', err);
        setError(err instanceof Error ? err.message : 'Failed to load replays');
      } finally {
        setLoading(false);
      }
    }
    
    fetchReplays();
  }, []);

  const filteredReplays = replays.filter((replay) => {
    if (filter === 'all') return true;
    const status = replay.status.toLowerCase();
    if (filter === 'completed') return status === 'completed' || status === 'processed';
    if (filter === 'processing') return status === 'processing' || status === 'pending';
    return true;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]" role="status" aria-label="Loading replays">
        <div className="relative">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-fire/30 to-boost/30 animate-pulse" />
          <div className="absolute inset-1 rounded-xl bg-void flex items-center justify-center">
            <div className="w-6 h-6 border-2 border-fire/30 border-t-fire rounded-full animate-spin" />
          </div>
        </div>
        <span className="sr-only">Loading replays...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 lg:p-8">
        <div className="card p-8 text-center">
          <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-defeat/20 flex items-center justify-center">
            <svg className="w-8 h-8 text-defeat" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <p className="text-white/70 mb-2">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="btn-primary mt-4"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 animate-fade-in">
        <div>
          <h1 className="text-4xl font-display text-white tracking-wide mb-2">REPLAYS</h1>
          <p className="text-white/50">
            {replays.length} {replays.length === 1 ? 'replay' : 'replays'} uploaded
          </p>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2" role="group" aria-label="Filter replays">
          <FilterButton active={filter === 'all'} onClick={() => setFilter('all')}>
            All
          </FilterButton>
          <FilterButton active={filter === 'completed'} onClick={() => setFilter('completed')}>
            Analyzed
          </FilterButton>
          <FilterButton active={filter === 'processing'} onClick={() => setFilter('processing')}>
            Processing
          </FilterButton>
        </div>
      </div>

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        {/* Glow border effect */}
        <div className="absolute inset-0 glow-border rounded-2xl pointer-events-none" />

        <div className="overflow-x-auto">
          <table className="w-full">
            <caption className="sr-only">Your uploaded replays</caption>
            <thead>
              <tr className="border-b border-white/5">
                <th scope="col" className="px-5 py-4 text-left">
                  <span className="stat-label">Replay</span>
                </th>
                <th scope="col" className="px-5 py-4 text-left hidden sm:table-cell">
                  <span className="stat-label">Map</span>
                </th>
                <th scope="col" className="px-5 py-4 text-left hidden md:table-cell">
                  <span className="stat-label">Playlist</span>
                </th>
                <th scope="col" className="px-5 py-4 text-left">
                  <span className="stat-label">Result</span>
                </th>
                <th scope="col" className="px-5 py-4 text-left hidden lg:table-cell">
                  <span className="stat-label">Played</span>
                </th>
                <th scope="col" className="px-5 py-4 text-left">
                  <span className="stat-label">Status</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {filteredReplays.map((replay, index) => (
                <ReplayRow key={replay.id} replay={replay} index={index} />
              ))}
            </tbody>
          </table>
        </div>

        {/* Empty state */}
        {filteredReplays.length === 0 && (
          <div className="text-center py-16 animate-fade-in">
            <div className="w-16 h-16 mx-auto mb-6 rounded-2xl bg-white/5 flex items-center justify-center">
              <svg className="w-8 h-8 text-white/50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-white/50 mb-2 font-medium">No replays found</p>
            <p className="text-sm text-white/50">
              {filter === 'all' ? 'Upload some replays to get started' : 'Try adjusting your filter'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
