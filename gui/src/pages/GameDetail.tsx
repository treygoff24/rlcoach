import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getReplay } from '../api/client';
import { Card, CardHeader, CardContent, SkeletonCard, ErrorState } from '../components';

export function GameDetail() {
  const { replayId } = useParams<{ replayId: string }>();

  const { data, isLoading, error } = useQuery({
    queryKey: ['replay', replayId],
    queryFn: () => getReplay(replayId!),
    enabled: !!replayId,
  });

  if (error) {
    return <ErrorState message="Failed to load replay" />;
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (!data) {
    return <ErrorState message="Replay not found" />;
  }

  const bluePlayers = data.players.filter((p) => p.team === 'BLUE');
  const orangePlayers = data.players.filter((p) => p.team === 'ORANGE');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link
          to="/games"
          className="text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-[var(--color-text)]">
            {data.my_score} - {data.opponent_score}
            <span
              className={`ml-3 text-lg ${
                data.result === 'WIN'
                  ? 'text-[var(--color-success)]'
                  : data.result === 'LOSS'
                  ? 'text-[var(--color-error)]'
                  : 'text-[var(--color-warning)]'
              }`}
            >
              {data.result}
            </span>
          </h1>
          <p className="text-sm text-[var(--color-text-muted)]">
            {new Date(data.played_at_utc).toLocaleString()} • {data.playlist} • {data.map}
          </p>
        </div>
      </div>

      {/* Match Info */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Match Info</h2>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-sm text-[var(--color-text-muted)]">Duration</div>
              <div className="text-lg font-medium">
                {Math.floor(data.duration_seconds / 60)}:{String(Math.floor(data.duration_seconds % 60)).padStart(2, '0')}
              </div>
            </div>
            <div>
              <div className="text-sm text-[var(--color-text-muted)]">Playlist</div>
              <div className="text-lg font-medium">{data.playlist}</div>
            </div>
            <div>
              <div className="text-sm text-[var(--color-text-muted)]">Map</div>
              <div className="text-lg font-medium">{data.map}</div>
            </div>
            <div>
              <div className="text-sm text-[var(--color-text-muted)]">Final Score</div>
              <div className="text-lg font-medium">{data.my_score} - {data.opponent_score}</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Teams */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Blue Team */}
        <Card>
          <CardHeader className="bg-blue-500/10 border-b-blue-500/50">
            <h2 className="text-lg font-semibold text-blue-400">Blue Team</h2>
          </CardHeader>
          <CardContent className="p-0">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--color-border)]">
                  <th className="text-left p-3 text-xs font-medium text-[var(--color-text-muted)]">Player</th>
                  <th className="text-center p-3 text-xs font-medium text-[var(--color-text-muted)]">G</th>
                  <th className="text-center p-3 text-xs font-medium text-[var(--color-text-muted)]">A</th>
                  <th className="text-center p-3 text-xs font-medium text-[var(--color-text-muted)]">S</th>
                  <th className="text-center p-3 text-xs font-medium text-[var(--color-text-muted)]">Sh</th>
                </tr>
              </thead>
              <tbody>
                {bluePlayers.map((player) => (
                  <tr key={player.player_id} className="border-b border-[var(--color-border)]">
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <span className={player.is_me ? 'text-[var(--color-primary)] font-medium' : ''}>
                          {player.display_name}
                        </span>
                        {player.is_me && (
                          <span className="text-xs px-1.5 py-0.5 bg-[var(--color-primary)]/20 text-[var(--color-primary)] rounded">
                            You
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="text-center p-3">{player.goals}</td>
                    <td className="text-center p-3">{player.assists}</td>
                    <td className="text-center p-3">{player.saves}</td>
                    <td className="text-center p-3">{player.shots}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>

        {/* Orange Team */}
        <Card>
          <CardHeader className="bg-orange-500/10 border-b-orange-500/50">
            <h2 className="text-lg font-semibold text-orange-400">Orange Team</h2>
          </CardHeader>
          <CardContent className="p-0">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--color-border)]">
                  <th className="text-left p-3 text-xs font-medium text-[var(--color-text-muted)]">Player</th>
                  <th className="text-center p-3 text-xs font-medium text-[var(--color-text-muted)]">G</th>
                  <th className="text-center p-3 text-xs font-medium text-[var(--color-text-muted)]">A</th>
                  <th className="text-center p-3 text-xs font-medium text-[var(--color-text-muted)]">S</th>
                  <th className="text-center p-3 text-xs font-medium text-[var(--color-text-muted)]">Sh</th>
                </tr>
              </thead>
              <tbody>
                {orangePlayers.map((player) => (
                  <tr key={player.player_id} className="border-b border-[var(--color-border)]">
                    <td className="p-3">
                      <span className={player.is_me ? 'text-[var(--color-primary)] font-medium' : ''}>
                        {player.display_name}
                      </span>
                    </td>
                    <td className="text-center p-3">{player.goals}</td>
                    <td className="text-center p-3">{player.assists}</td>
                    <td className="text-center p-3">{player.saves}</td>
                    <td className="text-center p-3">{player.shots}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
