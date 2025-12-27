import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer } from 'recharts';
import { getPlayer, tagPlayer } from '../api/client';
import { Card, CardHeader, CardContent, SkeletonCard, ErrorState } from '../components';

export function PlayerDetail() {
  const { playerId } = useParams<{ playerId: string }>();
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState('');
  const [isEditing, setIsEditing] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ['player', playerId],
    queryFn: () => getPlayer(playerId!),
    enabled: !!playerId,
  });

  const tagMutation = useMutation({
    mutationFn: ({ tagged, notes }: { tagged: boolean; notes?: string }) =>
      tagPlayer(playerId!, { tagged, notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['player', playerId] });
      queryClient.invalidateQueries({ queryKey: ['players'] });
      setIsEditing(false);
    },
  });

  if (error) {
    return <ErrorState message="Failed to load player" />;
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
    return <ErrorState message="Player not found" />;
  }

  const tendencyData = data.tendency_profile
    ? [
        { trait: 'Aggression', value: data.tendency_profile.aggression_score },
        { trait: 'Challenges', value: data.tendency_profile.challenge_rate },
        { trait: 'First Man', value: data.tendency_profile.first_man_tendency },
        { trait: 'Boost Priority', value: data.tendency_profile.boost_priority },
        { trait: 'Mechanics', value: data.tendency_profile.mechanical_index },
        { trait: 'Defense', value: data.tendency_profile.defensive_index },
      ]
    : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link
          to="/players"
          className="text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-[var(--color-text)]">{data.display_name}</h1>
          <p className="text-sm text-[var(--color-text-muted)]">
            {data.platform || 'Unknown Platform'} • {data.games_with_me} games together
          </p>
        </div>
        <button
          onClick={() => tagMutation.mutate({
            tagged: !data.is_tagged_teammate,
          })}
          disabled={tagMutation.isPending}
          className={`px-4 py-2 rounded-lg flex items-center gap-2 transition-colors ${
            data.is_tagged_teammate
              ? 'bg-[var(--color-primary)] text-white'
              : 'bg-[var(--color-bg-tertiary)] text-[var(--color-text)] hover:bg-[var(--color-border)]'
          }`}
        >
          {data.is_tagged_teammate ? '★ Tagged' : '☆ Tag Teammate'}
        </button>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Player Info */}
        <Card>
          <CardHeader>
            <h2 className="text-lg font-semibold">Player Info</h2>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">First Seen</span>
                <span>
                  {data.first_seen_utc
                    ? new Date(data.first_seen_utc).toLocaleDateString()
                    : 'Unknown'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">Last Seen</span>
                <span>
                  {data.last_seen_utc
                    ? new Date(data.last_seen_utc).toLocaleDateString()
                    : 'Unknown'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--color-text-muted)]">Games Together</span>
                <span>{data.games_with_me}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Notes */}
        <Card>
          <CardHeader className="flex justify-between items-center">
            <h2 className="text-lg font-semibold">Notes</h2>
            {!isEditing && (
              <button
                onClick={() => {
                  setNotes(data.teammate_notes || '');
                  setIsEditing(true);
                }}
                className="text-sm text-[var(--color-primary)] hover:text-[var(--color-primary-dark)]"
              >
                Edit
              </button>
            )}
          </CardHeader>
          <CardContent>
            {isEditing ? (
              <div className="space-y-3">
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Add notes about this player..."
                  className="w-full h-24 bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] rounded-lg px-3 py-2 text-sm text-[var(--color-text)] resize-none"
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => tagMutation.mutate({
                      tagged: data.is_tagged_teammate,
                      notes,
                    })}
                    disabled={tagMutation.isPending}
                    className="px-4 py-2 rounded-lg bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-dark)] transition-colors"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => setIsEditing(false)}
                    className="px-4 py-2 rounded-lg bg-[var(--color-bg-tertiary)] text-[var(--color-text)] hover:bg-[var(--color-border)] transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-[var(--color-text-muted)]">
                {data.teammate_notes || 'No notes yet. Click Edit to add some.'}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Tendency Profile */}
      {tendencyData.length > 0 && (
        <Card>
          <CardHeader>
            <h2 className="text-lg font-semibold">Play Style Tendencies</h2>
          </CardHeader>
          <CardContent>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={tendencyData}>
                  <PolarGrid stroke="var(--color-border)" />
                  <PolarAngleAxis
                    dataKey="trait"
                    tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
                  />
                  <Radar
                    name="Tendencies"
                    dataKey="value"
                    stroke="var(--color-primary)"
                    fill="var(--color-primary)"
                    fillOpacity={0.3}
                    strokeWidth={2}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mt-4">
              {tendencyData.map((t) => (
                <div key={t.trait} className="flex justify-between">
                  <span className="text-sm text-[var(--color-text-muted)]">{t.trait}</span>
                  <span className="text-sm font-medium">{t.value.toFixed(1)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
