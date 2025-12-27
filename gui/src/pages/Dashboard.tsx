import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { getDashboard } from '../api/client';
import { StatCard, Card, CardHeader, CardContent, SkeletonCard, ErrorState, NoGamesEmpty } from '../components';

export function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: getDashboard,
    refetchInterval: 60000, // Refetch every minute
  });

  if (error) {
    return <ErrorState message="Failed to load dashboard" />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--color-text)]">Dashboard</h1>
        <p className="text-sm text-[var(--color-text-muted)]">Your coaching overview</p>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {isLoading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : data ? (
          <>
            <StatCard
              label="Games Today"
              value={data.quick_stats.games_today}
            />
            <StatCard
              label="Wins Today"
              value={data.quick_stats.wins_today}
              subtitle={`of ${data.quick_stats.games_today} games`}
            />
            <StatCard
              label="Win Rate"
              value={`${Math.round(data.quick_stats.win_rate_today)}%`}
              trend={data.quick_stats.win_rate_today >= 50 ? 'up' : 'down'}
            />
            <StatCard
              label="Avg Boost/Min"
              value={data.quick_stats.avg_bcpm_today?.toFixed(0) ?? '-'}
            />
          </>
        ) : null}
      </div>

      {/* Recent Games */}
      <Card>
        <CardHeader className="flex justify-between items-center">
          <h2 className="text-lg font-semibold">Recent Games</h2>
          <Link
            to="/games"
            className="text-sm text-[var(--color-primary)] hover:text-[var(--color-primary-dark)]"
          >
            View all
          </Link>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex items-center justify-between py-2">
                  <div className="h-4 w-32 bg-[var(--color-bg-tertiary)] rounded animate-pulse" />
                  <div className="h-4 w-16 bg-[var(--color-bg-tertiary)] rounded animate-pulse" />
                </div>
              ))}
            </div>
          ) : data?.recent_games.length === 0 ? (
            <NoGamesEmpty />
          ) : (
            <div className="divide-y divide-[var(--color-border)]">
              {data?.recent_games.map((game) => (
                <Link
                  key={game.replay_id}
                  to={`/games/${encodeURIComponent(game.replay_id)}`}
                  className="flex items-center justify-between px-4 py-3 hover:bg-[var(--color-bg-tertiary)] transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        game.result === 'WIN'
                          ? 'bg-[var(--color-success)]'
                          : game.result === 'LOSS'
                          ? 'bg-[var(--color-error)]'
                          : 'bg-[var(--color-warning)]'
                      }`}
                    />
                    <div>
                      <span className="text-sm font-medium">
                        {game.my_score} - {game.opponent_score}
                      </span>
                      <span className="text-xs text-[var(--color-text-muted)] ml-2">
                        {game.playlist}
                      </span>
                    </div>
                  </div>
                  <div className="text-xs text-[var(--color-text-muted)]">
                    {new Date(game.played_at_utc).toLocaleTimeString()}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
