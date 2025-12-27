import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getPlayers, tagPlayer } from '../api/client';
import { Card, CardHeader, CardContent, SkeletonTable, ErrorState, NoDataEmpty } from '../components';

export function Players() {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState({
    tagged: undefined as boolean | undefined,
    minGames: 1,
    limit: 20,
    offset: 0,
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ['players', filters],
    queryFn: () => getPlayers({
      tagged: filters.tagged,
      min_games: filters.minGames,
      limit: filters.limit,
      offset: filters.offset,
      sort: '-games_with_me',
    }),
  });

  const tagMutation = useMutation({
    mutationFn: ({ playerId, tagged }: { playerId: string; tagged: boolean }) =>
      tagPlayer(playerId, { tagged }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['players'] });
    },
  });

  if (error) {
    return <ErrorState message="Failed to load players" />;
  }

  const totalPages = data ? Math.ceil(data.total / filters.limit) : 0;
  const currentPage = Math.floor(filters.offset / filters.limit) + 1;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--color-text)]">Players</h1>
        <p className="text-sm text-[var(--color-text-muted)]">People you've played with</p>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="flex flex-wrap gap-4">
          <select
            value={filters.tagged === undefined ? '' : filters.tagged ? 'true' : 'false'}
            onChange={(e) => setFilters({
              ...filters,
              tagged: e.target.value === '' ? undefined : e.target.value === 'true',
              offset: 0,
            })}
            className="bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]"
          >
            <option value="">All Players</option>
            <option value="true">Tagged Teammates</option>
            <option value="false">Not Tagged</option>
          </select>
          <div className="flex items-center gap-2">
            <label className="text-sm text-[var(--color-text-muted)]">Min games:</label>
            <input
              type="number"
              value={filters.minGames}
              onChange={(e) => setFilters({ ...filters, minGames: parseInt(e.target.value) || 0, offset: 0 })}
              min={0}
              className="w-20 bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded px-3 py-2 text-sm text-[var(--color-text)]"
            />
          </div>
        </CardContent>
      </Card>

      {/* Players List */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">
            {data ? `${data.total} players` : 'Loading...'}
          </h2>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4">
              <SkeletonTable rows={10} />
            </div>
          ) : data?.items.length === 0 ? (
            <NoDataEmpty message="No players found" />
          ) : (
            <>
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[var(--color-border)]">
                    <th className="text-left p-4 text-sm font-medium text-[var(--color-text-muted)]">Player</th>
                    <th className="text-center p-4 text-sm font-medium text-[var(--color-text-muted)]">Games</th>
                    <th className="text-left p-4 text-sm font-medium text-[var(--color-text-muted)]">Last Seen</th>
                    <th className="text-center p-4 text-sm font-medium text-[var(--color-text-muted)]">Tagged</th>
                    <th className="text-left p-4 text-sm font-medium text-[var(--color-text-muted)]">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.items.map((player) => (
                    <tr
                      key={player.player_id}
                      className="border-b border-[var(--color-border)] hover:bg-[var(--color-bg-tertiary)] transition-colors"
                    >
                      <td className="p-4">
                        <Link
                          to={`/players/${encodeURIComponent(player.player_id)}`}
                          className="text-[var(--color-primary)] hover:underline font-medium"
                        >
                          {player.display_name}
                        </Link>
                        <div className="text-xs text-[var(--color-text-muted)]">
                          {player.platform || 'Unknown'}
                        </div>
                      </td>
                      <td className="p-4 text-center">{player.games_with_me}</td>
                      <td className="p-4 text-sm text-[var(--color-text-muted)]">
                        {player.last_seen_utc
                          ? new Date(player.last_seen_utc).toLocaleDateString()
                          : '-'}
                      </td>
                      <td className="p-4 text-center">
                        <button
                          onClick={() => tagMutation.mutate({
                            playerId: player.player_id,
                            tagged: !player.is_tagged_teammate,
                          })}
                          disabled={tagMutation.isPending}
                          className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors ${
                            player.is_tagged_teammate
                              ? 'bg-[var(--color-primary)] text-white'
                              : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)] hover:bg-[var(--color-border)]'
                          }`}
                        >
                          {player.is_tagged_teammate ? '★' : '☆'}
                        </button>
                      </td>
                      <td className="p-4 text-sm text-[var(--color-text-muted)] max-w-48 truncate">
                        {player.teammate_notes || '-'}
                      </td>
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
