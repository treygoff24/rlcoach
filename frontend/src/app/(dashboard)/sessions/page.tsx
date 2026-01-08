// frontend/src/app/(dashboard)/sessions/page.tsx
'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';

interface Session {
  id: string;
  date: string;
  duration_minutes: number;
  replay_count: number;
  wins: number;
  losses: number;
  avg_goals: number;
  avg_saves: number;
}

interface SessionsResponse {
  sessions: Session[];
  total: number;
}

function formatDate(dateStr: string) {
  const date = new Date(dateStr);
  return new Intl.DateTimeFormat('en-US', {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  }).format(date);
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchSessions() {
      try {
        setLoading(true);
        setError(null);
        
        const response = await fetch('/api/v1/replays/sessions');
        
        if (!response.ok) {
          if (response.status === 401) {
            setError('Please sign in to view your sessions');
            return;
          }
          throw new Error(`Failed to fetch sessions: ${response.status}`);
        }
        
        const data: SessionsResponse = await response.json();
        setSessions(data.sessions);
      } catch (err) {
        console.error('Error fetching sessions:', err);
        setError(err instanceof Error ? err.message : 'Failed to load sessions');
      } finally {
        setLoading(false);
      }
    }
    
    fetchSessions();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]" role="status" aria-label="Loading sessions">
        <div className="animate-spin w-8 h-8 border-2 border-orange-500 border-t-transparent rounded-full" aria-hidden="true" />
        <span className="sr-only">Loading sessions...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 lg:p-8">
        <div className="card p-8 text-center">
          <p className="text-white/70">{error}</p>
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
    <div className="p-6 lg:p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Sessions</h1>
        <p className="text-gray-400 mt-1">Your play sessions grouped by day</p>
      </div>

      {sessions.length === 0 ? (
        <div className="card p-8 text-center">
          <p className="text-white/50">No play sessions found</p>
          <p className="text-white/30 text-sm mt-2">Upload some replays to see your sessions</p>
        </div>
      ) : (
        <div className="space-y-4">
          {sessions.map((session) => {
            const winRate = session.replay_count > 0 
              ? Math.round((session.wins / session.replay_count) * 100)
              : 0;
            return (
              <Link
                key={session.id}
                href={`/replays?date=${session.date}`}
                className="block bg-gray-900/50 border border-gray-800 rounded-xl p-6 hover:border-gray-700 transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 focus:ring-offset-gray-900"
              >
                <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                  <div>
                    <h3 className="text-lg font-semibold text-white">{formatDate(session.date)}</h3>
                    <p className="text-sm text-gray-400 mt-1">
                      {session.replay_count} games • {session.duration_minutes} minutes
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-4 sm:gap-6">
                    <div className="text-center min-w-[60px]">
                      <p className="text-2xl font-bold text-white">{session.wins}-{session.losses}</p>
                      <p className="text-xs text-gray-400">W-L</p>
                    </div>
                    <div className="text-center min-w-[60px]">
                      <p className={`text-2xl font-bold ${winRate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                        {winRate}%
                      </p>
                      <p className="text-xs text-gray-400">Win Rate</p>
                    </div>
                    <div className="text-center min-w-[60px]">
                      <p className="text-2xl font-bold text-white">{session.avg_goals.toFixed(1)}</p>
                      <p className="text-xs text-gray-400">Avg Goals</p>
                    </div>
                    <div className="text-center min-w-[60px]">
                      <p className="text-2xl font-bold text-white">{session.avg_saves.toFixed(1)}</p>
                      <p className="text-xs text-gray-400">Avg Saves</p>
                    </div>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
