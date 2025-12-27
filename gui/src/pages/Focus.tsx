import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getWeaknesses, getPatterns } from '../api/client';
import { Card, CardHeader, CardContent, SkeletonCard, ErrorState, NoDataEmpty } from '../components';

const SEVERITY_STYLES = {
  critical: 'bg-[var(--color-error)]/20 text-[var(--color-error)] border-[var(--color-error)]/50',
  moderate: 'bg-[var(--color-warning)]/20 text-[var(--color-warning)] border-[var(--color-warning)]/50',
  minor: 'bg-blue-500/20 text-blue-400 border-blue-500/50',
  strength: 'bg-[var(--color-success)]/20 text-[var(--color-success)] border-[var(--color-success)]/50',
  neutral: 'bg-[var(--color-bg-tertiary)] text-[var(--color-text-muted)] border-[var(--color-border)]',
};

export function Focus() {
  const [period] = useState('30d');
  const [rank] = useState('GC1');

  const { data: weaknessesData, isLoading: weaknessesLoading, error: weaknessesError } = useQuery({
    queryKey: ['weaknesses', period, rank],
    queryFn: () => getWeaknesses({ period, rank }),
  });

  const { data: patternsData, isLoading: patternsLoading, error: patternsError } = useQuery({
    queryKey: ['patterns', period],
    queryFn: () => getPatterns({ period }),
  });

  if (weaknessesError || patternsError) {
    return <ErrorState message="Failed to load focus areas" />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--color-text)]">Focus Areas</h1>
        <p className="text-sm text-[var(--color-text-muted)]">Areas to improve and your strengths</p>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Weaknesses */}
        <Card>
          <CardHeader>
            <h2 className="text-lg font-semibold text-[var(--color-error)]">Areas to Improve</h2>
          </CardHeader>
          <CardContent>
            {weaknessesLoading ? (
              <SkeletonCard />
            ) : weaknessesData?.weaknesses.length === 0 ? (
              <NoDataEmpty message="No weaknesses detected" />
            ) : (
              <div className="space-y-3">
                {weaknessesData?.weaknesses.map((w) => (
                  <div
                    key={w.metric}
                    className={`p-4 rounded-lg border ${SEVERITY_STYLES[w.severity]}`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium">{w.metric.toUpperCase()}</span>
                      <span className="text-xs px-2 py-1 rounded-full bg-black/20">
                        {w.severity}
                      </span>
                    </div>
                    <div className="text-sm opacity-80">
                      Your avg: {w.my_value.toFixed(2)} • {rank} median: {w.target_median.toFixed(2)}
                    </div>
                    <div className="text-xs mt-1 opacity-60">
                      Z-score: {w.z_score.toFixed(2)} ({Math.abs(w.z_score).toFixed(1)} std devs {w.z_score < 0 ? 'below' : 'above'} average)
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Strengths */}
        <Card>
          <CardHeader>
            <h2 className="text-lg font-semibold text-[var(--color-success)]">Your Strengths</h2>
          </CardHeader>
          <CardContent>
            {weaknessesLoading ? (
              <SkeletonCard />
            ) : weaknessesData?.strengths.length === 0 ? (
              <NoDataEmpty message="Keep playing to identify strengths" />
            ) : (
              <div className="space-y-3">
                {weaknessesData?.strengths.map((s) => (
                  <div
                    key={s.metric}
                    className={`p-4 rounded-lg border ${SEVERITY_STYLES.strength}`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium">{s.metric.toUpperCase()}</span>
                      <span className="text-xs px-2 py-1 rounded-full bg-black/20">
                        strength
                      </span>
                    </div>
                    <div className="text-sm opacity-80">
                      Your avg: {s.my_value.toFixed(2)} • {rank} median: {s.target_median.toFixed(2)}
                    </div>
                    <div className="text-xs mt-1 opacity-60">
                      Z-score: +{s.z_score.toFixed(2)} ({s.z_score.toFixed(1)} std devs above average)
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Win/Loss Patterns */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Win vs Loss Patterns</h2>
          {patternsData && (
            <p className="text-sm text-[var(--color-text-muted)]">
              Based on {patternsData.win_count} wins and {patternsData.loss_count} losses
            </p>
          )}
        </CardHeader>
        <CardContent>
          {patternsLoading ? (
            <SkeletonCard />
          ) : patternsData?.patterns.length === 0 ? (
            <NoDataEmpty message="Need more games to detect patterns" />
          ) : (
            <div className="space-y-4">
              {patternsData?.patterns.map((p) => (
                <div
                  key={p.metric}
                  className="flex items-center justify-between p-4 rounded-lg bg-[var(--color-bg-tertiary)]"
                >
                  <div>
                    <div className="font-medium">{p.metric.toUpperCase()}</div>
                    <div className="text-sm text-[var(--color-text-muted)]">
                      Win avg: {p.win_avg.toFixed(2)} • Loss avg: {p.loss_avg.toFixed(2)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div
                      className={`text-lg font-bold ${
                        p.direction === 'higher_when_winning'
                          ? 'text-[var(--color-success)]'
                          : 'text-[var(--color-error)]'
                      }`}
                    >
                      {p.direction === 'higher_when_winning' ? '+' : ''}{p.delta.toFixed(2)}
                    </div>
                    <div className="text-xs text-[var(--color-text-muted)]">
                      Effect size: {p.effect_size.toFixed(2)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
