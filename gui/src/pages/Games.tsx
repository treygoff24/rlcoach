import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getGames } from '../api/client';
import { Card, CardHeader, CardContent, SkeletonTable, ErrorState, NoGamesEmpty } from '../components';

export function Games() {
  const [filters, setFilters] = useState({
    playlist: '',
    result: '',
    limit: 20,
    offset: 0,
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ['games', filters],
    queryFn: () => getGames({
      playlist: filters.playlist || undefined,
      result: filters.result as 'WIN' | 'LOSS' | 'DRAW' | undefined,
      limit: filters.limit,
      offset: filters.offset,
    }),
  });

  if (error) {
    return <ErrorState message="Failed to load games" />;
  }

  const totalPages = data ? Math.ceil(data.total / filters.limit) : 0;
  const currentPage = Math.floor(filters.offset / filters.limit) + 1;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--color-text)]">Games</h1>
        <p className="text-sm text-[var(--color-text-muted)]">Browse your replay history</p>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="flex flex-wrap gap-4">
          <select
            value={filters.playlist}
            onChange={(e) => setFilters({ ...filters, playlist: e.target.value, offset: 0 })}
            className="bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]"
          >
            <option value="">All Playlists</option>
            <option value="DOUBLES">Doubles</option>
            <option value="STANDARD">Standard</option>
            <option value="DUEL">Duel</option>
          </select>
          <select
            value={filters.result}
            onChange={(e) => setFilters({ ...filters, result: e.target.value, offset: 0 })}
            className="bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]"
          >
            <option value="">All Results</option>
            <option value="WIN">Wins</option>
            <option value="LOSS">Losses</option>
            <option value="DRAW">Draws</option>
          </select>
        </CardContent>
      </Card>

      {/* Games List */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">
            {data ? `${data.total} games` : 'Loading...'}
          </h2>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4">
              <SkeletonTable rows={10} />
            </div>
          ) : data?.items.length === 0 ? (
            <NoGamesEmpty />
          ) : (
            <>
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[var(--color-border)]">
                    <th className="text-left p-4 text-sm font-medium text-[var(--color-text-muted)]">Date</th>
                    <th className="text-left p-4 text-sm font-medium text-[var(--color-text-muted)]">Playlist</th>
                    <th className="text-left p-4 text-sm font-medium text-[var(--color-text-muted)]">Result</th>
                    <th className="text-left p-4 text-sm font-medium text-[var(--color-text-muted)]">Score</th>
                    <th className="text-left p-4 text-sm font-medium text-[var(--color-text-muted)]">Duration</th>
                    <th className="text-left p-4 text-sm font-medium text-[var(--color-text-muted)]">Map</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items.map((game) => (
                    <tr
                      key={game.replay_id}
                      className="border-b border-[var(--color-border)] hover:bg-[var(--color-bg-tertiary)] transition-colors"
                    >
                      <td className="p-4">
                        <Link
                          to={`/games/${encodeURIComponent(game.replay_id)}`}
                          className="text-[var(--color-primary)] hover:underline"
                        >
                          {new Date(game.played_at_utc).toLocaleDateString()}
                        </Link>
                        <div className="text-xs text-[var(--color-text-muted)]">
                          {new Date(game.played_at_utc).toLocaleTimeString()}
                        </div>
                      </td>
                      <td className="p-4 text-sm">{game.playlist}</td>
                      <td className="p-4">
                        <span
                          className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${
                            game.result === 'WIN'
                              ? 'bg-[var(--color-success)]/20 text-[var(--color-success)]'
                              : game.result === 'LOSS'
                              ? 'bg-[var(--color-error)]/20 text-[var(--color-error)]'
                              : 'bg-[var(--color-warning)]/20 text-[var(--color-warning)]'
                          }`}
                        >
                          {game.result}
                        </span>
                      </td>
                      <td className="p-4 text-sm font-medium">
                        {game.my_score} - {game.opponent_score}
                      </td>
                      <td className="p-4 text-sm text-[var(--color-text-muted)]">
                        {Math.floor(game.duration_seconds / 60)}:{String(Math.floor(game.duration_seconds % 60)).padStart(2, '0')}
                      </td>
                      <td className="p-4 text-sm text-[var(--color-text-muted)]">{game.map}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between p-4 border-t border-[var(--color-border)]">
                  <div className="text-sm text-[var(--color-text-muted)]">
                    Page {currentPage} of {totalPages}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setFilters({ ...filters, offset: filters.offset - filters.limit })}
                      disabled={filters.offset === 0}
                      className="px-3 py-1 rounded text-sm bg-[var(--color-bg-tertiary)] text-[var(--color-text)] disabled:opacity-50 disabled:cursor-not-allowed hover:bg-[var(--color-border)] transition-colors"
                    >
                      Previous
                    </button>
                    <button
                      onClick={() => setFilters({ ...filters, offset: filters.offset + filters.limit })}
                      disabled={currentPage >= totalPages}
                      className="px-3 py-1 rounded text-sm bg-[var(--color-bg-tertiary)] text-[var(--color-text)] disabled:opacity-50 disabled:cursor-not-allowed hover:bg-[var(--color-border)] transition-colors"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
